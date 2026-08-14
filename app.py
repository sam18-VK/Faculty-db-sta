"""
Institutional Database Management System
========================================
A multi-tenant, metadata-driven web application.

Each institution gets an isolated workspace. Within it, an authenticated
admin can:

  * manage the built-in Faculty / Department / Course modules, and
  * define entirely new data sets ("record types") at runtime -- choosing
    their fields and the cardinality of the relationships between them --
    without any code changes.

User-defined data is stored using the Entity-Attribute-Value pattern
(`record` / `record_value`). EAV trades away column-level type safety, so it
is a poor default for a schema known up front; it is used deliberately here
because the schema is authored by the user at runtime and cannot be declared
in advance.
"""

import os
import sqlite3
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for, flash, g, session, abort
)
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# DATABASE_PATH lets the deployment decide where the database lives. On Render's
# free tier the filesystem is ephemeral, so this stays inside the project; once a
# persistent disk is attached, point it at e.g. /var/data/faculty.db instead.
DATABASE = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "faculty.db"))

# The product name stays constant while the institution using it varies, so
# it is configuration rather than something baked into each template.
SITE_NAME = os.environ.get("SITE_NAME", "apexdata.in")

app = Flask(__name__)
# In production set SECRET_KEY as an environment variable. The fallback below
# exists only so the app still runs out-of-the-box during local development.
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-insecure-key")
app.config["DATABASE"] = DATABASE
app.config["SITE_NAME"] = SITE_NAME

DESIGNATIONS = [
    "Professor",
    "Associate Professor",
    "Assistant Professor",
    "Lecturer",
    "Head of Department",
]

# Field types an admin can choose when designing a record type. The value is
# what gets stored in field.data_type; the label is what the admin sees.
FIELD_TYPES = [
    ("text", "Text"),
    ("number", "Number"),
    ("date", "Date"),
    ("email", "Email"),
    ("boolean", "Yes / No"),
    ("longtext", "Long text"),
]
FIELD_TYPE_LABELS = dict(FIELD_TYPES)

# Relationship cardinalities. Each is enforced in link_records(), not merely
# recorded for documentation.
CARDINALITIES = [
    ("one_to_one", "One-to-One (1:1)"),
    ("one_to_many", "One-to-Many (1:N)"),
    ("many_to_many", "Many-to-Many (M:N)"),
]
CARDINALITY_LABELS = dict(CARDINALITIES)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


SCHEMA = """
-- ===================== Tenancy & authentication =====================

CREATE TABLE IF NOT EXISTS institution (
    institution_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    code           TEXT NOT NULL UNIQUE,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_user (
    user_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_id INTEGER NOT NULL,
    username       TEXT NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    full_name      TEXT,
    created_at     TEXT NOT NULL,
    FOREIGN KEY (institution_id) REFERENCES institution (institution_id)
        ON DELETE CASCADE
);

-- ===================== Built-in modules (per institution) =====================

CREATE TABLE IF NOT EXISTS department (
    department_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_id INTEGER NOT NULL,
    name           TEXT NOT NULL,
    code           TEXT NOT NULL,
    description    TEXT,
    UNIQUE (institution_id, name),
    UNIQUE (institution_id, code),
    FOREIGN KEY (institution_id) REFERENCES institution (institution_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS faculty (
    faculty_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    department_id   INTEGER NOT NULL,
    designation     TEXT NOT NULL,
    email           TEXT,
    phone           TEXT,
    qualification   TEXT,
    specialization  TEXT,
    joining_date    TEXT,
    FOREIGN KEY (department_id) REFERENCES department (department_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS course (
    course_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    code           TEXT NOT NULL,
    department_id  INTEGER NOT NULL,
    FOREIGN KEY (department_id) REFERENCES department (department_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS faculty_course (
    faculty_id INTEGER NOT NULL,
    course_id  INTEGER NOT NULL,
    PRIMARY KEY (faculty_id, course_id),
    FOREIGN KEY (faculty_id) REFERENCES faculty (faculty_id) ON DELETE CASCADE,
    FOREIGN KEY (course_id)  REFERENCES course (course_id)  ON DELETE CASCADE
);

-- ===================== Admin-defined schema (metadata) =====================

-- One row per data set the admin creates, e.g. "Students".
CREATE TABLE IF NOT EXISTS record_type (
    type_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_id INTEGER NOT NULL,
    name           TEXT NOT NULL,
    description    TEXT,
    created_at     TEXT NOT NULL,
    UNIQUE (institution_id, name),
    FOREIGN KEY (institution_id) REFERENCES institution (institution_id)
        ON DELETE CASCADE
);

-- One row per column on a record type.
CREATE TABLE IF NOT EXISTS field (
    field_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    type_id     INTEGER NOT NULL,
    name        TEXT NOT NULL,
    data_type   TEXT NOT NULL,
    is_required INTEGER NOT NULL DEFAULT 0,
    position    INTEGER NOT NULL DEFAULT 0,
    UNIQUE (type_id, name),
    FOREIGN KEY (type_id) REFERENCES record_type (type_id) ON DELETE CASCADE
);

-- A link definition between two record types, carrying its cardinality.
CREATE TABLE IF NOT EXISTS relationship (
    rel_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    institution_id INTEGER NOT NULL,
    name           TEXT NOT NULL,
    from_type_id   INTEGER NOT NULL,
    to_type_id     INTEGER NOT NULL,
    cardinality    TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    FOREIGN KEY (institution_id) REFERENCES institution (institution_id)
        ON DELETE CASCADE,
    FOREIGN KEY (from_type_id) REFERENCES record_type (type_id) ON DELETE CASCADE,
    FOREIGN KEY (to_type_id)   REFERENCES record_type (type_id) ON DELETE CASCADE
);

-- ===================== Admin-defined data (EAV) =====================

CREATE TABLE IF NOT EXISTS record (
    record_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    type_id    INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (type_id) REFERENCES record_type (type_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS record_value (
    record_id INTEGER NOT NULL,
    field_id  INTEGER NOT NULL,
    value     TEXT,
    PRIMARY KEY (record_id, field_id),
    FOREIGN KEY (record_id) REFERENCES record (record_id) ON DELETE CASCADE,
    FOREIGN KEY (field_id)  REFERENCES field (field_id)  ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS record_link (
    rel_id         INTEGER NOT NULL,
    from_record_id INTEGER NOT NULL,
    to_record_id   INTEGER NOT NULL,
    PRIMARY KEY (rel_id, from_record_id, to_record_id),
    FOREIGN KEY (rel_id)         REFERENCES relationship (rel_id) ON DELETE CASCADE,
    FOREIGN KEY (from_record_id) REFERENCES record (record_id)    ON DELETE CASCADE,
    FOREIGN KEY (to_record_id)   REFERENCES record (record_id)    ON DELETE CASCADE
);
"""


def init_db():
    db = sqlite3.connect(DATABASE)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(SCHEMA)
    db.commit()
    db.close()


def seed_db():
    """Create a demo institution, its admin, and sample data -- but only if the
    database is empty. Safe to call on every start."""
    db = sqlite3.connect(DATABASE)
    db.execute("PRAGMA foreign_keys = ON")
    cur = db.cursor()

    cur.execute("SELECT COUNT(*) FROM institution")
    if cur.fetchone()[0] > 0:
        db.close()
        return

    now = datetime.utcnow().isoformat(timespec="seconds")

    # --- Two institutions, to make tenant isolation demonstrable ---
    cur.execute(
        "INSERT INTO institution (name, code, created_at) VALUES (?, ?, ?)",
        ("Apex Institute of Science, Technology & Architecture", "APEX", now),
    )
    apex_id = cur.lastrowid
    cur.execute(
        "INSERT INTO institution (name, code, created_at) VALUES (?, ?, ?)",
        ("Northfield College", "NORTH", now),
    )
    north_id = cur.lastrowid

    # --- Admin accounts (passwords are hashed, never stored in plain text) ---
    cur.executemany(
        """INSERT INTO admin_user
           (institution_id, username, password_hash, full_name, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        [
            (apex_id, "admin", generate_password_hash("admin123"),
             "Apex Administrator", now),
            (north_id, "northadmin", generate_password_hash("north123"),
             "Northfield Administrator", now),
        ],
    )

    # --- Built-in modules for the Apex institution ---
    departments = [
        (apex_id, "Science", "SCI", "Department of Science"),
        (apex_id, "Technology", "TECH", "Department of Technology"),
        (apex_id, "Architecture", "ARCH", "Department of Architecture"),
    ]
    cur.executemany(
        "INSERT INTO department (institution_id, name, code, description) VALUES (?, ?, ?, ?)",
        departments,
    )
    db.commit()

    dept_ids = {
        row[0]: row[1]
        for row in cur.execute(
            "SELECT name, department_id FROM department WHERE institution_id = ?",
            (apex_id,),
        )
    }

    courses = [
        ("Physics I", "SCI101", dept_ids["Science"]),
        ("Organic Chemistry", "SCI205", dept_ids["Science"]),
        ("Data Structures", "TECH210", dept_ids["Technology"]),
        ("Database Systems", "TECH301", dept_ids["Technology"]),
        ("Computer Networks", "TECH330", dept_ids["Technology"]),
        ("Architectural Design Studio", "ARCH150", dept_ids["Architecture"]),
        ("Building Construction", "ARCH220", dept_ids["Architecture"]),
    ]
    cur.executemany(
        "INSERT INTO course (name, code, department_id) VALUES (?, ?, ?)", courses
    )

    faculty = [
        ("Dr. Anjali Rao", dept_ids["Science"], "Professor", "anjali.rao@univ.edu",
         "9876500001", "Ph.D. Physics", "Quantum Mechanics", "2012-07-01"),
        ("Dr. Rakesh Menon", dept_ids["Science"], "Associate Professor", "rakesh.menon@univ.edu",
         "9876500002", "Ph.D. Chemistry", "Organic Chemistry", "2015-01-15"),
        ("Dr. Priya Nair", dept_ids["Technology"], "Head of Department", "priya.nair@univ.edu",
         "9876500003", "Ph.D. Computer Science", "Databases & AI", "2009-06-01"),
        ("Er. Suresh Kumar", dept_ids["Technology"], "Assistant Professor", "suresh.kumar@univ.edu",
         "9876500004", "M.Tech CSE", "Computer Networks", "2018-08-20"),
        ("Ar. Meera Iyer", dept_ids["Architecture"], "Professor", "meera.iyer@univ.edu",
         "9876500005", "M.Arch", "Urban Design", "2011-03-10"),
        ("Ar. Vikram Shah", dept_ids["Architecture"], "Lecturer", "vikram.shah@univ.edu",
         "9876500006", "B.Arch, M.Plan", "Building Construction", "2020-09-01"),
    ]
    cur.executemany(
        """INSERT INTO faculty
           (name, department_id, designation, email, phone, qualification,
            specialization, joining_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        faculty,
    )
    db.commit()

    fac_ids = {
        r[0]: r[1]
        for r in cur.execute(
            """SELECT f.email, f.faculty_id FROM faculty f
               JOIN department d ON d.department_id = f.department_id
               WHERE d.institution_id = ?""",
            (apex_id,),
        )
    }
    course_ids = {
        r[0]: r[1]
        for r in cur.execute(
            """SELECT c.code, c.course_id FROM course c
               JOIN department d ON d.department_id = c.department_id
               WHERE d.institution_id = ?""",
            (apex_id,),
        )
    }
    cur.executemany(
        "INSERT INTO faculty_course (faculty_id, course_id) VALUES (?, ?)",
        [
            (fac_ids["anjali.rao@univ.edu"], course_ids["SCI101"]),
            (fac_ids["rakesh.menon@univ.edu"], course_ids["SCI205"]),
            (fac_ids["priya.nair@univ.edu"], course_ids["TECH301"]),
            (fac_ids["priya.nair@univ.edu"], course_ids["TECH210"]),
            (fac_ids["suresh.kumar@univ.edu"], course_ids["TECH330"]),
            (fac_ids["meera.iyer@univ.edu"], course_ids["ARCH150"]),
            (fac_ids["vikram.shah@univ.edu"], course_ids["ARCH220"]),
        ],
    )

    # --- A worked example of an admin-defined data set: Students ---
    cur.execute(
        "INSERT INTO record_type (institution_id, name, description, created_at) VALUES (?, ?, ?, ?)",
        (apex_id, "Students", "Enrolled student records", now),
    )
    student_type = cur.lastrowid
    cur.executemany(
        "INSERT INTO field (type_id, name, data_type, is_required, position) VALUES (?, ?, ?, ?, ?)",
        [
            (student_type, "Roll Number", "text", 1, 0),
            (student_type, "Full Name", "text", 1, 1),
            (student_type, "Email", "email", 0, 2),
            (student_type, "Year of Study", "number", 0, 3),
            (student_type, "Enrolment Date", "date", 0, 4),
            (student_type, "Hostel Resident", "boolean", 0, 5),
        ],
    )
    db.commit()

    fields = {
        r[0]: r[1]
        for r in cur.execute("SELECT name, field_id FROM field WHERE type_id = ?", (student_type,))
    }
    sample_students = [
        {"Roll Number": "APEX2024001", "Full Name": "Aditya Sharma",
         "Email": "aditya.s@apex.edu", "Year of Study": "2",
         "Enrolment Date": "2024-07-15", "Hostel Resident": "Yes"},
        {"Roll Number": "APEX2024002", "Full Name": "Fatima Khan",
         "Email": "fatima.k@apex.edu", "Year of Study": "3",
         "Enrolment Date": "2023-07-12", "Hostel Resident": "No"},
        {"Roll Number": "APEX2024003", "Full Name": "Joseph Mathew",
         "Email": "joseph.m@apex.edu", "Year of Study": "1",
         "Enrolment Date": "2025-07-10", "Hostel Resident": "Yes"},
    ]
    for stu in sample_students:
        cur.execute(
            "INSERT INTO record (type_id, created_at) VALUES (?, ?)", (student_type, now)
        )
        rid = cur.lastrowid
        cur.executemany(
            "INSERT INTO record_value (record_id, field_id, value) VALUES (?, ?, ?)",
            [(rid, fields[k], v) for k, v in stu.items()],
        )

    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Authentication & tenant scoping
# ---------------------------------------------------------------------------
def current_user():
    """The logged-in admin row, or None."""
    uid = session.get("user_id")
    if uid is None:
        return None
    return get_db().execute(
        """SELECT u.*, i.name AS institution_name, i.code AS institution_code
           FROM admin_user u JOIN institution i ON i.institution_id = u.institution_id
           WHERE u.user_id = ?""",
        (uid,),
    ).fetchone()


def institution_id():
    """The tenant every query in this request must be scoped to.

    Reading it from the session rather than the URL is deliberate: it means a
    user cannot reach another institution's data by editing an id in the
    address bar.
    """
    return session.get("institution_id")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("user_id") is None:
            flash("Please sign in to continue.", "danger")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


@app.context_processor
def inject_globals():
    """Make the current admin and the site name available to every template."""
    return {"current_user": current_user(), "site_name": app.config["SITE_NAME"]}


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT * FROM admin_user WHERE username = ?", (username,)
        ).fetchone()

        # A single generic message for both unknown-user and wrong-password,
        # so the form can't be used to discover which usernames exist.
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Incorrect username or password.", "danger")
        else:
            session.clear()
            session["user_id"] = user["user_id"]
            session["institution_id"] = user["institution_id"]
            flash(f"Welcome back, {user['full_name'] or user['username']}.", "success")
            nxt = request.args.get("next")
            # Only allow relative redirects, otherwise ?next=https://evil.site
            # would turn the login form into an open redirect.
            if nxt and nxt.startswith("/"):
                return redirect(nxt)
            return redirect(url_for("dashboard"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("login"))


def owned_record_type(type_id):
    """Fetch a record type, or 404 if it belongs to another institution."""
    rt = get_db().execute(
        "SELECT * FROM record_type WHERE type_id = ? AND institution_id = ?",
        (type_id, institution_id()),
    ).fetchone()
    if rt is None:
        abort(404)
    return rt


def owned_department(department_id):
    dept = get_db().execute(
        "SELECT * FROM department WHERE department_id = ? AND institution_id = ?",
        (department_id, institution_id()),
    ).fetchone()
    if dept is None:
        abort(404)
    return dept


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@app.route("/")
@login_required
def dashboard():
    db = get_db()
    inst = institution_id()

    total_faculty = db.execute(
        """SELECT COUNT(*) FROM faculty f
           JOIN department d ON d.department_id = f.department_id
           WHERE d.institution_id = ?""",
        (inst,),
    ).fetchone()[0]
    total_courses = db.execute(
        """SELECT COUNT(*) FROM course c
           JOIN department d ON d.department_id = c.department_id
           WHERE d.institution_id = ?""",
        (inst,),
    ).fetchone()[0]
    dept_counts = db.execute(
        """SELECT d.department_id, d.name, COUNT(f.faculty_id) AS cnt
           FROM department d LEFT JOIN faculty f ON f.department_id = d.department_id
           WHERE d.institution_id = ?
           GROUP BY d.department_id ORDER BY d.name""",
        (inst,),
    ).fetchall()

    custom_types = db.execute(
        """SELECT rt.*,
                  (SELECT COUNT(*) FROM field fl WHERE fl.type_id = rt.type_id) AS field_count,
                  (SELECT COUNT(*) FROM record r WHERE r.type_id = rt.type_id) AS record_count
           FROM record_type rt WHERE rt.institution_id = ?
           ORDER BY rt.name""",
        (inst,),
    ).fetchall()
    total_relationships = db.execute(
        "SELECT COUNT(*) FROM relationship WHERE institution_id = ?", (inst,)
    ).fetchone()[0]

    return render_template(
        "dashboard.html",
        total_faculty=total_faculty,
        total_courses=total_courses,
        dept_counts=dept_counts,
        custom_types=custom_types,
        total_relationships=total_relationships,
    )


# ---------------------------------------------------------------------------
# Faculty
# ---------------------------------------------------------------------------
@app.route("/faculty")
@login_required
def faculty_list():
    db = get_db()
    inst = institution_id()
    departments = db.execute(
        "SELECT * FROM department WHERE institution_id = ? ORDER BY name", (inst,)
    ).fetchall()

    q = request.args.get("q", "").strip()
    department_id = request.args.get("department_id", "")
    designation = request.args.get("designation", "")

    query = """
        SELECT f.*, d.name AS department_name
        FROM faculty f
        JOIN department d ON d.department_id = f.department_id
        WHERE d.institution_id = ?
    """
    params = [inst]
    if q:
        query += " AND (f.name LIKE ? OR f.email LIKE ? OR f.specialization LIKE ?)"
        like = f"%{q}%"
        params += [like, like, like]
    if department_id:
        query += " AND f.department_id = ?"
        params.append(department_id)
    if designation:
        query += " AND f.designation = ?"
        params.append(designation)
    query += " ORDER BY f.name"

    return render_template(
        "faculty_list.html",
        faculty_rows=db.execute(query, params).fetchall(),
        departments=departments,
        designations=DESIGNATIONS,
        q=q,
        selected_department=department_id,
        selected_designation=designation,
    )


@app.route("/faculty/<int:faculty_id>")
@login_required
def faculty_detail(faculty_id):
    db = get_db()
    faculty = db.execute(
        """SELECT f.*, d.name AS department_name
           FROM faculty f JOIN department d ON d.department_id = f.department_id
           WHERE f.faculty_id = ? AND d.institution_id = ?""",
        (faculty_id, institution_id()),
    ).fetchone()
    if faculty is None:
        abort(404)

    courses = db.execute(
        """SELECT c.* FROM course c
           JOIN faculty_course fc ON fc.course_id = c.course_id
           WHERE fc.faculty_id = ? ORDER BY c.name""",
        (faculty_id,),
    ).fetchall()
    return render_template("faculty_detail.html", faculty=faculty, courses=courses)


def _faculty_form_context(faculty, form_action):
    db = get_db()
    inst = institution_id()
    return dict(
        faculty=faculty,
        departments=db.execute(
            "SELECT * FROM department WHERE institution_id = ? ORDER BY name", (inst,)
        ).fetchall(),
        designations=DESIGNATIONS,
        all_courses=db.execute(
            """SELECT c.* FROM course c
               JOIN department d ON d.department_id = c.department_id
               WHERE d.institution_id = ? ORDER BY c.name""",
            (inst,),
        ).fetchall(),
        form_action=form_action,
    )


@app.route("/faculty/add", methods=["GET", "POST"])
@login_required
def faculty_add():
    db = get_db()
    if request.method == "POST":
        form = request.form
        owned_department(form["department_id"])  # reject cross-tenant ids
        try:
            cur = db.execute(
                """INSERT INTO faculty
                   (name, department_id, designation, email, phone, qualification,
                    specialization, joining_date)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    form["name"].strip(), form["department_id"], form["designation"],
                    form.get("email", "").strip() or None,
                    form.get("phone", "").strip(),
                    form.get("qualification", "").strip(),
                    form.get("specialization", "").strip(),
                    form.get("joining_date", "").strip() or None,
                ),
            )
            for cid in request.form.getlist("course_ids"):
                db.execute(
                    "INSERT INTO faculty_course (faculty_id, course_id) VALUES (?, ?)",
                    (cur.lastrowid, cid),
                )
            db.commit()
            flash(f"Faculty '{form['name']}' added successfully.", "success")
            return redirect(url_for("faculty_list"))
        except sqlite3.IntegrityError as e:
            flash(f"Could not save record: {e}", "danger")

    ctx = _faculty_form_context(None, url_for("faculty_add"))
    ctx["assigned_course_ids"] = set()
    return render_template("faculty_form.html", **ctx)


@app.route("/faculty/<int:faculty_id>/edit", methods=["GET", "POST"])
@login_required
def faculty_edit(faculty_id):
    db = get_db()
    faculty = db.execute(
        """SELECT f.* FROM faculty f
           JOIN department d ON d.department_id = f.department_id
           WHERE f.faculty_id = ? AND d.institution_id = ?""",
        (faculty_id, institution_id()),
    ).fetchone()
    if faculty is None:
        abort(404)

    if request.method == "POST":
        form = request.form
        owned_department(form["department_id"])
        try:
            db.execute(
                """UPDATE faculty SET name=?, department_id=?, designation=?, email=?,
                   phone=?, qualification=?, specialization=?, joining_date=?
                   WHERE faculty_id=?""",
                (
                    form["name"].strip(), form["department_id"], form["designation"],
                    form.get("email", "").strip() or None,
                    form.get("phone", "").strip(),
                    form.get("qualification", "").strip(),
                    form.get("specialization", "").strip(),
                    form.get("joining_date", "").strip() or None,
                    faculty_id,
                ),
            )
            db.execute("DELETE FROM faculty_course WHERE faculty_id = ?", (faculty_id,))
            for cid in request.form.getlist("course_ids"):
                db.execute(
                    "INSERT INTO faculty_course (faculty_id, course_id) VALUES (?, ?)",
                    (faculty_id, cid),
                )
            db.commit()
            flash(f"Faculty '{form['name']}' updated successfully.", "success")
            return redirect(url_for("faculty_detail", faculty_id=faculty_id))
        except sqlite3.IntegrityError as e:
            flash(f"Could not update record: {e}", "danger")

    ctx = _faculty_form_context(faculty, url_for("faculty_edit", faculty_id=faculty_id))
    ctx["assigned_course_ids"] = {
        r["course_id"] for r in db.execute(
            "SELECT course_id FROM faculty_course WHERE faculty_id = ?", (faculty_id,)
        )
    }
    return render_template("faculty_form.html", **ctx)


@app.route("/faculty/<int:faculty_id>/delete", methods=["POST"])
@login_required
def faculty_delete(faculty_id):
    db = get_db()
    faculty = db.execute(
        """SELECT f.name FROM faculty f
           JOIN department d ON d.department_id = f.department_id
           WHERE f.faculty_id = ? AND d.institution_id = ?""",
        (faculty_id, institution_id()),
    ).fetchone()
    if faculty is None:
        abort(404)
    db.execute("DELETE FROM faculty WHERE faculty_id = ?", (faculty_id,))
    db.commit()
    flash(f"Faculty '{faculty['name']}' deleted.", "success")
    return redirect(url_for("faculty_list"))


# ---------------------------------------------------------------------------
# Departments
# ---------------------------------------------------------------------------
@app.route("/departments")
@login_required
def department_list():
    departments = get_db().execute(
        """SELECT d.*,
                  (SELECT COUNT(*) FROM faculty f WHERE f.department_id = d.department_id) AS faculty_count,
                  (SELECT COUNT(*) FROM course c WHERE c.department_id = d.department_id) AS course_count
           FROM department d WHERE d.institution_id = ? ORDER BY d.name""",
        (institution_id(),),
    ).fetchall()
    return render_template("department_list.html", departments=departments)


@app.route("/departments/add", methods=["GET", "POST"])
@login_required
def department_add():
    db = get_db()
    if request.method == "POST":
        form = request.form
        try:
            db.execute(
                "INSERT INTO department (institution_id, name, code, description) VALUES (?, ?, ?, ?)",
                (institution_id(), form["name"].strip(), form["code"].strip().upper(),
                 form.get("description", "").strip()),
            )
            db.commit()
            flash(f"Department '{form['name']}' added successfully.", "success")
            return redirect(url_for("department_list"))
        except sqlite3.IntegrityError:
            flash("A department with that name or code already exists.", "danger")

    return render_template("department_form.html", department=None,
                           form_action=url_for("department_add"))


@app.route("/departments/<int:department_id>/edit", methods=["GET", "POST"])
@login_required
def department_edit(department_id):
    db = get_db()
    department = owned_department(department_id)

    if request.method == "POST":
        form = request.form
        try:
            db.execute(
                "UPDATE department SET name=?, code=?, description=? WHERE department_id=?",
                (form["name"].strip(), form["code"].strip().upper(),
                 form.get("description", "").strip(), department_id),
            )
            db.commit()
            flash(f"Department '{form['name']}' updated successfully.", "success")
            return redirect(url_for("department_list"))
        except sqlite3.IntegrityError:
            flash("A department with that name or code already exists.", "danger")

    return render_template("department_form.html", department=department,
                           form_action=url_for("department_edit", department_id=department_id))


@app.route("/departments/<int:department_id>/delete", methods=["POST"])
@login_required
def department_delete(department_id):
    db = get_db()
    department = owned_department(department_id)

    # Refuse to delete while records still depend on this department, rather
    # than silently cascading away faculty and course rows.
    faculty_count = db.execute(
        "SELECT COUNT(*) FROM faculty WHERE department_id = ?", (department_id,)
    ).fetchone()[0]
    course_count = db.execute(
        "SELECT COUNT(*) FROM course WHERE department_id = ?", (department_id,)
    ).fetchone()[0]

    if faculty_count or course_count:
        flash(
            f"Cannot delete '{department['name']}' — it still has "
            f"{faculty_count} faculty and {course_count} course(s). "
            "Reassign or remove those first.",
            "danger",
        )
        return redirect(url_for("department_list"))

    db.execute("DELETE FROM department WHERE department_id = ?", (department_id,))
    db.commit()
    flash(f"Department '{department['name']}' deleted.", "success")
    return redirect(url_for("department_list"))


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------
@app.route("/courses")
@login_required
def course_list():
    courses = get_db().execute(
        """SELECT c.*, d.name AS department_name,
                  (SELECT COUNT(*) FROM faculty_course fc WHERE fc.course_id = c.course_id) AS faculty_count
           FROM course c JOIN department d ON d.department_id = c.department_id
           WHERE d.institution_id = ? ORDER BY d.name, c.name""",
        (institution_id(),),
    ).fetchall()
    return render_template("course_list.html", courses=courses)


def _course_departments():
    return get_db().execute(
        "SELECT * FROM department WHERE institution_id = ? ORDER BY name",
        (institution_id(),),
    ).fetchall()


def owned_course(course_id):
    course = get_db().execute(
        """SELECT c.* FROM course c JOIN department d ON d.department_id = c.department_id
           WHERE c.course_id = ? AND d.institution_id = ?""",
        (course_id, institution_id()),
    ).fetchone()
    if course is None:
        abort(404)
    return course


@app.route("/courses/add", methods=["GET", "POST"])
@login_required
def course_add():
    db = get_db()
    if request.method == "POST":
        form = request.form
        owned_department(form["department_id"])
        try:
            db.execute(
                "INSERT INTO course (name, code, department_id) VALUES (?, ?, ?)",
                (form["name"].strip(), form["code"].strip().upper(), form["department_id"]),
            )
            db.commit()
            flash(f"Course '{form['name']}' added successfully.", "success")
            return redirect(url_for("course_list"))
        except sqlite3.IntegrityError:
            flash("A course with that code already exists.", "danger")

    return render_template("course_form.html", course=None,
                           departments=_course_departments(),
                           form_action=url_for("course_add"))


@app.route("/courses/<int:course_id>/edit", methods=["GET", "POST"])
@login_required
def course_edit(course_id):
    db = get_db()
    course = owned_course(course_id)

    if request.method == "POST":
        form = request.form
        owned_department(form["department_id"])
        try:
            db.execute(
                "UPDATE course SET name=?, code=?, department_id=? WHERE course_id=?",
                (form["name"].strip(), form["code"].strip().upper(),
                 form["department_id"], course_id),
            )
            db.commit()
            flash(f"Course '{form['name']}' updated successfully.", "success")
            return redirect(url_for("course_list"))
        except sqlite3.IntegrityError:
            flash("A course with that code already exists.", "danger")

    return render_template("course_form.html", course=course,
                           departments=_course_departments(),
                           form_action=url_for("course_edit", course_id=course_id))


@app.route("/courses/<int:course_id>/delete", methods=["POST"])
@login_required
def course_delete(course_id):
    db = get_db()
    course = owned_course(course_id)
    assigned = db.execute(
        "SELECT COUNT(*) FROM faculty_course WHERE course_id = ?", (course_id,)
    ).fetchone()[0]
    if assigned:
        flash(
            f"Cannot delete '{course['name']}' — {assigned} faculty member(s) "
            "are still assigned to it. Unassign them first.",
            "danger",
        )
        return redirect(url_for("course_list"))

    db.execute("DELETE FROM course WHERE course_id = ?", (course_id,))
    db.commit()
    flash(f"Course '{course['name']}' deleted.", "success")
    return redirect(url_for("course_list"))


# ---------------------------------------------------------------------------
# Schema designer: admin-defined record types and their fields
# ---------------------------------------------------------------------------
@app.route("/data")
@login_required
def type_list():
    types = get_db().execute(
        """SELECT rt.*,
                  (SELECT COUNT(*) FROM field f WHERE f.type_id = rt.type_id) AS field_count,
                  (SELECT COUNT(*) FROM record r WHERE r.type_id = rt.type_id) AS record_count
           FROM record_type rt WHERE rt.institution_id = ? ORDER BY rt.name""",
        (institution_id(),),
    ).fetchall()
    return render_template("type_list.html", types=types)


@app.route("/data/new", methods=["GET", "POST"])
@login_required
def type_add():
    db = get_db()
    if request.method == "POST":
        name = request.form["name"].strip()
        try:
            cur = db.execute(
                "INSERT INTO record_type (institution_id, name, description, created_at) VALUES (?, ?, ?, ?)",
                (institution_id(), name, request.form.get("description", "").strip(),
                 datetime.utcnow().isoformat(timespec="seconds")),
            )
            db.commit()
            flash(f"Data set '{name}' created. Now add some fields to it.", "success")
            return redirect(url_for("type_detail", type_id=cur.lastrowid))
        except sqlite3.IntegrityError:
            flash("You already have a data set with that name.", "danger")

    return render_template("type_form.html", record_type=None,
                           form_action=url_for("type_add"))


@app.route("/data/<int:type_id>/edit", methods=["GET", "POST"])
@login_required
def type_edit(type_id):
    db = get_db()
    rt = owned_record_type(type_id)
    if request.method == "POST":
        name = request.form["name"].strip()
        try:
            db.execute(
                "UPDATE record_type SET name=?, description=? WHERE type_id=?",
                (name, request.form.get("description", "").strip(), type_id),
            )
            db.commit()
            flash(f"Data set renamed to '{name}'.", "success")
            return redirect(url_for("type_detail", type_id=type_id))
        except sqlite3.IntegrityError:
            flash("You already have a data set with that name.", "danger")

    return render_template("type_form.html", record_type=rt,
                           form_action=url_for("type_edit", type_id=type_id))


@app.route("/data/<int:type_id>/delete", methods=["POST"])
@login_required
def type_delete(type_id):
    db = get_db()
    rt = owned_record_type(type_id)
    n = db.execute("SELECT COUNT(*) FROM record WHERE type_id = ?", (type_id,)).fetchone()[0]
    if n:
        flash(
            f"Cannot delete '{rt['name']}' — it still holds {n} record(s). "
            "Delete those first.",
            "danger",
        )
        return redirect(url_for("type_detail", type_id=type_id))

    db.execute("DELETE FROM record_type WHERE type_id = ?", (type_id,))
    db.commit()
    flash(f"Data set '{rt['name']}' deleted.", "success")
    return redirect(url_for("type_list"))


@app.route("/data/<int:type_id>")
@login_required
def type_detail(type_id):
    db = get_db()
    rt = owned_record_type(type_id)
    fields = db.execute(
        "SELECT * FROM field WHERE type_id = ? ORDER BY position, field_id", (type_id,)
    ).fetchall()
    relationships = db.execute(
        """SELECT r.*, ft.name AS from_name, tt.name AS to_name
           FROM relationship r
           JOIN record_type ft ON ft.type_id = r.from_type_id
           JOIN record_type tt ON tt.type_id = r.to_type_id
           WHERE r.institution_id = ? AND (r.from_type_id = ? OR r.to_type_id = ?)
           ORDER BY r.name""",
        (institution_id(), type_id, type_id),
    ).fetchall()
    record_count = db.execute(
        "SELECT COUNT(*) FROM record WHERE type_id = ?", (type_id,)
    ).fetchone()[0]

    return render_template(
        "type_detail.html",
        record_type=rt,
        fields=fields,
        relationships=relationships,
        record_count=record_count,
        field_types=FIELD_TYPES,
        cardinality_labels=CARDINALITY_LABELS,
    )


@app.route("/data/<int:type_id>/fields/add", methods=["POST"])
@login_required
def field_add(type_id):
    db = get_db()
    owned_record_type(type_id)
    name = request.form["name"].strip()
    data_type = request.form["data_type"]

    if data_type not in FIELD_TYPE_LABELS:
        abort(400)

    nxt = db.execute(
        "SELECT COALESCE(MAX(position), -1) + 1 FROM field WHERE type_id = ?", (type_id,)
    ).fetchone()[0]
    try:
        db.execute(
            "INSERT INTO field (type_id, name, data_type, is_required, position) VALUES (?, ?, ?, ?, ?)",
            (type_id, name, data_type, 1 if request.form.get("is_required") else 0, nxt),
        )
        db.commit()
        flash(f"Field '{name}' added.", "success")
    except sqlite3.IntegrityError:
        flash(f"This data set already has a field called '{name}'.", "danger")

    return redirect(url_for("type_detail", type_id=type_id))


@app.route("/data/<int:type_id>/fields/<int:field_id>/delete", methods=["POST"])
@login_required
def field_delete(type_id, field_id):
    db = get_db()
    owned_record_type(type_id)
    fld = db.execute(
        "SELECT * FROM field WHERE field_id = ? AND type_id = ?", (field_id, type_id)
    ).fetchone()
    if fld is None:
        abort(404)

    # Deleting a field also discards every value stored against it, so say so
    # rather than letting the cascade happen silently.
    n = db.execute(
        "SELECT COUNT(*) FROM record_value WHERE field_id = ? AND value IS NOT NULL AND value != ''",
        (field_id,),
    ).fetchone()[0]
    db.execute("DELETE FROM field WHERE field_id = ?", (field_id,))
    db.commit()
    msg = f"Field '{fld['name']}' deleted."
    if n:
        msg += f" {n} stored value(s) were removed with it."
    flash(msg, "success")
    return redirect(url_for("type_detail", type_id=type_id))


# ---------------------------------------------------------------------------
# Relationships between admin-defined data sets
# ---------------------------------------------------------------------------
def owned_relationship(rel_id):
    rel = get_db().execute(
        """SELECT r.*, ft.name AS from_name, tt.name AS to_name
           FROM relationship r
           JOIN record_type ft ON ft.type_id = r.from_type_id
           JOIN record_type tt ON tt.type_id = r.to_type_id
           WHERE r.rel_id = ? AND r.institution_id = ?""",
        (rel_id, institution_id()),
    ).fetchone()
    if rel is None:
        abort(404)
    return rel


def cardinality_violation(rel, from_record_id, to_record_id):
    """Return an explanatory message if this link would break the relationship's
    declared cardinality, otherwise None.

    This is where the cardinality an admin chooses stops being documentation and
    starts being a constraint. SQLite cannot express these rules declaratively
    for EAV-style links, so they are checked here before the insert.
    """
    db = get_db()
    rel_id = rel["rel_id"]
    card = rel["cardinality"]

    if card == "many_to_many":
        return None

    # In both 1:1 and 1:N, each "to" record may belong to only one "from".
    existing_to = db.execute(
        "SELECT COUNT(*) FROM record_link WHERE rel_id = ? AND to_record_id = ?",
        (rel_id, to_record_id),
    ).fetchone()[0]
    if existing_to:
        return (
            f"That {rel['to_name']} record is already linked to a "
            f"{rel['from_name']} record. '{rel['name']}' is "
            f"{CARDINALITY_LABELS[card]}, so it can only belong to one."
        )

    # 1:1 additionally caps the "from" side at a single link.
    if card == "one_to_one":
        existing_from = db.execute(
            "SELECT COUNT(*) FROM record_link WHERE rel_id = ? AND from_record_id = ?",
            (rel_id, from_record_id),
        ).fetchone()[0]
        if existing_from:
            return (
                f"That {rel['from_name']} record is already linked to a "
                f"{rel['to_name']} record. '{rel['name']}' is One-to-One, "
                "so each side can hold only one link."
            )

    return None


@app.route("/relationships")
@login_required
def relationship_list():
    db = get_db()
    inst = institution_id()
    relationships = db.execute(
        """SELECT r.*, ft.name AS from_name, tt.name AS to_name,
                  (SELECT COUNT(*) FROM record_link rl WHERE rl.rel_id = r.rel_id) AS link_count
           FROM relationship r
           JOIN record_type ft ON ft.type_id = r.from_type_id
           JOIN record_type tt ON tt.type_id = r.to_type_id
           WHERE r.institution_id = ? ORDER BY r.name""",
        (inst,),
    ).fetchall()
    types = db.execute(
        "SELECT * FROM record_type WHERE institution_id = ? ORDER BY name", (inst,)
    ).fetchall()
    return render_template(
        "relationship_list.html",
        relationships=relationships,
        types=types,
        cardinalities=CARDINALITIES,
        cardinality_labels=CARDINALITY_LABELS,
    )


@app.route("/relationships/add", methods=["POST"])
@login_required
def relationship_add():
    db = get_db()
    form = request.form
    from_type = owned_record_type(form["from_type_id"])
    to_type = owned_record_type(form["to_type_id"])
    cardinality = form["cardinality"]

    if cardinality not in CARDINALITY_LABELS:
        abort(400)

    db.execute(
        """INSERT INTO relationship
           (institution_id, name, from_type_id, to_type_id, cardinality, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (institution_id(), form["name"].strip(), from_type["type_id"],
         to_type["type_id"], cardinality,
         datetime.utcnow().isoformat(timespec="seconds")),
    )
    db.commit()
    flash(
        f"Relationship '{form['name']}' created: {from_type['name']} → "
        f"{to_type['name']} ({CARDINALITY_LABELS[cardinality]}).",
        "success",
    )
    return redirect(url_for("relationship_list"))


@app.route("/relationships/<int:rel_id>/delete", methods=["POST"])
@login_required
def relationship_delete(rel_id):
    db = get_db()
    rel = owned_relationship(rel_id)
    n = db.execute(
        "SELECT COUNT(*) FROM record_link WHERE rel_id = ?", (rel_id,)
    ).fetchone()[0]
    db.execute("DELETE FROM relationship WHERE rel_id = ?", (rel_id,))
    db.commit()
    msg = f"Relationship '{rel['name']}' deleted."
    if n:
        msg += f" {n} link(s) between records were removed with it."
    flash(msg, "success")
    return redirect(url_for("relationship_list"))


# ---------------------------------------------------------------------------
# Records inside admin-defined data sets (generated from metadata)
# ---------------------------------------------------------------------------
def type_fields(type_id):
    return get_db().execute(
        "SELECT * FROM field WHERE type_id = ? ORDER BY position, field_id", (type_id,)
    ).fetchall()


def record_values(record_id):
    """{field_id: value} for one record."""
    return {
        r["field_id"]: r["value"]
        for r in get_db().execute(
            "SELECT field_id, value FROM record_value WHERE record_id = ?", (record_id,)
        )
    }


def record_label(record_id):
    """A human-readable name for a record: the value of its first field."""
    row = get_db().execute(
        """SELECT rv.value FROM record_value rv
           JOIN field f ON f.field_id = rv.field_id
           WHERE rv.record_id = ? ORDER BY f.position, f.field_id LIMIT 1""",
        (record_id,),
    ).fetchone()
    if row and row["value"]:
        return row["value"]
    return f"Record #{record_id}"


app.jinja_env.globals["record_label"] = record_label


def validate_value(field, raw):
    """Return (cleaned_value, error). Validation is driven by the data type the
    admin picked for the field."""
    raw = (raw or "").strip()

    if not raw:
        if field["is_required"]:
            return None, f"'{field['name']}' is required."
        return "", None

    dt = field["data_type"]
    if dt == "number":
        try:
            float(raw)
        except ValueError:
            return None, f"'{field['name']}' must be a number."
    elif dt == "date":
        try:
            datetime.strptime(raw, "%Y-%m-%d")
        except ValueError:
            return None, f"'{field['name']}' must be a valid date."
    elif dt == "email":
        # Deliberately loose: a full RFC-compliant check is famously
        # impractical, and over-strict patterns reject valid addresses.
        if "@" not in raw or "." not in raw.split("@")[-1]:
            return None, f"'{field['name']}' must be a valid email address."
    elif dt == "boolean":
        return ("Yes" if raw.lower() in ("yes", "on", "true", "1") else "No"), None

    return raw, None


def owned_record(record_id):
    rec = get_db().execute(
        """SELECT r.*, rt.name AS type_name, rt.institution_id
           FROM record r JOIN record_type rt ON rt.type_id = r.type_id
           WHERE r.record_id = ? AND rt.institution_id = ?""",
        (record_id, institution_id()),
    ).fetchone()
    if rec is None:
        abort(404)
    return rec


@app.route("/data/<int:type_id>/records")
@login_required
def record_list(type_id):
    db = get_db()
    rt = owned_record_type(type_id)
    fields = type_fields(type_id)
    q = request.args.get("q", "").strip()

    records = db.execute(
        "SELECT * FROM record WHERE type_id = ? ORDER BY record_id", (type_id,)
    ).fetchall()

    rows = []
    for rec in records:
        vals = record_values(rec["record_id"])
        if q and not any(q.lower() in (vals.get(f["field_id"]) or "").lower() for f in fields):
            continue
        # Key is "vals", not "values": Jinja resolves `row.values` to dict.values
        # (the built-in method) before it looks for a key of that name.
        rows.append({"record": rec, "vals": vals})

    return render_template("record_list.html", record_type=rt, fields=fields,
                           rows=rows, q=q)


@app.route("/data/<int:type_id>/records/add", methods=["GET", "POST"])
@login_required
def record_add(type_id):
    db = get_db()
    rt = owned_record_type(type_id)
    fields = type_fields(type_id)

    if not fields:
        flash("Add at least one field before creating records.", "danger")
        return redirect(url_for("type_detail", type_id=type_id))

    submitted = {}
    if request.method == "POST":
        cleaned, errors = {}, []
        for f in fields:
            raw = request.form.get(f"field_{f['field_id']}", "")
            submitted[f["field_id"]] = raw
            value, err = validate_value(f, raw)
            if err:
                errors.append(err)
            else:
                cleaned[f["field_id"]] = value

        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            cur = db.execute(
                "INSERT INTO record (type_id, created_at) VALUES (?, ?)",
                (type_id, datetime.utcnow().isoformat(timespec="seconds")),
            )
            db.executemany(
                "INSERT INTO record_value (record_id, field_id, value) VALUES (?, ?, ?)",
                [(cur.lastrowid, fid, val) for fid, val in cleaned.items()],
            )
            db.commit()
            flash(f"{rt['name']} record created.", "success")
            return redirect(url_for("record_list", type_id=type_id))

    return render_template("record_form.html", record_type=rt, fields=fields,
                           record=None, values=submitted,
                           form_action=url_for("record_add", type_id=type_id))


@app.route("/data/<int:type_id>/records/<int:record_id>/edit", methods=["GET", "POST"])
@login_required
def record_edit(type_id, record_id):
    db = get_db()
    rt = owned_record_type(type_id)
    rec = owned_record(record_id)
    if rec["type_id"] != rt["type_id"]:
        abort(404)
    fields = type_fields(type_id)

    if request.method == "POST":
        cleaned, errors, submitted = {}, [], {}
        for f in fields:
            raw = request.form.get(f"field_{f['field_id']}", "")
            submitted[f["field_id"]] = raw
            value, err = validate_value(f, raw)
            if err:
                errors.append(err)
            else:
                cleaned[f["field_id"]] = value

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("record_form.html", record_type=rt, fields=fields,
                                   record=rec, values=submitted,
                                   form_action=url_for("record_edit", type_id=type_id,
                                                       record_id=record_id))

        for fid, val in cleaned.items():
            db.execute(
                """INSERT INTO record_value (record_id, field_id, value) VALUES (?, ?, ?)
                   ON CONFLICT(record_id, field_id) DO UPDATE SET value = excluded.value""",
                (record_id, fid, val),
            )
        db.commit()
        flash(f"{rt['name']} record updated.", "success")
        return redirect(url_for("record_list", type_id=type_id))

    return render_template("record_form.html", record_type=rt, fields=fields,
                           record=rec, values=record_values(record_id),
                           form_action=url_for("record_edit", type_id=type_id,
                                               record_id=record_id))


@app.route("/data/<int:type_id>/records/<int:record_id>/delete", methods=["POST"])
@login_required
def record_delete(type_id, record_id):
    db = get_db()
    owned_record_type(type_id)
    owned_record(record_id)
    db.execute("DELETE FROM record WHERE record_id = ?", (record_id,))
    db.commit()
    flash("Record deleted.", "success")
    return redirect(url_for("record_list", type_id=type_id))


@app.route("/data/<int:type_id>/records/<int:record_id>")
@login_required
def record_detail(type_id, record_id):
    db = get_db()
    rt = owned_record_type(type_id)
    rec = owned_record(record_id)
    if rec["type_id"] != rt["type_id"]:
        abort(404)

    fields = type_fields(type_id)
    values = record_values(record_id)

    # Relationships where this record can be the "from" side, plus what it is
    # currently linked to, and what it could still be linked to.
    outgoing = []
    rels = db.execute(
        """SELECT r.*, tt.name AS to_name FROM relationship r
           JOIN record_type tt ON tt.type_id = r.to_type_id
           WHERE r.institution_id = ? AND r.from_type_id = ? ORDER BY r.name""",
        (institution_id(), type_id),
    ).fetchall()
    for rel in rels:
        linked = db.execute(
            """SELECT rec.record_id FROM record_link rl
               JOIN record rec ON rec.record_id = rl.to_record_id
               WHERE rl.rel_id = ? AND rl.from_record_id = ?""",
            (rel["rel_id"], record_id),
        ).fetchall()
        candidates = db.execute(
            "SELECT record_id FROM record WHERE type_id = ? ORDER BY record_id",
            (rel["to_type_id"],),
        ).fetchall()
        linked_ids = {r["record_id"] for r in linked}
        outgoing.append({
            "rel": rel,
            "linked": [r["record_id"] for r in linked],
            "candidates": [r["record_id"] for r in candidates if r["record_id"] not in linked_ids],
        })

    incoming = db.execute(
        """SELECT r.name AS rel_name, r.cardinality, ft.name AS from_name,
                  rl.from_record_id
           FROM record_link rl
           JOIN relationship r ON r.rel_id = rl.rel_id
           JOIN record_type ft ON ft.type_id = r.from_type_id
           WHERE rl.to_record_id = ?""",
        (record_id,),
    ).fetchall()

    return render_template(
        "record_detail.html",
        record_type=rt, record=rec, fields=fields, values=values,
        outgoing=outgoing, incoming=incoming,
        cardinality_labels=CARDINALITY_LABELS,
    )


@app.route("/data/<int:type_id>/records/<int:record_id>/link", methods=["POST"])
@login_required
def record_link_add(type_id, record_id):
    db = get_db()
    owned_record_type(type_id)
    owned_record(record_id)
    rel = owned_relationship(request.form["rel_id"])
    target_id = int(request.form["to_record_id"])
    owned_record(target_id)

    if rel["from_type_id"] != type_id:
        abort(400)

    problem = cardinality_violation(rel, record_id, target_id)
    if problem:
        flash(problem, "danger")
    else:
        db.execute(
            "INSERT OR IGNORE INTO record_link (rel_id, from_record_id, to_record_id) VALUES (?, ?, ?)",
            (rel["rel_id"], record_id, target_id),
        )
        db.commit()
        flash(f"Linked via '{rel['name']}'.", "success")

    return redirect(url_for("record_detail", type_id=type_id, record_id=record_id))


@app.route("/data/<int:type_id>/records/<int:record_id>/unlink", methods=["POST"])
@login_required
def record_link_remove(type_id, record_id):
    db = get_db()
    owned_record_type(type_id)
    owned_record(record_id)
    rel = owned_relationship(request.form["rel_id"])
    db.execute(
        "DELETE FROM record_link WHERE rel_id = ? AND from_record_id = ? AND to_record_id = ?",
        (rel["rel_id"], record_id, request.form["to_record_id"]),
    )
    db.commit()
    flash("Link removed.", "success")
    return redirect(url_for("record_detail", type_id=type_id, record_id=record_id))


# ---------------------------------------------------------------------------
# Template filters
# ---------------------------------------------------------------------------
@app.template_filter("dateformat")
def dateformat(value):
    if not value:
        return "—"
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d %b %Y")
    except ValueError:
        return value


# Stable colours for the seeded departments; anything created later gets a
# colour picked deterministically from the palette, so new departments always
# render a visible badge instead of white-on-white.
DEPT_COLORS = {
    "science": "#2e7d32",
    "technology": "#1565c0",
    "architecture": "#b8860b",
}
_DEPT_PALETTE = [
    "#6a1b9a", "#00838f", "#c62828", "#4e342e",
    "#37474f", "#ad1457", "#558b2f", "#ef6c00",
]


@app.template_filter("dept_color")
def dept_color(name):
    """Return a hex colour for a department name."""
    if not name:
        return "#5a6570"
    key = str(name).strip().lower()
    if key in DEPT_COLORS:
        return DEPT_COLORS[key]
    # sum of code points keeps this stable across restarts, unlike hash()
    return _DEPT_PALETTE[sum(ord(ch) for ch in key) % len(_DEPT_PALETTE)]


@app.template_filter("field_type_label")
def field_type_label(value):
    return FIELD_TYPE_LABELS.get(value, value)


# Create and seed the database on import. A WSGI server such as gunicorn
# imports `app` directly and never executes the __main__ block below, so this
# has to happen here. Both calls are idempotent: init_db uses CREATE TABLE IF
# NOT EXISTS, and seed_db returns early once any institution exists.
init_db()
seed_db()


if __name__ == "__main__":
    # Debug mode is opt-in: set FLASK_DEBUG=1 locally. It must stay off in
    # production, where it would expose an interactive console on errors.
    debug = os.environ.get("FLASK_DEBUG") == "1"
    app.run(debug=debug, host="127.0.0.1", port=5000)

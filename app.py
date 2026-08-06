"""
Faculty Database Management System
Department of Science, Technology & Architecture
------------------------------------------------
A Flask + SQLite web application to manage faculty records:
add / edit / delete / view faculty, search & filter by department
and designation, and assign courses/subjects taught by each faculty
member.
"""

import os
import sqlite3
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash, g

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
# DATABASE_PATH lets the deployment decide where the database lives. On Render's
# free tier the filesystem is ephemeral, so this stays inside the project; once a
# persistent disk is attached, point it at e.g. /var/data/faculty.db instead.
DATABASE = os.environ.get("DATABASE_PATH", os.path.join(BASE_DIR, "faculty.db"))

app = Flask(__name__)
# In production set SECRET_KEY as an environment variable. The fallback below
# exists only so the app still runs out-of-the-box during local development.
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-insecure-key")
app.config["DATABASE"] = DATABASE

DESIGNATIONS = [
    "Professor",
    "Associate Professor",
    "Assistant Professor",
    "Lecturer",
    "Head of Department",
]


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


def init_db():
    db = sqlite3.connect(DATABASE)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS department (
            department_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL UNIQUE,
            code          TEXT NOT NULL UNIQUE,
            description   TEXT
        );

        CREATE TABLE IF NOT EXISTS faculty (
            faculty_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            name            TEXT NOT NULL,
            department_id   INTEGER NOT NULL,
            designation     TEXT NOT NULL,
            email           TEXT UNIQUE,
            phone           TEXT,
            qualification   TEXT,
            specialization  TEXT,
            joining_date    TEXT,
            FOREIGN KEY (department_id) REFERENCES department (department_id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS course (
            course_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            code          TEXT NOT NULL UNIQUE,
            department_id INTEGER NOT NULL,
            FOREIGN KEY (department_id) REFERENCES department (department_id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS faculty_course (
            faculty_id INTEGER NOT NULL,
            course_id  INTEGER NOT NULL,
            PRIMARY KEY (faculty_id, course_id),
            FOREIGN KEY (faculty_id) REFERENCES faculty (faculty_id)
                ON DELETE CASCADE,
            FOREIGN KEY (course_id) REFERENCES course (course_id)
                ON DELETE CASCADE
        );
        """
    )
    db.commit()
    db.close()


def seed_db():
    db = sqlite3.connect(DATABASE)
    db.execute("PRAGMA foreign_keys = ON")
    cur = db.cursor()

    cur.execute("SELECT COUNT(*) FROM department")
    if cur.fetchone()[0] > 0:
        db.close()
        return

    departments = [
        ("Science", "SCI", "Department of Science"),
        ("Technology", "TECH", "Department of Technology"),
        ("Architecture", "ARCH", "Department of Architecture"),
    ]
    cur.executemany(
        "INSERT INTO department (name, code, description) VALUES (?, ?, ?)",
        departments,
    )
    db.commit()

    dept_ids = {row[0]: row[1] for row in cur.execute("SELECT name, department_id FROM department")}

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
        "INSERT INTO course (name, code, department_id) VALUES (?, ?, ?)",
        courses,
    )
    db.commit()

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
           (name, department_id, designation, email, phone, qualification, specialization, joining_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        faculty,
    )
    db.commit()

    fac_ids = {row[0]: row[1] for row in cur.execute("SELECT email, faculty_id FROM faculty")}
    course_ids = {row[0]: row[1] for row in cur.execute("SELECT code, course_id FROM course")}

    assignments = [
        (fac_ids["anjali.rao@univ.edu"], course_ids["SCI101"]),
        (fac_ids["rakesh.menon@univ.edu"], course_ids["SCI205"]),
        (fac_ids["priya.nair@univ.edu"], course_ids["TECH301"]),
        (fac_ids["priya.nair@univ.edu"], course_ids["TECH210"]),
        (fac_ids["suresh.kumar@univ.edu"], course_ids["TECH330"]),
        (fac_ids["meera.iyer@univ.edu"], course_ids["ARCH150"]),
        (fac_ids["vikram.shah@univ.edu"], course_ids["ARCH220"]),
    ]
    cur.executemany(
        "INSERT INTO faculty_course (faculty_id, course_id) VALUES (?, ?)",
        assignments,
    )
    db.commit()
    db.close()


@app.route("/")
def dashboard():
    db = get_db()
    total_faculty = db.execute("SELECT COUNT(*) FROM faculty").fetchone()[0]
    dept_counts = db.execute(
        """SELECT d.department_id, d.name, COUNT(f.faculty_id) AS cnt
           FROM department d LEFT JOIN faculty f ON f.department_id = d.department_id
           GROUP BY d.department_id ORDER BY d.name"""
    ).fetchall()
    total_courses = db.execute("SELECT COUNT(*) FROM course").fetchone()[0]
    return render_template(
        "dashboard.html",
        total_faculty=total_faculty,
        dept_counts=dept_counts,
        total_courses=total_courses,
    )


@app.route("/faculty")
def faculty_list():
    db = get_db()
    departments = db.execute("SELECT * FROM department ORDER BY name").fetchall()

    q = request.args.get("q", "").strip()
    department_id = request.args.get("department_id", "")
    designation = request.args.get("designation", "")

    query = """
        SELECT f.*, d.name AS department_name
        FROM faculty f
        JOIN department d ON d.department_id = f.department_id
        WHERE 1=1
    """
    params = []
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

    faculty_rows = db.execute(query, params).fetchall()

    return render_template(
        "faculty_list.html",
        faculty_rows=faculty_rows,
        departments=departments,
        designations=DESIGNATIONS,
        q=q,
        selected_department=department_id,
        selected_designation=designation,
    )


@app.route("/faculty/<int:faculty_id>")
def faculty_detail(faculty_id):
    db = get_db()
    faculty = db.execute(
        """SELECT f.*, d.name AS department_name
           FROM faculty f JOIN department d ON d.department_id = f.department_id
           WHERE f.faculty_id = ?""",
        (faculty_id,),
    ).fetchone()
    if faculty is None:
        flash("Faculty record not found.", "danger")
        return redirect(url_for("faculty_list"))

    courses = db.execute(
        """SELECT c.* FROM course c
           JOIN faculty_course fc ON fc.course_id = c.course_id
           WHERE fc.faculty_id = ? ORDER BY c.name""",
        (faculty_id,),
    ).fetchall()

    return render_template("faculty_detail.html", faculty=faculty, courses=courses)


@app.route("/faculty/add", methods=["GET", "POST"])
def faculty_add():
    db = get_db()
    departments = db.execute("SELECT * FROM department ORDER BY name").fetchall()
    all_courses = db.execute("SELECT * FROM course ORDER BY name").fetchall()

    if request.method == "POST":
        form = request.form
        try:
            cur = db.execute(
                """INSERT INTO faculty
                   (name, department_id, designation, email, phone, qualification, specialization, joining_date)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    form["name"].strip(),
                    form["department_id"],
                    form["designation"],
                    form.get("email", "").strip() or None,
                    form.get("phone", "").strip(),
                    form.get("qualification", "").strip(),
                    form.get("specialization", "").strip(),
                    form.get("joining_date", "").strip() or None,
                ),
            )
            faculty_id = cur.lastrowid
            course_ids = request.form.getlist("course_ids")
            for cid in course_ids:
                db.execute(
                    "INSERT INTO faculty_course (faculty_id, course_id) VALUES (?, ?)",
                    (faculty_id, cid),
                )
            db.commit()
            flash(f"Faculty '{form['name']}' added successfully.", "success")
            return redirect(url_for("faculty_list"))
        except sqlite3.IntegrityError as e:
            flash(f"Could not save record: {e}", "danger")

    return render_template(
        "faculty_form.html",
        faculty=None,
        departments=departments,
        designations=DESIGNATIONS,
        all_courses=all_courses,
        assigned_course_ids=set(),
        form_action=url_for("faculty_add"),
    )


@app.route("/faculty/<int:faculty_id>/edit", methods=["GET", "POST"])
def faculty_edit(faculty_id):
    db = get_db()
    faculty = db.execute("SELECT * FROM faculty WHERE faculty_id = ?", (faculty_id,)).fetchone()
    if faculty is None:
        flash("Faculty record not found.", "danger")
        return redirect(url_for("faculty_list"))

    departments = db.execute("SELECT * FROM department ORDER BY name").fetchall()
    all_courses = db.execute("SELECT * FROM course ORDER BY name").fetchall()

    if request.method == "POST":
        form = request.form
        try:
            db.execute(
                """UPDATE faculty SET name=?, department_id=?, designation=?, email=?,
                   phone=?, qualification=?, specialization=?, joining_date=?
                   WHERE faculty_id=?""",
                (
                    form["name"].strip(),
                    form["department_id"],
                    form["designation"],
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

    assigned = db.execute(
        "SELECT course_id FROM faculty_course WHERE faculty_id = ?", (faculty_id,)
    ).fetchall()
    assigned_course_ids = {row["course_id"] for row in assigned}

    return render_template(
        "faculty_form.html",
        faculty=faculty,
        departments=departments,
        designations=DESIGNATIONS,
        all_courses=all_courses,
        assigned_course_ids=assigned_course_ids,
        form_action=url_for("faculty_edit", faculty_id=faculty_id),
    )


@app.route("/faculty/<int:faculty_id>/delete", methods=["POST"])
def faculty_delete(faculty_id):
    db = get_db()
    faculty = db.execute("SELECT name FROM faculty WHERE faculty_id = ?", (faculty_id,)).fetchone()
    db.execute("DELETE FROM faculty WHERE faculty_id = ?", (faculty_id,))
    db.commit()
    if faculty:
        flash(f"Faculty '{faculty['name']}' deleted.", "success")
    return redirect(url_for("faculty_list"))


# ---------------------------------------------------------------------------
# Department management
# ---------------------------------------------------------------------------
@app.route("/departments")
def department_list():
    db = get_db()
    departments = db.execute(
        """SELECT d.*,
                  (SELECT COUNT(*) FROM faculty f WHERE f.department_id = d.department_id) AS faculty_count,
                  (SELECT COUNT(*) FROM course c WHERE c.department_id = d.department_id) AS course_count
           FROM department d ORDER BY d.name"""
    ).fetchall()
    return render_template("department_list.html", departments=departments)


@app.route("/departments/add", methods=["GET", "POST"])
def department_add():
    db = get_db()
    if request.method == "POST":
        form = request.form
        try:
            db.execute(
                "INSERT INTO department (name, code, description) VALUES (?, ?, ?)",
                (
                    form["name"].strip(),
                    form["code"].strip().upper(),
                    form.get("description", "").strip(),
                ),
            )
            db.commit()
            flash(f"Department '{form['name']}' added successfully.", "success")
            return redirect(url_for("department_list"))
        except sqlite3.IntegrityError:
            flash("A department with that name or code already exists.", "danger")

    return render_template(
        "department_form.html",
        department=None,
        form_action=url_for("department_add"),
    )


@app.route("/departments/<int:department_id>/edit", methods=["GET", "POST"])
def department_edit(department_id):
    db = get_db()
    department = db.execute(
        "SELECT * FROM department WHERE department_id = ?", (department_id,)
    ).fetchone()
    if department is None:
        flash("Department not found.", "danger")
        return redirect(url_for("department_list"))

    if request.method == "POST":
        form = request.form
        try:
            db.execute(
                "UPDATE department SET name=?, code=?, description=? WHERE department_id=?",
                (
                    form["name"].strip(),
                    form["code"].strip().upper(),
                    form.get("description", "").strip(),
                    department_id,
                ),
            )
            db.commit()
            flash(f"Department '{form['name']}' updated successfully.", "success")
            return redirect(url_for("department_list"))
        except sqlite3.IntegrityError:
            flash("A department with that name or code already exists.", "danger")

    return render_template(
        "department_form.html",
        department=department,
        form_action=url_for("department_edit", department_id=department_id),
    )


@app.route("/departments/<int:department_id>/delete", methods=["POST"])
def department_delete(department_id):
    db = get_db()
    department = db.execute(
        "SELECT name FROM department WHERE department_id = ?", (department_id,)
    ).fetchone()
    if department is None:
        flash("Department not found.", "danger")
        return redirect(url_for("department_list"))

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
# Course management
# ---------------------------------------------------------------------------
@app.route("/courses/add", methods=["GET", "POST"])
def course_add():
    db = get_db()
    departments = db.execute("SELECT * FROM department ORDER BY name").fetchall()

    if request.method == "POST":
        form = request.form
        try:
            db.execute(
                "INSERT INTO course (name, code, department_id) VALUES (?, ?, ?)",
                (
                    form["name"].strip(),
                    form["code"].strip().upper(),
                    form["department_id"],
                ),
            )
            db.commit()
            flash(f"Course '{form['name']}' added successfully.", "success")
            return redirect(url_for("course_list"))
        except sqlite3.IntegrityError:
            flash("A course with that code already exists.", "danger")

    return render_template(
        "course_form.html",
        course=None,
        departments=departments,
        form_action=url_for("course_add"),
    )


@app.route("/courses/<int:course_id>/edit", methods=["GET", "POST"])
def course_edit(course_id):
    db = get_db()
    course = db.execute("SELECT * FROM course WHERE course_id = ?", (course_id,)).fetchone()
    if course is None:
        flash("Course not found.", "danger")
        return redirect(url_for("course_list"))

    departments = db.execute("SELECT * FROM department ORDER BY name").fetchall()

    if request.method == "POST":
        form = request.form
        try:
            db.execute(
                "UPDATE course SET name=?, code=?, department_id=? WHERE course_id=?",
                (
                    form["name"].strip(),
                    form["code"].strip().upper(),
                    form["department_id"],
                    course_id,
                ),
            )
            db.commit()
            flash(f"Course '{form['name']}' updated successfully.", "success")
            return redirect(url_for("course_list"))
        except sqlite3.IntegrityError:
            flash("A course with that code already exists.", "danger")

    return render_template(
        "course_form.html",
        course=course,
        departments=departments,
        form_action=url_for("course_edit", course_id=course_id),
    )


@app.route("/courses/<int:course_id>/delete", methods=["POST"])
def course_delete(course_id):
    db = get_db()
    course = db.execute("SELECT name FROM course WHERE course_id = ?", (course_id,)).fetchone()
    if course is None:
        flash("Course not found.", "danger")
        return redirect(url_for("course_list"))

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


@app.route("/courses")
def course_list():
    db = get_db()
    courses = db.execute(
        """SELECT c.*, d.name AS department_name,
                  (SELECT COUNT(*) FROM faculty_course fc WHERE fc.course_id = c.course_id) AS faculty_count
           FROM course c JOIN department d ON d.department_id = c.department_id
           ORDER BY d.name, c.name"""
    ).fetchall()
    return render_template("course_list.html", courses=courses)


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


@app.template_filter("dateformat")
def dateformat(value):
    if not value:
        return "—"
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d %b %Y")
    except ValueError:
        return value


# Create and seed the database on import. A WSGI server such as gunicorn
# imports `app` directly and never executes the __main__ block below, so this
# has to happen here. Both calls are idempotent: init_db uses CREATE TABLE IF
# NOT EXISTS, and seed_db returns early once any department exists.
init_db()
seed_db()


if __name__ == "__main__":
    # Debug mode is opt-in: set FLASK_DEBUG=1 locally. It must stay off in
    # production, where it would expose an interactive console on errors.
    debug = os.environ.get("FLASK_DEBUG") == "1"
    app.run(debug=debug, host="127.0.0.1", port=5000)

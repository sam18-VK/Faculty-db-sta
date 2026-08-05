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
DATABASE = os.path.join(BASE_DIR, "faculty.db")

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret-key-change-in-production"
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


@app.template_filter("dateformat")
def dateformat(value):
    if not value:
        return "—"
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d %b %Y")
    except ValueError:
        return value


if __name__ == "__main__":
    init_db()
    seed_db()
    app.run(debug=True, host="0.0.0.0", port=5000)

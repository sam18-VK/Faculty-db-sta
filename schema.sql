-- ============================================================
-- Faculty Database Management System
-- Department of Science, Technology & Architecture
-- Schema: SQLite (portable to MySQL with minor type changes)
-- ============================================================

CREATE TABLE department (
    department_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL UNIQUE,
    code          TEXT NOT NULL UNIQUE,
    description   TEXT
);

CREATE TABLE faculty (
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

CREATE TABLE course (
    course_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    code          TEXT NOT NULL UNIQUE,
    department_id INTEGER NOT NULL,
    FOREIGN KEY (department_id) REFERENCES department (department_id)
        ON DELETE CASCADE
);

CREATE TABLE faculty_course (
    faculty_id INTEGER NOT NULL,
    course_id  INTEGER NOT NULL,
    PRIMARY KEY (faculty_id, course_id),
    FOREIGN KEY (faculty_id) REFERENCES faculty (faculty_id)
        ON DELETE CASCADE,
    FOREIGN KEY (course_id) REFERENCES course (course_id)
        ON DELETE CASCADE
);

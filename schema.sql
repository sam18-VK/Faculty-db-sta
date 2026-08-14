-- ============================================================
-- Institutional Database Management System
-- Multi-tenant, metadata-driven schema (SQLite)
--
-- Groups:
--   1. Tenancy & authentication  : institution, admin_user
--   2. Built-in modules          : department, faculty, course, faculty_course
--   3. Admin-defined schema      : record_type, field, relationship
--   4. Admin-defined data (EAV)  : record, record_value, record_link
-- ============================================================
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

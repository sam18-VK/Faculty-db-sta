# Institutional Database Management System (IDMS)

A multi-tenant, metadata-driven web application. Several institutions can use
the same deployment without seeing each other's data, and each institution's
administrator can design new data sets at runtime — choosing their fields and
the cardinality of the relationships between them — without any code changes.

## Features

**Access control**
- Administrator login; passwords stored as PBKDF2 hashes, never plain text
- Every route except sign-in/out requires authentication
- All queries scoped to the signed-in admin's institution, read from the
  session rather than the URL, so data cannot be reached by editing an id

**Built-in modules** (per institution)
- Faculty: add / edit / delete, search by name, email or specialization,
  filter by department and designation
- Departments and Courses: full CRUD
- Referential guards: a department can't be deleted while it holds faculty or
  courses; a course can't be deleted while faculty are assigned to it

**Admin-defined data sets**
- Create new data sets ("Students", "Alumni", "Lab Equipment", …)
- Give each one fields with types: Text, Number, Date, Email, Yes/No, Long text
- Mark fields required; values are validated against their declared type
- List, search, add, edit and delete records through forms generated at
  runtime from the field definitions

**Relationships with enforced cardinality**
- Link two data sets as 1:1, 1:N or M:N
- The chosen cardinality is enforced when records are linked, not merely
  recorded — invalid links are rejected with an explanation

## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000. The database and demo data are created on first run.

### Demo accounts

| Username | Password | Institution |
|---|---|---|
| `admin` | `admin123` | Apex Institute of Science, Technology & Architecture |
| `northadmin` | `north123` | Northfield College |

Sign in as each to confirm neither can see the other's records. **Change these
before any real deployment.**

To enable auto-reload while developing, set `FLASK_DEBUG=1`. Leave it unset in
production — debug mode exposes an interactive console on errors.

### Configuration

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Signs session cookies. **Set this in production.** | insecure dev fallback |
| `DATABASE_PATH` | Where the SQLite file lives. Point at a persistent disk in production. | `./faculty.db` |
| `FLASK_DEBUG` | Set to `1` for auto-reload and tracebacks locally. | off |

## Database design

Twelve tables in four groups — see `schema.sql` for the full DDL.

1. **Tenancy & authentication** — `institution`, `admin_user`
2. **Built-in modules** — `department`, `faculty`, `course`, `faculty_course`
3. **Admin-defined schema (metadata)** — `record_type`, `field`, `relationship`
4. **Admin-defined data** — `record`, `record_value`, `record_link`

### A note on the EAV pattern

User-defined records are stored as Entity-Attribute-Value: `record` holds one
row per record, and `record_value` holds one row per field value rather than
one column per field.

EAV is normally considered an anti-pattern. It gives up column-level type
safety, makes queries more awkward, and performs worse than a native schema.
It is used deliberately here because the schema is authored by the user at
runtime and therefore cannot be declared in advance — the alternative would be
issuing `CREATE TABLE` from user input, which is considerably worse. Type
validation is recovered in the application layer via `validate_value()`.

## Project structure

```
faculty_db_project/
├── app.py                 # Application: schema, routes, auth, validation
├── schema.sql             # Database DDL (reference copy)
├── requirements.txt
├── render.yaml            # Deployment config
├── templates/             # Jinja2 templates (Bootstrap 5)
│   ├── base.html          login.html          dashboard.html
│   ├── faculty_*.html     department_*.html   course_*.html
│   ├── type_*.html        record_*.html       relationship_list.html
└── static/css/style.css
```

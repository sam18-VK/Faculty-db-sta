# Faculty Database Management System
### Department of Science, Technology & Architecture

A Flask + SQLite web application for managing faculty records: add,
edit, delete and search faculty across the Science, Technology and
Architecture departments, and track which courses each faculty
member teaches.

## Features
- Dashboard with faculty/department/course counts
- Full add / edit / delete for **faculty**, **departments** and **courses**
- Search by name, email or specialization
- Filter by department and designation
- Assign multiple courses to each faculty member (many-to-many)
- Referential-integrity guards: a department can't be deleted while it still
  has faculty or courses, and a course can't be deleted while faculty are
  assigned to it

## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000 in your browser. The SQLite database
(`faculty.db`) and sample data are created automatically on first run.

To enable auto-reload while developing, set `FLASK_DEBUG=1` first. Leave it
unset in production — debug mode exposes an interactive console on errors.

### Configuration

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Signs session cookies. **Set this in production.** | insecure dev fallback |
| `FLASK_DEBUG` | Set to `1` for auto-reload and tracebacks locally. | off |

## Project structure
```
faculty_db_project/
├── app.py              # Flask application (routes + DB logic)
├── schema.sql           # Database schema (reference copy)
├── requirements.txt
├── templates/            # Jinja2 HTML templates (Bootstrap 5 UI)
│   ├── base.html
│   ├── dashboard.html
│   ├── faculty_list.html
│   ├── faculty_detail.html
│   ├── faculty_form.html
│   ├── department_list.html
│   ├── department_form.html
│   ├── course_list.html
│   └── course_form.html
└── static/css/style.css
```

## Database schema
See `schema.sql`. Four tables: `department`, `faculty`, `course`,
and the junction table `faculty_course` (many-to-many between
faculty and the courses they teach).

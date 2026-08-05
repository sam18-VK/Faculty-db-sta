# Faculty Database Management System
### Department of Science, Technology & Architecture

A Flask + SQLite web application for managing faculty records: add,
edit, delete and search faculty across the Science, Technology and
Architecture departments, and track which courses each faculty
member teaches.

## Features
- Dashboard with faculty/department/course counts
- Add / edit / delete faculty records
- Search by name, email or specialization
- Filter by department and designation
- Assign multiple courses to each faculty member (many-to-many)
- Course directory showing how many faculty teach each course

## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000 in your browser. The SQLite database
(`faculty.db`) and sample data are created automatically on first run.

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
│   └── course_list.html
└── static/css/style.css
```

## Database schema
See `schema.sql`. Four tables: `department`, `faculty`, `course`,
and the junction table `faculty_course` (many-to-many between
faculty and the courses they teach).

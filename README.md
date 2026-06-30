# الطبيب الحافظ — Al-Tabib Al-Hafez

A full-featured web application for managing **Quran memorization (hifdh) circles**. Designed for Islamic educational institutions to streamline administrative, pedagogical, and reporting workflows.

## Roles

- **Admin** — Full system oversight
- **Supervisor** — Monitor circles, teachers, and students
- **Teacher** — Manage sessions, attendance, evaluations, and memorization reviews
- **Student** — Track progress, submit review requests, view attendance

## Features

- Circle (halaqa) creation, scheduling, and enrollment
- Session attendance tracking with justification workflows
- Memorization review and recitation request system
- Student evaluation and exam management with multi-criteria grading
- Verse-by-verse progress tracking
- Certificate generation with unique serial numbers (PDF)
- Real-time notifications via WebSockets
- Internal messaging system
- Announcements broadcasting
- Comprehensive reports and analytics
- REST API with JWT authentication (OpenAPI/Swagger docs)
- QR-code-enabled student identity cards
- Teacher absence and substitution management

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Django 5.1 LTS |
| API | Django REST Framework 3.17, SimpleJWT |
| Real-time | Django Channels, Redis |
| Async Tasks | Celery + Redis + Celery Beat |
| Database | PostgreSQL 16 |
| Frontend | Django Templates, HTMX, Tailwind CSS |
| PDF | fpdf2 |
| Containerization | Docker, Docker Compose |
| Reverse Proxy | nginx |
| WSGI/ASGI | Gunicorn + Uvicorn |

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL 16 (or SQLite for local dev)
- Redis

### Local Development

```bash
# Clone the repo
git clone https://github.com/HAROUNTOUM/quran.git
cd quran

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements/local.txt

# Copy environment variables
cp .env.example .env

# Run migrations
python manage.py migrate

# Seed initial data
python manage.py seed_data

# Start the development server
python manage.py runserver
```

### Docker Deployment

```bash
docker compose up -d
```

## Project Structure

```
apps/
├── accounts/       # Custom user model, roles, student cards
├── announcements/  # Announcements broadcasting
├── api/            # REST API routing
├── attendance/     # Session attendance tracking
├── certificates/   # PDF certificate generation
├── circles/        # Halaqa circles, enrollment, sessions
├── core/           # Base models and shared utilities
├── exams/          # Exam creation and grading
├── lessons/        # Lesson plans
├── memorization/   # Review requests, progress tracking
├── messaging/      # Internal messaging
├── notifications/  # Real-time notifications
├── references/     # Quranic references (Surahs, Ayahs)
├── reports/        # Reporting module
└── requests/       # General request workflows
config/             # Django settings (base/local/production)
templates/          # Server-side rendered templates
requirements/       # Python dependencies
nginx/              # nginx configuration
```

## Environment Variables

Key environment variables (see `.env.example`):

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `SECRET_KEY` | Django secret key |
| `REDIS_URL` | Redis connection string |
| `EMAIL_HOST_USER` | SMTP username |
| `EMAIL_HOST_PASSWORD` | SMTP password |

## License

MIT

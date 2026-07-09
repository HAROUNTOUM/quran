<p align="center">
  <h1 align="center">الطبيب الحافظ — Al-Tabib Al-Hafez</h1>
  <p align="center">A comprehensive platform for managing Quran memorization (Hifdh) circles in Islamic educational institutions.</p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12%2B-blue" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/Django-5.1%20LTS-green" alt="Django 5.1 LTS">
  <img src="https://img.shields.io/badge/PostgreSQL-16-blue" alt="PostgreSQL 16">
  <img src="https://img.shields.io/badge/License-MIT-yellow" alt="License MIT">
  <img src="https://img.shields.io/badge/status-production%20ready-brightgreen" alt="Production Ready">
</p>

---

## Overview

Al-Tabib Al-Hafez is a full-featured web application designed to streamline the administrative, pedagogical, and reporting workflows of Quran memorization programs. Built with a role-based multi-tenant architecture, it serves admins, supervisors, teachers, and students through a unified platform.

### The Problem

Quran memorization centers often struggle with fragmented tools — spreadsheets for attendance, paper-based progress tracking, and manual certificate generation. This leads to administrative overhead, data loss, and limited visibility into student progress.

### The Solution

A centralized, digital platform that automates attendance, tracks verse-by-verse memorization progress, generates certificates, provides real-time analytics, and gives each stakeholder the tools they need in one place.

---

## Key Features

| Domain | Features |
|--------|----------|
| **Circles (Halaqat)** | Create, schedule, and manage enrollment for memorization circles |
| **Attendance** | Session tracking with justification workflows and automated reporting |
| **Memorization** | Verse-by-verse progress tracking for new Hifdh and Murajaa (revision) |
| **Exams & Evaluation** | Multi-criteria grading with detailed performance analytics |
| **Certificates** | Automated PDF generation with unique serial numbers per student |
| **Real-time** | WebSocket-powered notifications and messaging |
| **Analytics** | Comprehensive dashboards, reports, and leaderboards |
| **API** | Full REST API with JWT auth and OpenAPI/Swagger documentation |
| **Identity** | QR-code-enabled student identity cards |
| **Substitutions** | Teacher absence and substitution management |

---

## Roles

| Role | Capabilities |
|------|-------------|
| **Admin** | Full system oversight, configuration, and user management |
| **Supervisor** | Monitor circles, teachers, and students across the institution |
| **Teacher** | Manage sessions, attendance, evaluations, and memorization reviews |
| **Student** | Track progress, submit review requests, view attendance and grades |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Django 5.1 LTS |
| **API** | Django REST Framework 3.17, SimpleJWT |
| **Real-time** | Django Channels, Redis |
| **Background Tasks** | Celery + Redis + Celery Beat |
| **Database** | PostgreSQL 16 |
| **Frontend** | Django Templates, HTMX, Tailwind CSS |
| **PDF Generation** | fpdf2 |
| **Containerization** | Docker, Docker Compose |
| **Reverse Proxy** | nginx |
| **ASGI / WSGI** | Uvicorn + Gunicorn |

---

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL 16 (SQLite works for local development)
- Redis

### Local Development

```bash
# Clone the repository
git clone https://github.com/HAROUNTOUM/quran.git
cd quran

# Set up a virtual environment
python3 -m venv .venv && source .venv/bin/activate

# Install dependencies
pip install -r requirements/local.txt

# Configure environment
cp .env.example .env

# Initialize the database
python manage.py migrate

# Seed demo data
python manage.py seed_data

# Run the server
python manage.py runserver
```

### Docker Deployment

```bash
docker compose up -d
```

---

## Architecture

The project follows a modular Django app structure, keeping each domain isolated and maintainable:

```
apps/
├── accounts/         # Custom user model, roles, student cards
├── announcements/    # Broadcasting and announcements
├── api/              # REST API routing and versioning
├── attendance/       # Session attendance and justifications
├── certificates/     # PDF certificate generation
├── circles/          # Halaqa management, enrollment, sessions
├── core/             # Base models, shared utilities
├── exams/            # Exam creation and grading
├── lessons/          # Lesson planning
├── memorization/     # Hifdh and Murajaa tracking
├── messaging/        # Internal communication
├── notifications/    # Real-time WebSocket notifications
├── references/       # Quranic data (Surahs, Ayahs)
├── reports/          # Analytics and reporting
└── requests/         # General request workflows
```

---

## API Overview

The platform exposes a comprehensive REST API at `/api/v1/` with interactive documentation at `/api/v1/docs/` (Swagger).

**Authentication:** JWT-based (access + refresh tokens via SimpleJWT)

**Key endpoints:**

| Resource | Endpoints | Description |
|----------|-----------|-------------|
| Auth | `POST /auth/login/`, `/auth/refresh/`, `/auth/me/` | Authentication & profile |
| Circles | `GET/POST /circles/`, `/circles/{id}/enroll/` | Circle management |
| Sessions | `GET/POST /sessions/`, `/sessions/{id}/attendance/` | Session management |
| Memorization | `GET/POST /memorization-progress/`, `/review-requests/` | Progress tracking |
| Exams | `GET /exams/`, `/exams/{id}/marks/` | Exam results |
| Certificates | `GET /certificates/`, `/certificates/{id}/` | Certificate management |
| Notifications | `GET /notifications/`, `/notifications/{id}/read/` | Real-time notifications |

---

## Student Mobile Interface

The platform includes a 5-tab student dashboard designed for both web and mobile:

| Tab | Description |
|-----|-------------|
| **الرئيسية** (Home) | Dashboard with stats, alerts, quick actions, announcements |
| **المذاكرة** (Memorization) | Hifdh progress, Murajaa progress, review requests, weekly goals |
| **الحصص** (Sessions) | Schedule, attendance, classroom, justifications |
| **الحلقات** (Circles) | Enrolled circles, enrollment, leaderboards, exams |
| **المزيد** (More) | Support, announcements, notifications, webinars, certificates, profile |

---

## Deployment

The project is fully containerized and ready for production deployment:

```bash
# Build and start all services
docker compose up -d --build

# Run migrations on the production database
docker compose exec web python manage.py migrate

# Collect static files
docker compose exec web python manage.py collectstatic --noinput

# Create a superuser
docker compose exec web python manage.py createsuperuser
```

Environment variables are managed through `.env` (see `.env.example` for all options).

---

## Roadmap

- [x] Core circle and session management
- [x] Attendance tracking with justifications
- [x] Memorization progress tracking
- [x] Exam and evaluation system
- [x] PDF certificate generation
- [x] Real-time notifications (WebSockets)
- [x] REST API with Swagger docs
- [x] QR-code student identity cards
- [x] Docker containerization
- [x] Teacher substitution management
- [ ] Internationalization (i18n) — Arabic / English / French
- [ ] Mobile application (Flutter)
- [ ] Voice-based memorization assessment
- [ ] AI-powered progress insights
- [ ] Gamification and achievement badges

---

## Contributing

Contributions are welcome. Please open an issue first to discuss your proposed changes.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes (`git commit -m 'feat: add your feature'`)
4. Push to the branch (`git push origin feature/your-feature`)
5. Open a Pull Request

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

## Contact

- **Repository:** [github.com/HAROUNTOUM/quran](https://github.com/HAROUNTOUM/quran)
- **Issues:** [github.com/HAROUNTOUM/quran/issues](https://github.com/HAROUNTOUM/quran/issues)

Built with care for Quran memorization communities worldwide.

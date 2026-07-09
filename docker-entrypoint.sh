#!/bin/sh
set -e

echo "Running database migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput --clear

echo "Creating/ensuring admin user..."
python manage.py shell <<EOF
from apps.accounts.models import User
admin, created = User.objects.get_or_create(
    email="admin@hafez.com",
    defaults=dict(
        username="admin@hafez.com",
        role=User.Role.MAIN_ADMIN,
        is_approved=User.ApprovalStatus.APPROVED,
        is_active=True,
        is_staff=True,
        is_superuser=True,
        full_name_ar="مدير النظام",
    ),
)
if created:
    admin.set_password(__import__('os').environ.get('ADMIN_PASSWORD', 'admin123'))
    admin.save()
    print("Admin user created")
else:
    admin.is_approved = User.ApprovalStatus.APPROVED
    admin.is_active = True
    admin.is_staff = True
    admin.is_superuser = True
    admin.save()
    print("Admin user updated")
EOF

echo "Creating teacher/student test accounts..."
python manage.py shell <<EOF
from apps.accounts.models import User

PASS = __import__('os').environ.get('ADMIN_PASSWORD', 'admin123')

teacher, _ = User.objects.get_or_create(
    email="teacher1@hafez.com",
    defaults=dict(
        username="teacher1@hafez.com",
        role=User.Role.TEACHER,
        is_approved=User.ApprovalStatus.APPROVED,
        is_active=True,
        full_name_ar="سعيد المعلم",
    ),
)
teacher.set_password(PASS)
teacher.save()

student, _ = User.objects.get_or_create(
    email="student1@hafez.com",
    defaults=dict(
        username="student1@hafez.com",
        role=User.Role.STUDENT,
        is_approved=User.ApprovalStatus.APPROVED,
        is_active=True,
        full_name_ar="محمد الطالب",
    ),
)
student.set_password(PASS)
student.save()
print("Test accounts ready")
EOF

# Optional demo seed for real-use testing. Enabled by setting SEED_DEMO_DATA=true
# in the service env. Both commands are idempotent (get_or_create / upsert), so a
# redeploy re-runs them harmlessly and keeps the shared test password stable.
if [ "$SEED_DEMO_DATA" = "true" ]; then
  echo "SEED_DEMO_DATA=true → seeding Quran reference data..."
  python manage.py seed_quran
  python manage.py seed_thumns
  echo "Seeding demo accounts, circles, sessions and attendance..."
  python manage.py seed_data
  echo "Seeding reports data (hifz, murajaa, grades)..."
  python manage.py seed_reports_data
  echo "Seeding certificate test data..."
  python manage.py seed_cert_test_data
  echo "Seeding comprehensive data (private sessions, webinars, chat, requests)..."
  python manage.py seed_comprehensive
  echo "Demo data seeded (all accounts share password: test1234)."
fi

exec "$@"

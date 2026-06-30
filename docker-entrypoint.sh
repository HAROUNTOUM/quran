#!/bin/sh
set -e

echo "Running database migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput --clear

echo "Creating admin user if not exists..."
python manage.py shell <<EOF
from apps.accounts.models import User
if not User.objects.filter(role=User.Role.ADMIN).exists():
    User.objects.create_superuser(
        email="admin@hafez.com",
        password=__import__('os').environ.get('ADMIN_PASSWORD', 'admin123'),
        full_name_ar="مدير النظام",
        role=User.Role.ADMIN,
    )
    print("Admin user created")
else:
    print("Admin user already exists")
EOF

exec "$@"

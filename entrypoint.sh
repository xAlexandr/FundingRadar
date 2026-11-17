#!/bin/sh

echo "⏳ Ждём, пока БД станет доступна..."

# Ждём БД на хосте db, порту 5432
while ! nc -z $DB_HOST $DB_PORT; do
  sleep 0.5
done

echo "✅ База данных доступна. Запускаем миграции..."

# Можно создать суперпользователя автоматически (необязательно)
# echo "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.create_superuser('admin', 'admin@example.com', 'adminpass')" | python manage.py shell
echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "🚀 Запускаем Django..."
exec "$@"
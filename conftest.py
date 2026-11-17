import os
import sys
from pathlib import Path

# Set environment variables BEFORE Django setup
os.environ['DJANGO_SECRET_KEY'] = 'test-secret-key-for-testing-only'
os.environ['DJANGO_SETTINGS_MODULE'] = 'funding_web.settings'
os.environ.setdefault('DEBUG', 'True')
os.environ.setdefault('REDIS_HOST', 'localhost')
os.environ.setdefault('REDIS_PORT', '6379')
os.environ.setdefault('MYSQL_HOST', 'localhost')
os.environ.setdefault('DB_HOST', 'localhost')
os.environ.setdefault('FILTER_HOST', 'localhost')

# Ensure project root is on path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import django
django.setup()

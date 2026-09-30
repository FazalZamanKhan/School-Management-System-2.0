import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.test')
import django
django.setup()
from django.db import connection
cursor = connection.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%roleassignment%'")
for row in cursor.fetchall():
    print('Table:', row[0])
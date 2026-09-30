import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.test')
import django
django.setup()
from django.db import connection
cursor = connection.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='accounts_roleassignment'")
print('Table exists:', cursor.fetchone())
cursor.execute("SELECT sql FROM sqlite_master WHERE name='accounts_roleassignment'")
row = cursor.fetchone()
if row:
    print('Schema:', row[0])
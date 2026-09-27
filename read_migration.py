import os

# Read the frostfire password reset migration
path = 'backend/apps/accounts/migrations/0033_reset_frostfire_password.py'
with open(path, 'r', errors='ignore') as f:
    content = f.read()
    print(content)
import os

path = 'backend/apps/accounts/serializers.py'
with open(path, 'r', errors='ignore') as f:
    content = f.read()

# Check if the fix is present
if 'Platform Super Admin found' in content:
    print('Fix PRESENT: Platform Super Admin exception added')
else:
    print('Fix ABSENT: Platform Super Admin exception not found')
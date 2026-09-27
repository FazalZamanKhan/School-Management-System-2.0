import os

# Inspect the serializers.py file around line 730
path = 'backend/apps/accounts/serializers.py'
with open(path, 'r', errors='ignore') as f:
    lines = f.readlines()
    print('=== backend/apps/accounts/serializers.py around line 730 ===')
    for i in range(720, min(750, len(lines))):
        print(f'{i}: {lines[i-1]}', end='')
    print()

# Inspect the views.py file around line 136
path = 'backend/apps/accounts/views.py'
with open(path, 'r', errors='ignore') as f:
    lines = f.readlines()
    print('=== backend/apps/accounts/views.py around line 136 ===')
    for i in range(120, min(160, len(lines))):
        print(f'{i}: {lines[i-1]}', end='')
    print()
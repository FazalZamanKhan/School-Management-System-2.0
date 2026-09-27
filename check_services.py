import os

# Check the services file for login_candidate_count
path = 'backend/apps/accounts/services.py'
with open(path, 'r', errors='ignore') as f:
    content = f.read()
    # Find login_candidate_count
    lines = content.split('\n')
    for i, line in enumerate(lines, 1):
        if 'login_candidate_count' in line:
            # Print surrounding context
            start = max(0, i-5)
            end = min(len(lines), i+15)
            for j in range(start, end):
                print(f'{j}: {lines[j]}', end='')
            print('\n---\n')
            
# Also check models
path = 'backend/apps/accounts/models.py'
with open(path, 'r', errors='ignore') as f:
    content = f.read()
    lines = content.split('\n')
    for i, line in enumerate(lines, 1):
        if 'FrostFire' in line or 'is_superuser' in line or 'Role' in line or 'institution' in line:
            print(f'Line {i}: {line[:200]}')
            if i > 1 and i < len(lines):
                pass  # just print first match
import os

# Read the serializers.py login section
path = 'backend/apps/accounts/serializers.py'
with open(path, 'r', errors='ignore') as f:
    content = f.read()
    
# Find the LoginSerializer class and the relevant section
lines = content.split('\n')
for i, line in enumerate(lines, 1):
    if 'class LoginSerializer' in line:
        print(f'Found LoginSerializer at line {i}')
        # Print from this class until we hit another class or end
        for j in range(i, min(i+150, len(lines))):
            print(f'{j}: {lines[j-1]}')
            # Stop after we've printed enough lines or hit a new class
            if j > i + 100:
                break
        break
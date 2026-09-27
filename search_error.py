import os

# Search for the error message in the codebase
print("=" * 60)
print("SEARCHING FOR 'shared by multiple accounts' ERROR MESSAGE")
print("=" * 60)

found = 0
for root, dirs, files in os.walk('backend'):
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            try:
                with open(path, 'r', errors='ignore') as fh:
                    content = fh.read()
                    if 'shared' in content.lower() and 'multiple' in content.lower():
                        found += 1
                        print(f'\nFOUND in: {path}')
                        lines = content.split('\n')
                        for i, line in enumerate(lines, 1):
                            if 'shared' in line.lower() and ('multiple' in line.lower() or 'ambiguous' in line.lower()):
                                print(f'  Line {i}: {line[:300]}')
            except Exception as e:
                pass

if found == 0:
    print('\nNo matches found for "shared by multiple accounts"')

print('\n' + '=' * 60)
print("SEARCHING FOR 'school_code' + 'login' LOGIC")
print("=" * 60)

# Search for LoginView or login handling
for root, dirs, files in os.walk('backend/apps/accounts'):
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            try:
                with open(path, 'r', errors='ignore') as fh:
                    content = fh.read()
                    if 'LoginView' in content or 'def post' in content:
                        print(f'\nFOUND in: {path}')
                        lines = content.split('\n')
                        for i, line in enumerate(lines, 1):
                            if 'school_code' in line.lower() and i > 100 and i < 250:
                                print(f'  Line {i}: {line[:200]}')
            except:
                pass
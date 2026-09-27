import os

# Search for FrostFire in the codebase
print("=" * 60)
print("SEARCHING FOR 'FrostFire' IN CODEBASE")
print("=" * 60)

found = 0
for root, dirs, files in os.walk('backend'):
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            try:
                with open(path, 'r', errors='ignore') as fh:
                    content = fh.read()
                    if 'FrostFire' in content:
                        found += 1
                        print(f'\nFOUND in: {path}')
                        lines = content.split('\n')
                        for i, line in enumerate(lines, 1):
                            if 'FrostFire' in line:
                                print(f'  Line {i}: {line[:200]}')
            except:
                pass

if found == 0:
    print('\nNo matches found for "FrostFire" in backend/')

# Also search in frontend
print('\n' + '=' * 60)
print('SEARCHING FOR FrostFire IN FRONTEND')
print('=' * 60)
for root, dirs, files in os.walk('frontend'):
    for f in files:
        if f.endswith('.js') or f.endswith('.jsx') or f.endswith('.jsx'):
            path = os.path.join(root, f)
            try:
                with open(path, 'r', errors='ignore') as fh:
                    content = fh.read()
                    if 'FrostFire' in content:
                        found += 1
                        print(f'\nFOUND in: {path}')
                        lines = content.split('\n')
                        for i, line in enumerate(lines, 1):
                            if 'FrostFire' in line:
                                print(f'  Line {i}: {line[:200]}')
            except:
                pass

if found == 0:
    print('\nNo matches found for "FrostFire" in frontend/')
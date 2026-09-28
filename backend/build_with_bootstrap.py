#!/usr/bin/env python
"""Build script that conditionally runs ensure_superuser before normal build."""

import os
import subprocess
import sys


def run_command(cmd, description, cwd=None):
    """Run a command and return success status."""
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    if cwd:
        print(f"Working directory: {cwd}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        print(f"FAILED: {description} (exit code {result.returncode})")
        return False
    print(f"SUCCESS: {description}")
    return True


def main():
    # Get the backend directory
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Check if bootstrap is explicitly enabled
    bootstrap_enabled = os.environ.get("DJANGO_BOOTSTRAP_SUPERUSER") == "1"
    
    # Always run collectstatic
    steps = [
        (["python", "manage.py", "collectstatic", "--noinput"], "Collect static files"),
    ]
    
    # Conditionally add bootstrap step
    if bootstrap_enabled:
        print("BOOTSTRAP MODE ENABLED: DJANGO_BOOTSTRAP_SUPERUSER=1")
        # Insert bootstrap before other steps
        steps.insert(0, (["python", "manage.py", "ensure_superuser"], "Super Admin bootstrap"))
    else:
        print("BOOTSTRAP MODE DISABLED: DJANGO_BOOTSTRAP_SUPERUSER != 1 (or unset)")
    
    # Execute all steps
    for cmd, desc in steps:
        if not run_command(cmd, desc, cwd=backend_dir):
            sys.exit(1)
    
    # Print version info
    version = os.environ.get("BUILD_VERSION", "unknown")
    print(f"BUILD_VERSION={version}")
    
    print("Build completed successfully")


if __name__ == "__main__":
    main()
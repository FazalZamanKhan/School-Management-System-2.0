"""Test settings with PostgreSQL for CI and database-specific checks."""

from .test import *  # noqa: F401,F403
from .base import DATABASES as POSTGRES_DATABASES

DATABASES = POSTGRES_DATABASES

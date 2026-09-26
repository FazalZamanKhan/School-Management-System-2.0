# Generated migration to reset FrostFire Super Admin password
# Reads new password from DJANGO_SUPERUSER_PASSWORD environment variable

from django.db import migrations
import os
from django.contrib.auth.hashers import make_password


def reset_frostfire_password(apps, schema_editor):
    """Reset FrostFire Super Admin password from environment variable."""
    # Only run if the environment variable is set
    new_password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')
    if not new_password:
        # No password provided in environment, skip
        return

    User = apps.get_model('accounts', 'User')
    try:
        # Filter by is_superuser=True to get the correct FrostFire (Platform Super Admin)
        user = User.objects.get(username='FrostFire', is_superuser=True)
        user.password = make_password(new_password)
        user.must_change_password = False
        user.save(update_fields=['password', 'must_change_password'])
    except User.DoesNotExist:
        # FrostFire Super Admin doesn't exist, skip
        pass
    except User.MultipleObjectsReturned:
        # Multiple FrostFire users exist, get the one that is a superuser
        user = User.objects.filter(username='FrostFire', is_superuser=True).first()
        if user:
            user.password = make_password(new_password)
            user.must_change_password = False
            user.save(update_fields=['password', 'must_change_password'])


def reverse_frostfire_password(apps, schema_editor):
    """No reverse operation - password reset is one-way."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0028_remove_roleassignment_unique_role_per_membership_and_more'),
    ]

    operations = [
        migrations.RunPython(reset_frostfire_password, reverse_frostfire_password),
    ]
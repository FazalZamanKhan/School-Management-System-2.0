# PHASE 152A — FIX IMPLEMENTATION

## Fix Location

`backend/apps/accounts/serializers.py` — `LoginSerializer.validate()` method, lines 721-738

## The Problem

When a user attempts to log in without providing `school_code`, and the username/email exists in multiple institutions (`login_candidate_count > 1`), the system unconditionally raises:

> "This username or email is shared by multiple accounts in different schools. Provide your school_code to log in."

This correctly protects School Admin accounts, but incorrectly also blocks Platform Super Admin (`FrostFire`) accounts from global authentication.

## The Fix

Add a Platform Super Admin exception: when `candidate_count > 1` and no `school_code`, first check if there's a `is_superuser=True` account with this identifier. If so, attempt authentication globally (password check). If authentication succeeds, allow it. If not, show "Invalid credentials." If no superuser exists with this username, show the shared-username error.

## Code Change

**Before** (lines 721-738):
```python
else:
    # Unscoped login (platform root / localhost, no school_code): refuse
    # ambiguity. A username shared by several schools must be logged in
    # with its school_code.
    candidate_count = login_candidate_count(identifier)
    if candidate_count == 0:
        user = None
    elif candidate_count > 1:
        raise serializers.ValidationError(
            "This username or email is shared by multiple accounts in "
            "different schools. Provide your school_code to log in."
        )
    else:
        user = authenticate(
            request=request,
            username=identifier,
            password=attrs.get("password"),
        )
```

**After**:
```python
else:
    # Unscoped login (platform root / localhost, no school_code): refuse
    # ambiguity. A username shared by several schools must be logged in
    # with its school_code — EXCEPT for Platform Super Admin accounts,
    # which authenticate globally.
    candidate_count = login_candidate_count(identifier)
    
    if candidate_count > 1:
        # Check if there's a Platform Super Admin with this username
        # who should authenticate globally without school_code
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import User
        super_user = User.objects.filter(username=identifier, is_superuser=True).first()
        
        if super_user is not None:
            # Platform Super Admin found — attempt authentication globally
            # (will check password; succeeds only with correct password)
            user = authenticate(
                request=request,
                username=identifier,
                password=attrs.get("password"),
            )
            if user is None:
                # Super Admin exists but password is incorrect
                raise serializers.ValidationError(
                    "Invalid credentials."
                )
        else:
            # No Super Admin with this username: shared username error
            raise serializers.ValidationError(
                "This username or email is shared by multiple accounts in "
                "different schools. Provide your school_code to log in."
            )
    else:
        user = authenticate(
            request=request,
            username=identifier,
            password=attrs.get("password"),
        )
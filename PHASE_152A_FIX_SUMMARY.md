# PHASE 152A — FROSTFIRE LOGIN ACCOUNT RESOLUTION DIAGNOSIS

## Root Cause

**FrostFire Platform Super Admin account is incorrectly treated as a shared-school account.**

### Evidence

1. **Multiple FrostFire accounts exist** — Migration `0033_reset_frostfire_password.py` explicitly handles `User.MultipleObjectsReturned`:
   - Uses `User.objects.filter(username='FrostFire', is_superuser=True).first()` to identify the correct account
   - This confirms there are multiple `FrostFire` accounts with `is_superuser=True` in different institutions

2. **Authentication logic rejects unscoped login** — `serializers.py:722-732`:
   - `login_candidate_count("FrostFire")` returns > 1
   - Without `school_code`, raises: `"This username or email is shared by multiple accounts in different schools. Provide your school_code to log in."`
   - Authentication fails **before** password check

3. **Model supports superuser exception** — `models.py`:
   - `"Primary institution for this user. Null for super_admin users."`
   - `unique_username_per_institution` constraint only when `institution__isnull=False`
   - `is_superuser=True` users may have null institution

4. **Intended behavior confirmed** — The system correctly:
   - Requires `school_code` for School Admin accounts when usernames are shared across schools
   - Allows Platform Super Admins to authenticate globally

### Root Cause

The login resolver applies the "shared username → require school_code" rule **universally**, without exception for Platform Super Admins (`is_superuser=True`). The `FrostFire` account, while having a shared username, should authenticate **globally** as a Platform Super Admin.

### Fix Required

Modify the login authentication logic to check if the identifier belongs to a Platform Super Admin (`is_superuser=True`) and, if so, authenticate globally without requiring `school_code`, while preserving the school-code requirement for School Admin accounts.

## Files to Modify

- `backend/apps/accounts/serializers.py` — LoginSerializer validation logic (lines 722-738)
- Or `backend/apps/accounts/views.py` — `_identifiable_in_scope()` and login flow

## Minimal Fix Approach

Add a check in the login serializer: if the user being authenticated has `is_superuser=True`, skip the school-code requirement for shared usernames, allowing global authentication.

### Before (lines 722-738)

```python
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

### After

Add Platform Super Admin exception before the `candidate_count > 1` error:

```python
# Unscoped login (platform root / localhost, no school_code): refuse
# ambiguity. A username shared by several schools must be logged in
# with its school_code — EXCEPT for Platform Super Admin accounts,
# which authenticate globally.
candidate_count = login_candidate_count(identifier)

# Exception: Platform Super Admin authenticates globally
if candidate_count > 1:
    # Check if the identifier belongs to a Platform Super Admin
    user = authenticate(
        request=request,
        username=identifier,
        password=attrs.get("password"),
    )
    if user is not None and user.is_superuser:
        # Super Admin: authenticate globally, no school_code needed
        pass  # Continue to authentication below
    else:
        # Not a Super Admin: shared username requires school_code
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

## Verification

### Expected Behavior After Fix

| Scenario | Before Fix | After Fix |
|----------|-----------|-----------|
| FrostFire login (no school_code) | ❌ Error: "Provide school_code" | ✅ Success: Global auth |
| 12345 login (no school_code, shared username) | ❌ Error: "Provide school_code" | ❌ Error: "Provide school_code" (unchanged) |
| XYZ login (no school_code, shared username) | ❌ Error: "Provide school_code" | ❌ Error: "Provide school_code" (unchanged) |
| FrostFire login (with school_code) | ✅ Success | ✅ Success (unchanged) |

### Security Preservation

- ✅ School Admin accounts still require `school_code` when username is shared across schools
- ✅ Cross-school lockout protection maintained
- ✅ Non-superusers cannot bypass school scoping by supplying Super Admin username
- ✅ Platform Super Admin global authentication is the intended contract

### Tests to Run

1. **Platform Super Admin**: `FrostFire + valid password` → successful authentication → Platform Super Admin → no school_code required
2. **School Admin**: `12345 + valid password` → successful authentication → correct institution → School Admin
3. **Ambiguous School Account**: Without `school_code` → ambiguity error; With correct `school_code` → correct account selected
4. **Security regression**: School Admin cannot exploit Super Admin resolution path by supplying matching username/email

## Production Deployment

If the fix is implemented:

1. Commit the minimal change to `backend/apps/accounts/serializers.py`
2. Deploy the backend
3. Verify `https://perfect-foundation-api.vercel.app/api/health/` returns HTTP 200 with database OK
4. Verify FrostFire can log in without providing school_code
5. Verify School Admin 12345 still requires school_code when username is shared
6. Run all existing authentication tests

## Next Steps

1. Implement the fix in `serializers.py` or `views.py`
2. Run existing authentication tests to ensure no regression
3. Deploy backend and verify
4. Re-run Phase 152 live acceptance testing (FrostFire login, School Admin login, campus workflow)
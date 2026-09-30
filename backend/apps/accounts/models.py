from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.core.models import SoftDeleteMixin, SoftDeleteManager
from apps.schools.models import School


class Role(models.TextChoices):
    SUPER_ADMIN = "super_admin", "Platform Super Admin"
    ADMIN = "admin", "Institution Admin"
    ORG_ADMIN = "org_admin", "Organization Administrator"
    HEAD_OFFICE = "head_office", "Head Office"
    PRINCIPAL = "principal", "Principal"
    VICE_PRINCIPAL = "vice_principal", "Vice Principal"
    CAMPUS_ADMIN = "campus_admin", "Campus Administrator"
    ACADEMIC = "academic", "Academic Administrator"
    COUNSELLOR = "counsellor", "Counsellor / Student Counselor"
    ACCOUNTANT = "accountant", "Accountant"
    HR = "hr", "HR / Staff Officer"
    RECEPTIONIST = "receptionist", "Receptionist"
    ADMINISTRATIVE_OFFICER = "administrative_officer", "Administrative Officer"
    LIBRARIAN = "librarian", "Librarian"
    GUARD = "guard", "Security Guard"
    NURSE = "nurse", "Nurse / Medical Officer"
    TEACHER = "teacher", "Teacher"
    PARENT = "parent", "Parent / Guardian"
    STUDENT = "student", "Student"
    STAFF = "staff", "Staff Member"


# Canonical role hierarchy (higher = more privilege). Used to prevent role
# escalation: a user may only manage roles ranked strictly below their own.
ROLE_RANK = {
    Role.SUPER_ADMIN: 100,
    Role.ORG_ADMIN: 90,
    Role.HEAD_OFFICE: 85,
    Role.ADMIN: 80,
    Role.PRINCIPAL: 70,
    Role.VICE_PRINCIPAL: 65,
    Role.CAMPUS_ADMIN: 60,
    Role.ACADEMIC: 55,
    Role.ACCOUNTANT: 50,
    Role.HR: 45,
    Role.COUNSELLOR: 42,
    Role.RECEPTIONIST: 40,
    Role.ADMINISTRATIVE_OFFICER: 38,
    Role.LIBRARIAN: 35,
    Role.GUARD: 30,
    Role.NURSE: 28,
    Role.TEACHER: 25,
    Role.STAFF: 20,
    Role.STUDENT: 10,
    Role.PARENT: 5,
}


def role_rank(role):
    """Return the numeric rank for a role value (or 0 for unknown roles)."""
    return ROLE_RANK.get(role, 0)


class User(AbstractUser):
    """
    Base user account for the School Management System.

    Staff and students will be connected to this account through
    their respective profiles.
    """

    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)

    institution = models.ForeignKey(
        School,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="users",
        help_text="Primary institution for this user. Null for super_admin users.",
    )

    username = models.CharField(
        max_length=150,
        unique=False,
        help_text="Username unique per institution. Super_admin users may have null institution.",
    )

    photo = models.ImageField(
        upload_to="profiles/users/",
        blank=True,
        null=True,
    )

    twofa_secret = models.CharField(
        max_length=64,
        blank=True,
        default="",
    )

    twofa_enabled = models.BooleanField(default=False)

    # Email verification (verify on register / first login)
    email_verified = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)

    # Account security fields
    failed_login_attempts = models.PositiveIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    last_failed_login_ip = models.GenericIPAddressField(null=True, blank=True)
    last_failed_login_at = models.DateTimeField(null=True, blank=True)
    password_changed_at = models.DateTimeField(auto_now_add=True)
    must_change_password = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["institution", "username"],
                name="unique_username_per_institution",
                condition=models.Q(institution__isnull=False),
            ),
        ]

    def get_active_memberships(self):
        return self.memberships.filter(status="active").select_related(
            "institution"
        )

    def get_roles(self, institution=None):
        cache = self.__dict__.get("_roles_cache")

        if cache is None:
            cache = {}
            self.__dict__["_roles_cache"] = cache

        key = institution.pk if hasattr(institution, "pk") else institution

        if key in cache:
            return cache[key]

        memberships = self.get_active_memberships()

        if institution is not None:
            memberships = memberships.filter(institution=institution)

        roles = list(
            RoleAssignment.objects.filter(
                membership__in=memberships
            ).values_list("role", flat=True)
        )

        cache[key] = roles
        return roles

    def has_role(self, role, institution=None):
        return role in self.get_roles(institution)

    def has_any_role(self, roles, institution=None):
        if self.is_superuser:
            return True

        user_roles = set(self.get_roles(institution))

        return any(role in user_roles for role in roles)

    @property
    def primary_role(self):
        roles = self.get_roles()

        priority = [
            Role.SUPER_ADMIN,
            Role.ORG_ADMIN,
            Role.HEAD_OFFICE,
            Role.ADMIN,
            Role.PRINCIPAL,
            Role.VICE_PRINCIPAL,
            Role.CAMPUS_ADMIN,
            Role.ACADEMIC,
            Role.ACCOUNTANT,
            Role.HR,
            Role.COUNSELLOR,
            Role.RECEPTIONIST,
            Role.ADMINISTRATIVE_OFFICER,
            Role.LIBRARIAN,
            Role.GUARD,
            Role.NURSE,
            Role.TEACHER,
            Role.PARENT,
            Role.STAFF,
            Role.STUDENT,
        ]

        for candidate in priority:
            if candidate in roles:
                return candidate

        return None

    @property
    def primary_institution(self):
        membership = self.get_active_memberships().first()
        return membership.institution if membership else None

    @property
    def is_super_admin(self):
        """True when this account is the platform Super Admin.

        A Super Admin is either a Django superuser (system-wide access) or the
        holder of the ``super_admin`` role. The platform enforces that there is
        exactly one such account at any time.
        """
        return self.is_superuser or self.has_role(Role.SUPER_ADMIN)

    def clean(self):
        super().clean()
        # Denormalized ``institution`` FK must agree with a real membership for
        # non-Super-Admin users. Super Admin may hold a null institution (or
        # many memberships) because they are not bound to one school.
        if (
            self.institution_id is not None
            and not self.is_superadmin_expected()
        ):
            has_membership = self.memberships.filter(
                institution_id=self.institution_id
            ).exists()
            if not has_membership:
                raise ValidationError(
                    {
                        "institution": (
                            "This user does not have a membership in the "
                            "selected institution."
                        )
                    }
                )

        # Hard-couple the role with Django superuser. A user holding the
        # super_admin role MUST be a Django superuser (unchecked demotions would
        # silently close the single-Super-Admin invariant surface).
        if (
            not self.is_superuser
            and self.has_role(Role.SUPER_ADMIN)
        ):
            raise ValidationError(
                {
                    "is_superuser": (
                        "This account holds the super_admin role but is not a "
                        "Django superuser. Keep is_superuser=True for the "
                        "platform Super Admin."
                    )
                }
            )

    def is_superadmin_expected(self):
        """Whether this user holds (or is being assigned) Super Admin powers.

        Kept as a helper so it can be reused by the save-time guards without
        triggering the full permission machinery.
        """
        if self.is_superuser or self.has_role(Role.SUPER_ADMIN):
            return True
        return RoleAssignment.objects.filter(
            membership__user=self,
            role=Role.SUPER_ADMIN,
        ).exists()

    def __str__(self):
        return self.username

    # =========================================================================
    # PERMISSION CHECKING METHODS
    # =========================================================================
    
    def get_permissions(self, institution=None):
        """
        Get all effective permissions for the user in an institution.
        
        Returns a set of permission codenames combining:
        - Role-based permissions (via RolePermission)
        - User-specific allow overrides (via UserPermission with effect=allow)
        - Excludes user-specific deny overrides (via UserPermission with effect=deny)
        """
        if institution is None:
            institution = self.primary_institution
        
        if institution is None:
            return set()
        
        # Get role-based permissions
        memberships = self.get_active_memberships().filter(institution=institution)
        role_names = RoleAssignment.objects.filter(
            membership__in=memberships
        ).values_list("role", flat=True).distinct()
        
        role_perms = set()
        if role_names:
            role_perms = set(RolePermission.objects.filter(
                role__in=role_names,
                institution=institution,
            ).values_list("permission__codename", flat=True))
        
        # Get user-specific allow permissions
        allow_perms = set(UserPermission.objects.filter(
            user=self,
            institution=institution,
            effect="allow",
        ).filter(
            models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=timezone.now())
        ).values_list("permission__codename", flat=True))
        
        # Get user-specific deny permissions
        deny_perms = set(UserPermission.objects.filter(
            user=self,
            institution=institution,
            effect="deny",
        ).filter(
            models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=timezone.now())
        ).values_list("permission__codename", flat=True))
        
        # Combine: role perms + allow perms - deny perms
        effective = (role_perms | allow_perms) - deny_perms
        
        # Superuser gets all permissions
        if self.is_superuser:
            return set(Permission.objects.values_list("codename", flat=True))
        
        return effective
    
    def has_permission(self, codename, institution=None):
        """Check if user has a specific permission."""
        return codename in self.get_permissions(institution)
    
    def has_any_permission(self, codenames, institution=None):
        """Check if user has any of the given permissions."""
        perms = self.get_permissions(institution)
        return any(c in perms for c in codenames)
    
    def has_all_permissions(self, codenames, institution=None):
        """Check if user has all of the given permissions."""
        perms = self.get_permissions(institution)
        return all(c in perms for c in codenames)


class EmailVerification(models.Model):
    """A single-use, expiring email-verification token for a user."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="email_verifications",
    )

    token = models.CharField(max_length=64, unique=True)

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    used = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_valid(self):
        return not self.used and self.expires_at > timezone.now()

    def __str__(self):
        return f"Email verification for {self.user.username}"


class InstitutionMembership(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("inactive", "Inactive"),
        ("suspended", "Suspended"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="memberships",
    )

    institution = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="memberships",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
    )

    joined_at = models.DateField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "institution"],
                name="unique_membership_per_user_institution",
            )
        ]

    def __str__(self):
        return (
            f"{self.user.username} @ {self.institution.name}"
        )

    def _user_is_super_admin(self):
        user = self.user
        return bool(
            user.is_superuser
            or user.has_role(Role.SUPER_ADMIN)
            or RoleAssignment.objects.filter(
                membership__user=user,
                role=Role.SUPER_ADMIN,
            ).exists()
        )

    def _assert_valid_for_user(self):
        """Server-side membership integrity guard.

        Rules enforced here:
          * Normal users belong to exactly ONE school. A second *active*
            membership in a different institution is rejected. (Several
            inactive/suspended historical memberships are tolerated.)
          * Super Admin is exempt: they may hold memberships in many schools in
            order to switch context system-wide.
          * Any linked profile (Staff / Teacher / Student) that carries a
            school must agree with this membership, so "User = Lahore but
            Profile = Sialkot" contradictions are impossible.
        """
        if self.user_id is None or self.institution_id is None:
            return

        if self._user_is_super_admin():
            return

        # Exactly one school for normal users.
        other_active = (
            InstitutionMembership.objects.filter(
                user_id=self.user_id,
                status="active",
            )
            .exclude(pk=self.pk)
            .exclude(institution_id=self.institution_id)
            .exists()
        )
        if other_active:
            raise ValidationError(
                "A normal user belongs to exactly one school. This user "
                "already has an active membership in another institution."
            )

        # Profile institution must match the membership.
        for related_attr in (
            "staff_profile",
            "teacher_profile",
            "student_profile",
        ):
            try:
                profile = getattr(self.user, related_attr, None)
            except Exception:
                profile = None
            if (
                profile is not None
                and profile.institution_id is not None
                and profile.institution_id != self.institution_id
            ):
                raise ValidationError(
                    f"The linked {related_attr} belongs to a different school "
                    "than this membership."
                )

    def clean(self):
        super().clean()
        self._assert_valid_for_user()

    def save(self, *args, **kwargs):
        self._assert_valid_for_user()
        super().save(*args, **kwargs)
        self._invalidate_user_role_cache()

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        self._invalidate_user_role_cache()

    def _invalidate_user_role_cache(self):
        user = self.user

        if user is not None:
            user.__dict__.pop("_roles_cache", None)


class RoleAssignment(models.Model):
    membership = models.ForeignKey(
        InstitutionMembership,
        on_delete=models.CASCADE,
        related_name="role_assignments",
    )

    role = models.CharField(
        max_length=30,
        choices=Role.choices,
    )

    campus = models.ForeignKey(
        "schools.Campus",
        on_delete=models.CASCADE,
        related_name="role_assignments",
        null=True,
        blank=True,
        help_text="Campus-level scope for campus-level roles (principal, vice_principal, campus_admin). Null for school-level roles.",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["role"]
        constraints = [
            models.UniqueConstraint(
                fields=["membership", "role"],
                name="unique_role_per_membership",
                condition=models.Q(campus__isnull=True),
            ),
            models.UniqueConstraint(
                fields=["membership", "role", "campus"],
                name="unique_role_per_membership_campus",
                condition=models.Q(campus__isnull=False),
            ),
            # At most ONE super_admin exists platform-wide. A partial unique
            # index on a constant makes the whole table reject a second row.
            models.UniqueConstraint(
                fields=["role"],
                name="unique_super_admin_role",
                condition=models.Q(role="super_admin"),
            ),
            # One Principal per campus
            models.UniqueConstraint(
                fields=["campus", "role"],
                name="unique_principal_per_campus",
                condition=models.Q(role="principal", campus__isnull=False),
            ),
            # One Vice Principal per campus
            models.UniqueConstraint(
                fields=["campus", "role"],
                name="unique_vice_principal_per_campus",
                condition=models.Q(role="vice_principal", campus__isnull=False),
            ),
            # One Campus Admin per campus
            models.UniqueConstraint(
                fields=["campus", "role"],
                name="unique_campus_admin_per_campus",
                condition=models.Q(role="campus_admin", campus__isnull=False),
            ),
        ]

    def clean(self):
        super().clean()
        if self.role != Role.SUPER_ADMIN:
            if self.role in [Role.PRINCIPAL, Role.VICE_PRINCIPAL, Role.CAMPUS_ADMIN]:
                if self.campus_id is None:
                    raise ValidationError(
                        {
                            "campus": (
                                f"{self.get_role_display()} requires an explicit campus assignment."
                            )
                        }
                    )
                # Validate campus belongs to the same school as the membership
                if self.membership_id and self.campus_id:
                    from apps.schools.models import Campus
                    campus = Campus.objects.filter(pk=self.campus_id).first()
                    if campus and campus.school_id != self.membership.institution_id:
                        raise ValidationError(
                            {
                                "campus": "Campus must belong to the same school as the user's membership."
                            }
                        )
            else:
                # School-level roles must not have a campus assignment
                if self.campus_id is not None:
                    raise ValidationError(
                        {
                            "campus": (
                                f"{self.get_role_display()} is a school-level role and cannot have a campus assignment."
                            )
                        }
                    )
            return
        existing = (
            RoleAssignment.objects.filter(
                role=Role.SUPER_ADMIN,
            )
            .exclude(pk=self.pk)
            .first()
        )
        if existing is not None:
            raise ValidationError(
                "There is already exactly one platform Super Admin "
                f"({existing.membership.user.username}). Duplicate Super Admin "
                "accounts are not allowed."
            )
        if self.membership_id and not self.membership.user.is_superuser:
            raise ValidationError(
                {
                    "role": (
                        "The super_admin role requires a Django superuser "
                        "account (is_superuser=True). Elevate the account first "
                        "(e.g. via ensure_superuser) so the platform stays "
                        "consistent."
                    )
                }
            )

    def save(self, *args, **kwargs):
        """Persist the assignment and keep the Super Admin invariant tight.

        Granting ``super_admin`` automatically elevates the account to a Django
        superuser (and staff), so the role can never exist on an account that is
        not also ``is_superuser`` — the model layer hard-couples the two. The
        flip is done through ``QuerySet.update`` to avoid recursion and is only
        applied *after* the row is safely inserted (a duplicate ``super_admin``
        raises IntegrityError before any elevation).
        """
        super().save(*args, **kwargs)
        if self.role == Role.SUPER_ADMIN and self.membership_id:
            user_id = InstitutionMembership.objects.filter(
                pk=self.membership_id
            ).values_list("user_id", flat=True).first()
            if user_id is not None:
                User.objects.filter(pk=user_id).update(
                    is_superuser=True,
                    is_staff=True,
                )
        self._invalidate_user_role_cache()

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        self._invalidate_user_role_cache()

    def _invalidate_user_role_cache(self):
        membership = self.membership
        user = getattr(membership, "user", None)

        if user is not None:
            user.__dict__.pop("_roles_cache", None)

    def __str__(self):
        return f"{self.membership} - {self.get_role_display()}"


def assign_role_safely(membership, role, campus=None):
    """Create a ``RoleAssignment`` without ever violating the single-Super-Admin
    invariant.

    Returns ``(assignment, created, note)`` where ``note`` is a human-readable
    string when the request was downgraded, else ``None``.

    When ``role`` is ``super_admin`` and a *different* user already holds the
    Super Admin role, the request is downgraded to ``admin`` (with a note)
    instead of failing, keeping seeds and commands idempotent.
    """
    if role == Role.SUPER_ADMIN:
        # Any *other* membership that already holds the role — even the same
        # account's membership in another school — means this request wants the
        # second (impossible) Super Admin row. Downgrade to ``admin`` instead of
        # letting the partial unique constraint raise IntegrityError, keeping
        # re-seeds idempotent.
        holder = (
            RoleAssignment.objects.filter(role=Role.SUPER_ADMIN)
            .select_related("membership__user")
            .exclude(membership=membership)
            .first()
        )
        if holder is not None:
            assignment, created = RoleAssignment.objects.get_or_create(
                membership=membership,
                role=Role.ADMIN,
            )
            return (
                assignment,
                created,
                (
                    f"super_admin already held by "
                    f"{holder.membership.user.username}; assigned admin instead"
                ),
            )

    assignment, created = RoleAssignment.objects.get_or_create(
        membership=membership,
        role=role,
        campus=campus,
    )
    return assignment, created, None


def demote_extra_active_memberships(user):
    """Enforce the single-school rule over historical ``InstitutionMembership``
    data for one user.

    A user who is NOT Super Admin and holds more than one *active* membership
    has all but one demoted to ``inactive``. The kept membership prefers the one
    matching ``user.institution`` (denormalized FK), else the earliest row.
    Super Admin users are left untouched.

    Uses ``bulk_update`` on purpose: ``InstitutionMembership.save()`` runs the
    single-school guard, which would refuse this exact historical demotion.

    Returns the list of demoted (now inactive) memberships.
    """
    if user.pk is None or user.is_superuser:
        return []
    if RoleAssignment.objects.filter(
        membership__user=user,
        role=Role.SUPER_ADMIN,
    ).exists():
        return []

    actives = list(
        InstitutionMembership.objects.filter(
            user=user,
            status="active",
        ).order_by("created_at", "id")
    )
    if len(actives) <= 1:
        return []

    keeper = None
    if user.institution_id is not None:
        keeper = next(
            (m for m in actives if m.institution_id == user.institution_id),
            None,
        )
    if keeper is None:
        keeper = actives[0]

    demoted = [m for m in actives if m.pk != keeper.pk]
    for membership in demoted:
        membership.status = "inactive"
    InstitutionMembership.objects.bulk_update(demoted, ["status"])
    user.__dict__.pop("_roles_cache", None)
    return demoted


class StaffProfile(SoftDeleteMixin):
    objects = SoftDeleteManager()
    GENDER_CHOICES = [
        ("male", "Male"),
        ("female", "Female"),
        ("other", "Other"),
    ]

    STATUS_CHOICES = [
        ("active", "Active"),
        ("inactive", "Inactive"),
    ]

    institution = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="staff_profiles",
        null=True,
        blank=True,
    )

    user = models.OneToOneField(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_profile",
    )

    membership = models.OneToOneField(InstitutionMembership, on_delete=models.SET_NULL, null=True, blank=True, related_name="staff_profile_membership")
    primary_campus = models.ForeignKey("schools.Campus", on_delete=models.SET_NULL, null=True, blank=True, related_name="primary_staff")

    employee_number = models.CharField(
        max_length=50,
    )

    photo = models.ImageField(
        upload_to="profiles/staff/",
        blank=True,
        null=True,
    )

    first_name = models.CharField(
        max_length=100,
    )

    last_name = models.CharField(
        max_length=100,
    )

    gender = models.CharField(
        max_length=20,
        choices=GENDER_CHOICES,
    )

    date_of_birth = models.DateField(
        null=True,
        blank=True,
    )

    phone = models.CharField(
        max_length=30,
        blank=True,
    )

    email = models.EmailField(
        blank=True,
    )

    designation = models.CharField(
        max_length=100,
        default="Staff",
    )

    department = models.CharField(
        max_length=100,
        blank=True,
    )

    joining_date = models.DateField(
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["first_name", "last_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["institution", "employee_number"],
                name="unique_staff_employee_number_per_institution",
            )
        ]

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return (
            f"{self.employee_number} - "
            f"{self.full_name or self.user.get_full_name() or self.user.username}"
        )


class StaffAttendance(SoftDeleteMixin):
    objects = SoftDeleteManager()
    """Daily attendance record for a staff member / teacher."""

    STATUS_CHOICES = [
        ("present", "Present"),
        ("absent", "Absent"),
        ("late", "Late"),
        ("half_day", "Half Day"),
        ("leave", "On Leave"),
    ]

    institution = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="staff_attendance",
        null=True,
        blank=True,
    )

    staff = models.ForeignKey(
        StaffProfile,
        on_delete=models.CASCADE,
        related_name="attendance_records",
        null=True,
        blank=True,
    )

    date = models.DateField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="present",
    )

    check_in = models.TimeField(
        null=True,
        blank=True,
    )

    check_out = models.TimeField(
        null=True,
        blank=True,
    )

    notes = models.TextField(
        blank=True,
    )

    marked_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marked_staff_attendance",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "staff__first_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["staff", "date"],
                name="unique_staff_attendance_per_day",
            )
        ]

    def __str__(self):
        return f"{self.staff} - {self.date} - {self.get_status_display()}"

    @property
    def working_hours(self):
        """Compute elapsed working time from check_in / check_out.

        Returns a ``timedelta``, or ``None`` when either timestamp is missing.
        """
        if self.check_in is None or self.check_out is None:
            return None

        from datetime import datetime

        start = datetime.combine(self.date, self.check_in)
        end = datetime.combine(self.date, self.check_out)
        if end < start:
            # Overnight shift: assume wrap-around to the next day.
            from datetime import timedelta

            end += timedelta(days=1)
        return end - start


class StaffAttendanceCorrection(SoftDeleteMixin):
    """
    Immutable audit trail for every change made to a staff attendance record.

    Each correction preserves the old value and the new value (status and
    check-in/check-out), who performed it, when, and why. Corrections are
    never edited or deleted, so the full history is retained.
    """

    objects = SoftDeleteManager()

    attendance = models.ForeignKey(
        StaffAttendance,
        on_delete=models.CASCADE,
        related_name="corrections",
    )

    staff = models.ForeignKey(
        StaffProfile,
        on_delete=models.CASCADE,
        related_name="attendance_corrections",
        null=True,
        blank=True,
    )

    institution = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="staff_attendance_corrections",
        null=True,
        blank=True,
    )

    from_status = models.CharField(
        max_length=20,
        choices=StaffAttendance.STATUS_CHOICES,
    )
    to_status = models.CharField(
        max_length=20,
        choices=StaffAttendance.STATUS_CHOICES,
    )

    from_check_in = models.TimeField(null=True, blank=True)
    to_check_in = models.TimeField(null=True, blank=True)
    from_check_out = models.TimeField(null=True, blank=True)
    to_check_out = models.TimeField(null=True, blank=True)

    reason = models.TextField(blank=True)

    corrected_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_attendance_corrections_made",
    )

    corrected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-corrected_at"]
        indexes = [
            models.Index(
                fields=["attendance", "-corrected_at"],
                name="staff_att_corr_att_idx",
            ),
            models.Index(
                fields=["staff", "corrected_by"],
                name="staff_att_corr_staff_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.staff} {self.attendance.date}: "
            f"{self.from_status} -> {self.to_status}"
        )


class StaffLeave(SoftDeleteMixin):
    objects = SoftDeleteManager()
    """Leave request raised by staff/teachers and approved by HR."""

    LEAVE_TYPE_CHOICES = [
        ("casual", "Casual Leave"),
        ("sick", "Sick Leave"),
        ("annual", "Annual Leave"),
        ("maternity", "Maternity Leave"),
        ("paternity", "Paternity Leave"),
        ("unpaid", "Unpaid Leave"),
        ("other", "Other"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"),
    ]

    institution = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="staff_leaves",
        null=True,
        blank=True,
    )

    staff = models.ForeignKey(
        StaffProfile,
        on_delete=models.CASCADE,
        related_name="leave_requests",
        null=True,
        blank=True,
    )

    leave_type = models.CharField(
        max_length=20,
        choices=LEAVE_TYPE_CHOICES,
    )

    start_date = models.DateField()
    end_date = models.DateField()

    reason = models.TextField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )

    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_staff_leave",
    )

    review_notes = models.TextField(
        blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    @property
    def days(self):
        return (self.end_date - self.start_date).days + 1

    def __str__(self):
        return (
            f"{self.staff} - {self.get_leave_type_display()} "
            f"({self.start_date} to {self.end_date})"
        )


class FailedLoginAttempt(models.Model):
    """Track failed login attempts for account lockout."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="failed_login_records",
    )
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    attempted_at = models.DateTimeField(auto_now_add=True)
    username_or_email = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-attempted_at"]
        indexes = [
            models.Index(
                fields=["user", "attempted_at"],
                name="failed_login_user_time_idx",
            ),
            models.Index(
                fields=["ip_address", "attempted_at"],
                name="failed_login_ip_time_idx",
            ),
        ]

    def __str__(self):
        return f"Failed login for {self.username_or_email} from {self.ip_address}"


class PasswordHistory(models.Model):
    """Store password history to prevent reuse."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="password_history",
    )
    password_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["user", "created_at"],
                name="pwdhist_user_time_idx",
            ),
        ]

    def __str__(self):
        return f"Password history for {self.user.username}"


class UserSession(models.Model):
    """Track active user sessions for management and revocation."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="user_sessions",
    )
    session_key = models.CharField(max_length=40, unique=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()
    is_current = models.BooleanField(default=False)

    class Meta:
        ordering = ["-last_activity_at"]
        indexes = [
            models.Index(
                fields=["user", "is_current"],
                name="usersession_user_current_idx",
            ),
            models.Index(
                fields=["expires_at"],
                name="usersession_expires_idx",
            ),
        ]

    def __str__(self):
        return f"Session for {self.user.username} from {self.ip_address}"

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at


class TwoFABackupCode(models.Model):
    """Backup codes for TOTP 2FA recovery.

    ``code_hash`` is an HMAC-SHA256 of the code keyed by the Django
    ``SECRET_KEY`` plus the per-code ``salt`` (never a bare hash). Legacy
    rows created before this hardening use an empty salt.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="twofa_backup_codes",
    )
    code_hash = models.CharField(max_length=128)
    salt = models.CharField(max_length=64, default="", blank=True)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["user", "used_at"],
                name="twofa_backup_user_used_idx",
            ),
        ]

    def __str__(self):
        status = "used" if self.used_at else "unused"
        return f"2FA backup code ({status}) for {self.user.username}"


# =============================================================================
# STUDENT TRANSFER
# =============================================================================


class TransferManager(models.Manager):
    """Custom manager for ``StudentTransfer`` with helper methods."""

    def transfer_student(self, student, to_campus, request_user, reason=""):
        """Initiate a student transfer request.

        Validates that ``request_user`` has the appropriate role for the
        target campus, creates a pending ``StudentTransfer`` record, and
        updates the student's primary campus enrollment.

        Returns the created ``StudentTransfer`` instance.
        """
        from apps.accounts.access import restrict_to_allowed_campuses

        # Determine if the user is allowed to transfer to this campus.
        # Campus admins can transfer within their own campus; super_admins
        # can transfer anywhere.
        user_roles = request_user.get_roles(request_user.primary_institution)
        is_super_admin = Role.SUPER_ADMIN in user_roles
        is_campus_admin = Role.CAMPUS_ADMIN in user_roles

        # Verify the user has permission on the target campus.
        if not is_super_admin and not is_campus_admin:
            raise PermissionDenied(
                "You do not have permission to transfer students to this campus."
            )

        # Use the existing campus-scoping helper to validate the target campus.
        allowed = restrict_to_allowed_campuses(
            InstitutionMembership.objects.none(),
            request_user,
            "campus_id",
            institution_field="institution",
        )
        # For super/admins we allow any campus; for campus_admins we restrict.
        if not is_super_admin:
            target_campus_ids = allowed.values_list("id", flat=True)
            if to_campus.id not in target_campus_ids:
                raise PermissionDenied(
                    "Target campus is not within your assigned campus."
                )

        # Update the student's primary campus immediately so enrolled classes
        # reflect the new campus right away.
        from students.models import Student, Enrollment

        student.primary_campus = to_campus
        student.save(update_fields=["primary_campus"])

        # Update all active enrollments to the new campus.
        Enrollment.objects.filter(
            student=student,
            status="active",
        ).update(campus=to_campus)

        # Create the transfer record.
        transfer = self.create(
            student=student,
            from_campus=student.primary_campus if hasattr(student, "primary_campus") else None,
            to_campus=to_campus,
            status="pending",
            reason=reason,
            approved_by=request_user,
        )

        # Record audit log.
        from apps.audit.models import record_audit

        record_audit(
            request=None,
            user=request_user,
            action="student_transfer_initiated",
            details={
                "student_id": student.pk,
                "student_name": str(student),
                "from_campus": str(student.primary_campus) if student.primary_campus else None,
                "to_campus": str(to_campus),
                "reason": reason,
            },
        )

        return transfer


class StudentTransfer(models.Model):
    """Formal transfer of a student between campuses.

    Records a transfer request that must be approved before the student's
    campus is changed. This prevents orphaned enrollments and ensures
    auditability of cross-campus moves.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    student = models.ForeignKey(
        "students.Student",
        on_delete=models.CASCADE,
        related_name="transfers",
    )
    from_campus = models.ForeignKey(
        "schools.Campus",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accounts_transfers_from",
    )
    to_campus = models.ForeignKey(
        "schools.Campus",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accounts_transfers_to",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
    )
    reason = models.TextField(
        blank=True,
        help_text="Reason for the transfer request.",
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_student_transfers",
    )

    class Meta:
        ordering = ["-requested_at"]
        indexes = [
            models.Index(fields=["student", "status"]),
            models.Index(fields=["status", "requested_at"]),
        ]

    def __str__(self):
        return (
            f"Transfer {self.pk}: {self.student} "
            f"from {self.from_campus} to {self.to_campus} "
            f"({self.status})"
        )

    @property
    def is_pending(self):
        return self.status == "pending"

    @property
    def is_approved(self):
        return self.status == "approved"

    @property
    def is_rejected(self):
        return self.status == "rejected"

    objects = TransferManager()


class TransferManager(models.Manager):
    """Custom manager for ``StudentTransfer`` with helper methods."""

    def transfer_student(self, student, to_campus, request_user, reason=""):
        """Initiate a student transfer request.

        Validates that ``request_user`` has the appropriate role for the
        target campus, creates a pending ``StudentTransfer`` record, and
        updates the student's primary campus enrollment.

        Returns the created ``StudentTransfer`` instance.
        """
        from apps.accounts.access import restrict_to_allowed_campuses

        # Determine if the user is allowed to transfer to this campus.
        # Campus admins can transfer within their own campus; super_admins
        # can transfer anywhere.
        user_roles = request_user.get_roles(request_user.primary_institution)
        is_super_admin = Role.SUPER_ADMIN in user_roles
        is_campus_admin = Role.CAMPUS_ADMIN in user_roles

        # Verify the user has permission on the target campus.
        if not is_super_admin and not is_campus_admin:
            raise PermissionDenied(
                "You do not have permission to transfer students to this campus."
            )

        # Use the existing campus-scoping helper to validate the target campus.
        allowed = restrict_to_allowed_campuses(
            InstitutionMembership.objects.none(),
            request_user,
            "campus_id",
            institution_field="institution",
        )
        # For super/admins we allow any campus; for campus_admins we restrict.
        if not is_super_admin:
            target_campus_ids = allowed.values_list("id", flat=True)
            if to_campus.id not in target_campus_ids:
                raise PermissionDenied(
                    "Target campus is not within your assigned campus."
                )

        # Update the student's primary campus immediately so enrolled classes
        # reflect the new campus right away.
        from students.models import Student, Enrollment

        student.primary_campus = to_campus
        student.save(update_fields=["primary_campus"])

        # Update all active enrollments to the new campus.
        Enrollment.objects.filter(
            student=student,
            status="active",
        ).update(campus=to_campus)

        # Create the transfer record.
        transfer = self.create(
            student=student,
            from_campus=student.primary_campus if hasattr(student, "primary_campus") else None,
            to_campus=to_campus,
            status="pending",
            reason=reason,
            approved_by=request_user,
        )

        # Record audit log.
        from apps.audit.models import record_audit

        record_audit(
            request=None,
            user=request_user,
            action="student_transfer_initiated",
            details={
                "student_id": student.pk,
                "student_name": str(student),
                "from_campus": str(student.primary_campus) if student.primary_campus else None,
                "to_campus": str(to_campus),
                "reason": reason,
            },
        )

        return transfer


# =============================================================================
# GRANULAR PERMISSIONS SYSTEM
# =============================================================================

class Permission(models.Model):
    """
    Granular permissions for the ERP system.
    
    Naming convention: <resource>.<action>
    Examples:
    - student.view, student.create, student.edit, student.delete
    - student.approve, student.reject, student.export, student.print
    - finance.invoice.view, finance.invoice.create, finance.invoice.edit
    - finance.payment.view, finance.payment.create, finance.payment.approve
    - exam.view, exam.create, exam.edit, exam.delete, exam.publish
    - attendance.view, attendance.create, attendance.edit
    - hr.employee.view, hr.employee.create, hr.employee.edit
    - payroll.view, payroll.create, payroll.approve, payroll.process
    - settings.view, settings.edit
    - report.view, report.export
    - user.manage, role.manage, permission.manage
    """
    
    ACTION_CHOICES = [
        ("view", "View"),
        ("create", "Create"),
        ("edit", "Edit"),
        ("update", "Update"),
        ("delete", "Delete"),
        ("approve", "Approve"),
        ("reject", "Reject"),
        ("export", "Export"),
        ("print", "Print"),
        ("manage", "Manage"),
        ("publish", "Publish"),
        ("process", "Process"),
        ("assign", "Assign"),
        ("unassign", "Unassign"),
        ("refund", "Refund"),
        ("return", "Return"),
        ("overdue", "Overdue"),
        ("adjust", "Adjust"),
        ("grade", "Grade"),
        ("send", "Send"),
        ("backup", "Backup"),
        ("maintenance", "Maintenance"),
        ("ask", "Ask"),
        ("search", "Search"),
        ("anomaly", "Anomaly"),
        ("communicate", "Communicate"),
    ]
    
    # Resource categories for organization
    CATEGORY_CHOICES = [
        ("student", "Student Management"),
        ("teacher", "Teacher Management"),
        ("staff", "Staff Management"),
        ("admission", "Admissions"),
        ("attendance", "Attendance"),
        ("exam", "Examinations"),
        ("finance", "Finance & Fees"),
        ("payroll", "Payroll"),
        ("hr", "Human Resources"),
        ("library", "Library"),
        ("transport", "Transport"),
        ("inventory", "Inventory"),
        ("hostel", "Hostel"),
        ("lms", "Learning Management"),
        ("communication", "Communication"),
        ("settings", "Settings"),
        ("report", "Reports"),
        ("user", "User Management"),
        ("role", "Role Management"),
        ("permission", "Permission Management"),
        ("system", "System Administration"),
        ("insight", "AI & Insights"),
    ]
    
    codename = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    is_system = models.BooleanField(default=False, help_text="System permissions cannot be deleted")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ["category", "action", "codename"]
        indexes = [
            models.Index(fields=["category", "action"], name="perm_cat_action_idx"),
        ]
    
    def __str__(self):
        return f"{self.codename} ({self.name})"
    
    @classmethod
    def get_default_permissions(cls):
        """Return the standard set of permissions for the ERP."""
        return [
            # Student permissions
            ("student.view", "View Students", "student", "view"),
            ("student.create", "Create Students", "student", "create"),
            ("student.edit", "Edit Students", "student", "edit"),
            ("student.delete", "Delete Students", "student", "delete"),
            ("student.export", "Export Students", "student", "export"),
            ("student.print", "Print Students", "student", "print"),
            ("student.approve", "Approve Student Status", "student", "approve"),
            ("student.assign", "Assign Student to Class", "student", "assign"),
            
            # Teacher permissions
            ("teacher.view", "View Teachers", "teacher", "view"),
            ("teacher.create", "Create Teachers", "teacher", "create"),
            ("teacher.edit", "Edit Teachers", "teacher", "edit"),
            ("teacher.delete", "Delete Teachers", "teacher", "delete"),
            ("teacher.export", "Export Teachers", "teacher", "export"),
            ("teacher.assign", "Assign Teacher to Class", "teacher", "assign"),
            
            # Staff permissions
            ("staff.view", "View Staff", "staff", "view"),
            ("staff.create", "Create Staff", "staff", "create"),
            ("staff.edit", "Edit Staff", "staff", "edit"),
            ("staff.delete", "Delete Staff", "staff", "delete"),
            ("staff.export", "Export Staff", "staff", "export"),
            ("staff.assign", "Assign Staff", "staff", "assign"),
            
            # Admission permissions
            ("admission.view", "View Admissions", "admission", "view"),
            ("admission.create", "Create Admissions", "admission", "create"),
            ("admission.edit", "Edit Admissions", "admission", "edit"),
            ("admission.delete", "Delete Admissions", "admission", "delete"),
            ("admission.approve", "Approve Admissions", "admission", "approve"),
            ("admission.reject", "Reject Admissions", "admission", "reject"),
            
            # Attendance permissions
            ("attendance.view", "View Attendance", "attendance", "view"),
            ("attendance.create", "Mark Attendance", "attendance", "create"),
            ("attendance.edit", "Edit Attendance", "attendance", "edit"),
            ("attendance.delete", "Delete Attendance", "attendance", "delete"),
            ("attendance.approve", "Approve Attendance", "attendance", "approve"),
            ("attendance.export", "Export Attendance", "attendance", "export"),
            ("attendance.print", "Print Attendance", "attendance", "print"),
            
            # Exam permissions
            ("exam.view", "View Exams", "exam", "view"),
            ("exam.create", "Create Exams", "exam", "create"),
            ("exam.edit", "Edit Exams", "exam", "edit"),
            ("exam.delete", "Delete Exams", "exam", "delete"),
            ("exam.publish", "Publish Exams", "exam", "publish"),
            ("exam.result.view", "View Exam Results", "exam", "view"),
            ("exam.result.create", "Enter Exam Results", "exam", "create"),
            ("exam.result.edit", "Edit Exam Results", "exam", "edit"),
            ("exam.result.approve", "Approve Exam Results", "exam", "approve"),
            ("exam.result.export", "Export Exam Results", "exam", "export"),
            ("exam.result.print", "Print Exam Results", "exam", "print"),
            
            # Finance permissions
            ("finance.fee_category.view", "View Fee Categories", "finance", "view"),
            ("finance.fee_category.create", "Create Fee Categories", "finance", "create"),
            ("finance.fee_category.edit", "Edit Fee Categories", "finance", "edit"),
            ("finance.fee_category.delete", "Delete Fee Categories", "finance", "delete"),
            ("finance.fee_structure.view", "View Fee Structures", "finance", "view"),
            ("finance.fee_structure.create", "Create Fee Structures", "finance", "create"),
            ("finance.fee_structure.edit", "Edit Fee Structures", "finance", "edit"),
            ("finance.fee_structure.delete", "Delete Fee Structures", "finance", "delete"),
            ("finance.invoice.view", "View Invoices", "finance", "view"),
            ("finance.invoice.create", "Create Invoices", "finance", "create"),
            ("finance.invoice.edit", "Edit Invoices", "finance", "edit"),
            ("finance.invoice.delete", "Delete Invoices", "finance", "delete"),
            ("finance.invoice.approve", "Approve Invoices", "finance", "approve"),
            ("finance.invoice.export", "Export Invoices", "finance", "export"),
            ("finance.invoice.print", "Print Invoices", "finance", "print"),
            ("finance.payment.view", "View Payments", "finance", "view"),
            ("finance.payment.create", "Record Payments", "finance", "create"),
            ("finance.payment.edit", "Edit Payments", "finance", "edit"),
            ("finance.payment.delete", "Delete Payments", "finance", "delete"),
            ("finance.payment.approve", "Approve Payments", "finance", "approve"),
            ("finance.payment.refund", "Refund Payments", "finance", "refund"),
            ("finance.concession.view", "View Concessions", "finance", "view"),
            ("finance.concession.create", "Create Concessions", "finance", "create"),
            ("finance.concession.approve", "Approve Concessions", "finance", "approve"),
            ("finance.concession.reject", "Reject Concessions", "finance", "reject"),
            ("finance.expense.view", "View Expenses", "finance", "view"),
            ("finance.expense.create", "Create Expenses", "finance", "create"),
            ("finance.expense.edit", "Edit Expenses", "finance", "edit"),
            ("finance.expense.approve", "Approve Expenses", "finance", "approve"),
            ("finance.journal.view", "View Journal Entries", "finance", "view"),
            ("finance.journal.create", "Create Journal Entries", "finance", "create"),
            ("finance.journal.edit", "Edit Journal Entries", "finance", "edit"),
            ("finance.journal.approve", "Approve Journal Entries", "finance", "approve"),
            ("finance.export", "Export Finance Data", "finance", "export"),
            ("finance.print", "Print Finance Reports", "finance", "print"),
            
            # Payroll permissions
            ("payroll.view", "View Payroll", "payroll", "view"),
            ("payroll.create", "Create Payroll", "payroll", "create"),
            ("payroll.edit", "Edit Payroll", "payroll", "edit"),
            ("payroll.process", "Process Payroll", "payroll", "process"),
            ("payroll.approve", "Approve Payroll", "payroll", "approve"),
            ("payroll.export", "Export Payroll", "payroll", "export"),
            ("payroll.print", "Print Payslips", "payroll", "print"),
            ("payroll.salary_structure.view", "View Salary Structures", "payroll", "view"),
            ("payroll.salary_structure.create", "Create Salary Structures", "payroll", "create"),
            ("payroll.salary_structure.edit", "Edit Salary Structures", "payroll", "edit"),
            
            # HR permissions
            ("hr.employee.view", "View Employees", "hr", "view"),
            ("hr.employee.create", "Create Employees", "hr", "create"),
            ("hr.employee.edit", "Edit Employees", "hr", "edit"),
            ("hr.employee.delete", "Delete Employees", "hr", "delete"),
            ("hr.contract.view", "View Contracts", "hr", "view"),
            ("hr.contract.create", "Create Contracts", "hr", "create"),
            ("hr.contract.edit", "Edit Contracts", "hr", "edit"),
            ("hr.contract.approve", "Approve Contracts", "hr", "approve"),
            ("hr.document.view", "View Documents", "hr", "view"),
            ("hr.document.create", "Upload Documents", "hr", "create"),
            ("hr.performance.view", "View Performance", "hr", "view"),
            ("hr.performance.create", "Create Performance Reviews", "hr", "create"),
            ("hr.performance.edit", "Edit Performance Reviews", "hr", "edit"),
            ("hr.workload.view", "View Workload", "hr", "view"),
            ("hr.workload.create", "Create Workload Assignments", "hr", "create"),
            ("hr.workload.edit", "Edit Workload Assignments", "hr", "edit"),
            ("hr.export", "Export HR Data", "hr", "export"),
            
            # Library permissions
            ("library.book.view", "View Books", "library", "view"),
            ("library.book.create", "Add Books", "library", "create"),
            ("library.book.edit", "Edit Books", "library", "edit"),
            ("library.book.delete", "Delete Books", "library", "delete"),
            ("library.issue.view", "View Book Issues", "library", "view"),
            ("library.issue.create", "Issue Books", "library", "create"),
            ("library.issue.return", "Return Books", "library", "return"),
            ("library.issue.overdue", "Manage Overdue", "library", "overdue"),
            ("library.export", "Export Library Data", "library", "export"),
            
            # Transport permissions
            ("transport.vehicle.view", "View Vehicles", "transport", "view"),
            ("transport.vehicle.create", "Add Vehicles", "transport", "create"),
            ("transport.vehicle.edit", "Edit Vehicles", "transport", "edit"),
            ("transport.route.view", "View Routes", "transport", "view"),
            ("transport.route.create", "Create Routes", "transport", "create"),
            ("transport.route.edit", "Edit Routes", "transport", "edit"),
            ("transport.student.view", "View Student Transport", "transport", "view"),
            ("transport.student.assign", "Assign Student Transport", "transport", "assign"),
            ("transport.export", "Export Transport Data", "transport", "export"),
            
            # Inventory permissions
            ("inventory.item.view", "View Inventory Items", "inventory", "view"),
            ("inventory.item.create", "Add Inventory Items", "inventory", "create"),
            ("inventory.item.edit", "Edit Inventory Items", "inventory", "edit"),
            ("inventory.item.delete", "Delete Inventory Items", "inventory", "delete"),
            ("inventory.stock.view", "View Stock", "inventory", "view"),
            ("inventory.stock.adjust", "Adjust Stock", "inventory", "adjust"),
            ("inventory.order.view", "View Purchase Orders", "inventory", "view"),
            ("inventory.order.create", "Create Purchase Orders", "inventory", "create"),
            ("inventory.order.approve", "Approve Purchase Orders", "inventory", "approve"),
            ("inventory.export", "Export Inventory Data", "inventory", "export"),
            
            # Hostel permissions
            ("hostel.room.view", "View Rooms", "hostel", "view"),
            ("hostel.room.create", "Create Rooms", "hostel", "create"),
            ("hostel.room.edit", "Edit Rooms", "hostel", "edit"),
            ("hostel.allocation.view", "View Allocations", "hostel", "view"),
            ("hostel.allocation.create", "Create Allocations", "hostel", "create"),
            ("hostel.allocation.edit", "Edit Allocations", "hostel", "edit"),
            ("hostel.fee.view", "View Hostel Fees", "hostel", "view"),
            ("hostel.fee.create", "Create Hostel Fees", "hostel", "create"),
            ("hostel.export", "Export Hostel Data", "hostel", "export"),
            
            # LMS permissions
            ("lms.course.view", "View Courses", "lms", "view"),
            ("lms.course.create", "Create Courses", "lms", "create"),
            ("lms.course.edit", "Edit Courses", "lms", "edit"),
            ("lms.course.delete", "Delete Courses", "lms", "delete"),
            ("lms.lesson.view", "View Lessons", "lms", "view"),
            ("lms.lesson.create", "Create Lessons", "lms", "create"),
            ("lms.lesson.edit", "Edit Lessons", "lms", "edit"),
            ("lms.enrollment.view", "View Enrollments", "lms", "view"),
            ("lms.enrollment.manage", "Manage Enrollments", "lms", "manage"),
            ("lms.assignment.view", "View Assignments", "lms", "view"),
            ("lms.assignment.create", "Create Assignments", "lms", "create"),
            ("lms.assignment.grade", "Grade Assignments", "lms", "grade"),
            ("lms.export", "Export LMS Data", "lms", "export"),
            
            # Communication permissions
            ("communication.announcement.view", "View Announcements", "communication", "view"),
            ("communication.announcement.create", "Create Announcements", "communication", "create"),
            ("communication.announcement.edit", "Edit Announcements", "communication", "edit"),
            ("communication.announcement.delete", "Delete Announcements", "communication", "delete"),
            ("communication.message.view", "View Messages", "communication", "view"),
            ("communication.message.send", "Send Messages", "communication", "send"),
            ("communication.sms.view", "View SMS", "communication", "view"),
            ("communication.sms.send", "Send SMS", "communication", "send"),
            ("communication.template.view", "View Templates", "communication", "view"),
            ("communication.template.create", "Create Templates", "communication", "create"),
            ("communication.template.edit", "Edit Templates", "communication", "edit"),
            
            # Settings permissions
            ("settings.view", "View Settings", "settings", "view"),
            ("settings.edit", "Edit Settings", "settings", "edit"),
            ("settings.branding.view", "View Branding", "settings", "view"),
            ("settings.branding.edit", "Edit Branding", "settings", "edit"),
            ("settings.module.view", "View Modules", "settings", "view"),
            ("settings.module.edit", "Edit Modules", "settings", "edit"),
            
            # Report permissions
            ("report.view", "View Reports", "report", "view"),
            ("report.create", "Create Reports", "report", "create"),
            ("report.edit", "Edit Reports", "report", "edit"),
            ("report.delete", "Delete Reports", "report", "delete"),
            ("report.export", "Export Reports", "report", "export"),
            ("report.print", "Print Reports", "report", "print"),
            ("report.builder.view", "View Report Builder", "report", "view"),
            ("report.builder.create", "Create Report Templates", "report", "create"),
            
            # User/Role/Permission management
            ("user.view", "View Users", "user", "view"),
            ("user.create", "Create Users", "user", "create"),
            ("user.edit", "Edit Users", "user", "edit"),
            ("user.delete", "Delete Users", "user", "delete"),
            ("user.manage", "Manage User Accounts", "user", "manage"),
            ("role.view", "View Roles", "role", "view"),
            ("role.create", "Create Roles", "role", "create"),
            ("role.edit", "Edit Roles", "role", "edit"),
            ("role.delete", "Delete Roles", "role", "delete"),
            ("role.manage", "Manage Roles", "role", "manage"),
            ("permission.view", "View Permissions", "permission", "view"),
            ("permission.assign", "Assign Permissions", "permission", "assign"),
            
            # System permissions
            ("system.audit.view", "View Audit Logs", "system", "view"),
            ("system.backup", "Manage Backups", "system", "backup"),
            ("system.maintenance", "System Maintenance", "system", "maintenance"),

            # AI & Insights permissions
            ("insight.view", "View AI Insights", "insight", "view"),
            ("insight.ask", "Use AI Assistant", "insight", "ask"),
            ("insight.search", "Use AI Search", "insight", "search"),
            ("insight.student.view", "AI Student Insights", "insight", "view"),
            ("insight.attendance.view", "AI Attendance Insights", "insight", "view"),
            ("insight.academic.view", "AI Academic Insights", "insight", "view"),
            ("insight.finance.view", "AI Finance Insights", "insight", "view"),
            ("insight.anomaly", "AI Anomaly Detection", "insight", "anomaly"),
            ("insight.communicate", "AI Communication Drafts", "insight", "communicate"),
        ]


class RolePermission(models.Model):
    """
    Assign permissions to roles within an institution.
    
    This allows customizing what each role can do per institution.
    """
    role = models.CharField(max_length=30, choices=Role.choices)
    permission = models.ForeignKey(
        Permission,
        on_delete=models.CASCADE,
        related_name="role_permissions",
    )
    institution = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="role_permissions",
    )
    granted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_role_permissions",
    )
    granted_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ["role", "permission__category", "permission__action"]
        constraints = [
            models.UniqueConstraint(
                fields=["role", "permission", "institution"],
                name="unique_role_permission_per_institution",
            ),
        ]
        indexes = [
            models.Index(fields=["role", "institution"], name="roleperm_role_inst_idx"),
        ]
    
    def __str__(self):
        return f"{self.role} -> {self.permission.codename} @ {self.institution.name}"


class UserPermission(models.Model):
    """
    User-specific permission overrides.
    
    Allows granting or denying specific permissions to individual users
    beyond their role-based permissions.
    """
    EFFECT_CHOICES = [
        ("allow", "Allow"),
        ("deny", "Deny"),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="custom_user_permissions",
    )
    permission = models.ForeignKey(
        Permission,
        on_delete=models.CASCADE,
        related_name="user_permissions",
    )
    institution = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="user_permissions",
    )
    effect = models.CharField(max_length=10, choices=EFFECT_CHOICES, default="allow")
    reason = models.TextField(blank=True)
    granted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="granted_user_permissions",
    )
    granted_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ["-granted_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "permission", "institution"],
                name="unique_user_permission_per_institution",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "institution"], name="userperm_user_inst_idx"),
        ]
    
    def __str__(self):
        return f"{self.user.username} -> {self.permission.codename} ({self.effect}) @ {self.institution.name}"
    
    def is_active(self):
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        return True

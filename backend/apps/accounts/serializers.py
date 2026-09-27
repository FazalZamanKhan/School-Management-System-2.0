from django.db import IntegrityError
from rest_framework import serializers

from .models import (
    InstitutionMembership,
    Permission,
    Role,
    RoleAssignment,
    RolePermission,
    StaffAttendance,
    StaffAttendanceCorrection,
    StaffLeave,
    StaffProfile,
    User,
    UserPermission,
)


class RoleAssignmentSerializer(serializers.ModelSerializer):
    role_label = serializers.CharField(
        source="get_role_display",
        read_only=True,
    )

    class Meta:
        model = RoleAssignment
        fields = ["role", "role_label"]


class InstitutionMembershipSerializer(serializers.ModelSerializer):
    institution_name = serializers.CharField(
        source="institution.name",
        read_only=True,
    )
    roles = RoleAssignmentSerializer(
        source="role_assignments",
        many=True,
        read_only=True,
    )

    class Meta:
        model = InstitutionMembership
        fields = [
            "id",
            "institution",
            "institution_name",
            "status",
            "joined_at",
            "roles",
        ]


class UserSerializer(serializers.ModelSerializer):
    memberships = InstitutionMembershipSerializer(
        many=True,
        read_only=True,
    )
    primary_role = serializers.CharField(
        read_only=True,
    )
    primary_institution = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()
    student_profile_id = serializers.SerializerMethodField()
    teacher_profile_id = serializers.SerializerMethodField()

    # Role/power fields are never writable through this serializer.
    is_superuser = serializers.BooleanField(read_only=True)

    # Surfaced so the SPA can force a password change on first login with a
    # system-generated temporary password.
    must_change_password = serializers.BooleanField(read_only=True)

    # Surfaced so the SPA can prompt for email verification on first login.
    email_verified = serializers.BooleanField(read_only=True)
    email_verified_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "phone",
            "first_name",
            "last_name",
            "photo",
            "photo_url",
            "is_staff",
            "is_superuser",
            "must_change_password",
            "email_verified",
            "email_verified_at",
            "primary_role",
            "primary_institution",
            "student_profile_id",
            "teacher_profile_id",
            "memberships",
        ]

    def get_primary_institution(self, obj):
        institution = obj.primary_institution
        return institution.name if institution else None

    def get_photo_url(self, obj):
        request = self.context.get("request")

        if obj.photo:
            url = obj.photo.url
            return request.build_absolute_uri(url) if request else url

        return None

    def get_student_profile_id(self, obj):
        profile = getattr(obj, "student_profile", None)
        return profile.id if profile else None

    def get_teacher_profile_id(self, obj):
        profile = getattr(obj, "teacher_profile", None)
        return profile.id if profile else None


class StaffProfileSerializer(serializers.ModelSerializer):
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = StaffProfile
        fields = [
            "id",
            "employee_number",
            "designation",
            "department",
            "joining_date",
            "status",
            "photo_url",
            "created_at",
            "updated_at",
        ]

    def get_photo_url(self, obj):
        request = self.context.get("request")

        if obj.photo:
            url = obj.photo.url
            return request.build_absolute_uri(url) if request else url

        return None


class UserProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()
    primary_role = serializers.CharField(read_only=True)
    primary_institution = serializers.SerializerMethodField()
    staff_profile = StaffProfileSerializer(read_only=True)
    memberships = InstitutionMembershipSerializer(
        many=True,
        read_only=True,
    )
    student_profile_id = serializers.SerializerMethodField()
    teacher_profile_id = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "full_name",
            "email",
            "phone",
            "photo_url",
            "primary_role",
            "primary_institution",
            "staff_profile",
            "memberships",
            "student_profile_id",
            "teacher_profile_id",
        ]

    def get_full_name(self, obj):
        return obj.get_full_name() or obj.username

    def get_photo_url(self, obj):
        request = self.context.get("request")

        if obj.photo:
            url = obj.photo.url
            return request.build_absolute_uri(url) if request else url

        staff = getattr(obj, "staff_profile", None)

        if staff and staff.photo:
            url = staff.photo.url
            return request.build_absolute_uri(url) if request else url

        return None

    def get_primary_institution(self, obj):
        institution = obj.primary_institution
        return institution.name if institution else None

    def get_student_profile_id(self, obj):
        profile = getattr(obj, "student_profile", None)
        return profile.id if profile else None

    def get_teacher_profile_id(self, obj):
        profile = getattr(obj, "teacher_profile", None)
        return profile.id if profile else None


class StaffProfileCRUDSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    employee_number = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    photo_url = serializers.SerializerMethodField()

    create_account = serializers.BooleanField(
        write_only=True,
        required=False,
        default=True,
    )

    username = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        allow_null=True,
        style={"input_type": "password"},
    )

    linked_username = serializers.SerializerMethodField()

    generated_password = serializers.SerializerMethodField()

    class Meta:
        model = StaffProfile
        fields = [
            "id",
            "employee_number",
            "user",
            "membership",
            "primary_campus",
            "linked_username",
            "generated_password",
            "photo",
            "photo_url",
            "first_name",
            "last_name",
            "full_name",
            "gender",
            "date_of_birth",
            "phone",
            "email",
            "designation",
            "department",
            "joining_date",
            "status",
            "create_account",
            "username",
            "password",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "full_name",
            "photo_url",
            "linked_username",
            "generated_password",
            "created_at",
            "updated_at",
        ]

    def get_full_name(self, obj):
        return obj.full_name

    def get_linked_username(self, obj):
        return obj.user.username if obj.user_id else None

    def get_generated_password(self, obj):
        return getattr(self, "_generated_password", None)

    def _resolve_school(self, staff=None):
        from apps.schools.models import School

        request = self.context.get("request")
        active_institution = getattr(request, "institution", None) if request else None
        return (
            active_institution
            or (staff.institution if staff is not None else None)
            or School.objects.filter(status="active").order_by("id").first()
            or School.objects.first()
        )

    def _ensure_employee_number(self, validated_data, staff=None):
        from apps.schools.services import next_entity_code
        from .models import StaffProfile

        current = (validated_data.get("employee_number") or "").strip()
        if current or (staff is not None and staff.employee_number):
            return current or staff.employee_number

        school = self._resolve_school(staff)
        return next_entity_code(school, "EMP", StaffProfile, "employee_number")

    def _build_user_account(self, staff, username, password):
        from apps.accounts.services import (
            create_user_with_username,
            role_for_designation,
        )
        from apps.schools.models import School

        # Prefer the request's active institution (correct school scoping);
        # fall back to the profile's own institution, then the first active
        # school only when no context is available.
        request = self.context.get("request")
        active_institution = getattr(request, "institution", None) if request else None
        school = (
            active_institution
            or staff.institution
            or School.objects.filter(status="active").order_by("id").first()
            or School.objects.first()
        )

        base = username or staff.employee_number
        user, _candidate, generated = create_user_with_username(
            base,
            institution=(school if school is not None else None),
            email=(staff.email or "").strip(),
            password=password or None,
            first_name=staff.first_name,
            last_name=staff.last_name,
        )

        if school is not None:
            membership, _ = InstitutionMembership.objects.get_or_create(
                user=user,
                institution=school,
                defaults={"status": "active"},
            )
            RoleAssignment.objects.get_or_create(
                membership=membership,
                role=role_for_designation(staff.designation),
            )

        return user, generated

    def create(self, validated_data):
        create_account = bool(validated_data.pop("create_account", False))
        username = validated_data.pop("username", "") or None
        password = validated_data.pop("password", "") or None

        validated_data["employee_number"] = self._ensure_employee_number(
            validated_data
        )

        staff = StaffProfile(**validated_data)
        try:
            staff.save()
        except IntegrityError:
            raise serializers.ValidationError(
                {
                    "employee_number": [
                        "A staff member with this employee number already exists."
                    ]
                }
            )

        if create_account:
            try:
                user, generated = self._build_user_account(staff, username, password)
            except IntegrityError:
                staff.delete()
                raise serializers.ValidationError(
                    {
                        "non_field_errors": [
                            "Could not create the login account: the username or "
                            "email is already in use."
                        ]
                    }
                )

            staff.user = user
            staff.save(update_fields=["user"])
            self._generated_password = generated

        return staff

    def update(self, instance, validated_data):
        create_account = bool(validated_data.pop("create_account", False))
        username = validated_data.pop("username", "") or None
        password = validated_data.pop("password", "") or None

        validated_data["employee_number"] = self._ensure_employee_number(
            validated_data, instance
        )

        for field, value in validated_data.items():
            setattr(instance, field, value)

        try:
            instance.save()
        except IntegrityError:
            raise serializers.ValidationError(
                {
                    "employee_number": [
                        "A staff member with this employee number already exists."
                    ]
                }
            )

        if create_account:
            if instance.user_id is None:
                try:
                    user, generated = self._build_user_account(
                        instance, username, password
                    )
                except IntegrityError:
                    raise serializers.ValidationError(
                        {
                            "non_field_errors": [
                                "Could not create the login account: the username "
                                "or email is already in use."
                            ]
                        }
                    )

                instance.user = user
                instance.save(update_fields=["user"])
                self._generated_password = generated
            else:
                user = instance.user
                user.first_name = instance.first_name
                user.last_name = instance.last_name
                if instance.email:
                    user.email = instance.email
                if password:
                    user.set_password(password)
                user.save()

        return instance

    def get_photo_url(self, obj):
        request = self.context.get("request")

        if obj.photo:
            url = obj.photo.url
            return request.build_absolute_uri(url) if request else url

        return None


class OptionalTimeField(serializers.TimeField):
    """TimeField that maps empty strings (blank form inputs) to None."""

    def to_internal_value(self, value):
        if value in ("", None):
            return None

        return super().to_internal_value(value)


class StaffAttendanceSerializer(serializers.ModelSerializer):
    staff = serializers.PrimaryKeyRelatedField(
        queryset=StaffProfile.objects.all(),
        required=False,
        allow_null=True,
        error_messages={
            "required": "Please select a staff member.",
            "incorrect_type": "Please select a valid staff member.",
        },
    )
    staff_name = serializers.CharField(
        source="staff.full_name",
        read_only=True,
    )
    staff_employee_number = serializers.CharField(
        source="staff.employee_number",
        read_only=True,
    )
    status_label = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )
    marked_by_name = serializers.SerializerMethodField()
    check_in = OptionalTimeField(required=False, allow_null=True)
    check_out = OptionalTimeField(required=False, allow_null=True)
    working_hours = serializers.SerializerMethodField()
    correction_count = serializers.IntegerField(
        source="corrections.count",
        read_only=True,
    )

    class Meta:
        model = StaffAttendance
        fields = [
            "id",
            "staff",
            "staff_name",
            "staff_employee_number",
            "date",
            "status",
            "status_label",
            "check_in",
            "check_out",
            "working_hours",
            "notes",
            "marked_by",
            "marked_by_name",
            "correction_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "marked_by", "created_at", "updated_at"]

    def get_marked_by_name(self, obj):
        if obj.marked_by is None:
            return None

        return (
            obj.marked_by.get_full_name()
            or obj.marked_by.username
        )

    def get_working_hours(self, obj):
        hours = obj.working_hours
        if hours is None:
            return None
        return round(hours.total_seconds() / 3600, 2)


class StaffAttendanceCorrectionSerializer(serializers.ModelSerializer):
    staff_name = serializers.CharField(
        source="staff.full_name",
        read_only=True,
    )
    corrected_by_name = serializers.SerializerMethodField()
    from_status_label = serializers.CharField(
        source="get_from_status_display",
        read_only=True,
    )
    to_status_label = serializers.CharField(
        source="get_to_status_display",
        read_only=True,
    )
    date = serializers.DateField(source="attendance.date", read_only=True)

    class Meta:
        model = StaffAttendanceCorrection
        fields = [
            "id",
            "attendance",
            "staff",
            "staff_name",
            "date",
            "from_status",
            "from_status_label",
            "to_status",
            "to_status_label",
            "from_check_in",
            "to_check_in",
            "from_check_out",
            "to_check_out",
            "reason",
            "corrected_by",
            "corrected_by_name",
            "corrected_at",
        ]
        read_only_fields = [
            "id",
            "attendance",
            "staff",
            "staff_name",
            "date",
            "from_status",
            "to_status",
            "from_check_in",
            "to_check_in",
            "from_check_out",
            "to_check_out",
            "reason",
            "corrected_by",
            "corrected_by_name",
            "corrected_at",
        ]

    def get_corrected_by_name(self, obj):
        if obj.corrected_by is None:
            return None
        return (
            obj.corrected_by.get_full_name()
            or obj.corrected_by.username
        )


class StaffLeaveSerializer(serializers.ModelSerializer):
    staff = serializers.PrimaryKeyRelatedField(
        queryset=StaffProfile.objects.all(),
        required=False,
        allow_null=True,
        error_messages={
            "required": "Please select a staff member.",
            "incorrect_type": "Please select a valid staff member.",
        },
    )
    staff_name = serializers.CharField(
        source="staff.full_name",
        read_only=True,
    )
    staff_employee_number = serializers.CharField(
        source="staff.employee_number",
        read_only=True,
    )
    leave_type_label = serializers.CharField(
        source="get_leave_type_display",
        read_only=True,
    )
    status_label = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )
    reviewed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = StaffLeave
        fields = [
            "id",
            "staff",
            "staff_name",
            "staff_employee_number",
            "leave_type",
            "leave_type_label",
            "start_date",
            "end_date",
            "days",
            "reason",
            "status",
            "status_label",
            "reviewed_by",
            "reviewed_by_name",
            "review_notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "days", "reviewed_by", "created_at", "updated_at"]

    def get_reviewed_by_name(self, obj):
        if obj.reviewed_by is None:
            return None

        return (
            obj.reviewed_by.get_full_name()
            or obj.reviewed_by.username
        )


class StaffLeaveActionSerializer(serializers.Serializer):
    """Approve or reject a staff leave request."""

    action = serializers.ChoiceField(
        choices=["approve", "reject"]
    )
    review_notes = serializers.CharField(
        required=False,
        allow_blank=True,
    )


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(required=False)
    email = serializers.EmailField(required=False)
    school_code = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(
        trim_whitespace=False,
        style={"input_type": "password"},
    )

    def validate(self, attrs):
        from django.contrib.auth import authenticate

        from .services import login_candidate_count

        username = attrs.get("username")
        email = attrs.get("email")

        identifier = username or email

        if not identifier:
            raise serializers.ValidationError(
                "Username or email is required."
            )

        school_code = attrs.get("school_code", "").strip().lower()
        request = self.context.get("request")
        host_institution = (
            getattr(request, "institution", None) if request else None
        )

        if school_code or host_institution is not None:
            # School-aware login: the lookup is scoped to the school, so the
            # same username in different schools is never ambiguous.
            auth_kwargs = dict(
                request=request,
                username=identifier,
                password=attrs.get("password"),
            )
            if school_code:
                auth_kwargs["school_code"] = school_code
            user = authenticate(**auth_kwargs)
        else:
            # Unscoped login (platform root / localhost, no school_code): refuse
            # ambiguity. A username shared by several schools must be logged in
            # with its school_code — EXCEPT for Platform Super Admin accounts,
            # which authenticate globally.
            candidate_count = login_candidate_count(identifier)

            if candidate_count > 1:
                # Check if there's a Platform Super Admin with this username
                # who should authenticate globally without school_code
                super_user = User.objects.filter(
                    username=identifier, is_superuser=True
                ).first()

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

        if user is None:
            raise serializers.ValidationError(
                "Invalid credentials."
            )

        if not user.is_active:
            raise serializers.ValidationError(
                "This account has been deactivated."
            )

        school_code = attrs.get("school_code", "").strip().lower()
        if school_code and not user.memberships.filter(
            institution__code__iexact=school_code,
            status="active",
        ).exists():
            raise serializers.ValidationError(
                "This account is not a member of the selected school."
            )

        attrs["user"] = user

        return attrs


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(
        style={"input_type": "password"},
        write_only=True,
    )
    new_password = serializers.CharField(
        min_length=8,
        style={"input_type": "password"},
        write_only=True,
    )
    confirm_password = serializers.CharField(
        style={"input_type": "password"},
        write_only=True,
    )

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                "The two passwords do not match."
            )

        _validate_password_policy(attrs["new_password"])

        return attrs


def _validate_password_policy(password):
    """Run the configured Django validators (no user attribute checks)."""
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import (
        ValidationError as DjangoValidationError,
    )

    try:
        validate_password(password)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({"new_password": exc.messages})


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        return value.lower().strip()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()

    new_password = serializers.CharField(
        min_length=8,
        write_only=True,
        style={"input_type": "password"},
    )

    confirm_password = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
    )

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(
                "The two passwords do not match."
            )

        _validate_password_policy(attrs["new_password"])

        return attrs


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = [
            "id",
            "codename",
            "name",
            "description",
            "action",
            "category",
            "is_system",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class RolePermissionSerializer(serializers.ModelSerializer):
    permission_detail = PermissionSerializer(source="permission", read_only=True)
    role_label = serializers.CharField(source="get_role_display", read_only=True)
    institution_name = serializers.CharField(source="institution.name", read_only=True)
    granted_by_name = serializers.CharField(source="granted_by.username", read_only=True)
    
    class Meta:
        model = RolePermission
        fields = [
            "id",
            "role",
            "role_label",
            "permission",
            "permission_detail",
            "institution",
            "institution_name",
            "granted_by",
            "granted_by_name",
            "granted_at",
        ]
        read_only_fields = ["id", "granted_at"]


class RolePermissionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = RolePermission
        fields = [
            "role",
            "permission",
            "institution",
        ]


class UserPermissionSerializer(serializers.ModelSerializer):
    permission_detail = PermissionSerializer(source="permission", read_only=True)
    institution_name = serializers.CharField(source="institution.name", read_only=True)
    granted_by_name = serializers.CharField(source="granted_by.username", read_only=True)
    user_name = serializers.CharField(source="user.username", read_only=True)
    is_active = serializers.SerializerMethodField()
    
    class Meta:
        model = UserPermission
        fields = [
            "id",
            "user",
            "user_name",
            "permission",
            "permission_detail",
            "institution",
            "institution_name",
            "effect",
            "reason",
            "granted_by",
            "granted_by_name",
            "granted_at",
            "expires_at",
            "is_active",
        ]
        read_only_fields = ["id", "granted_at", "is_active"]
    
    def get_is_active(self, obj):
        return obj.is_active()


class UserPermissionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPermission
        fields = [
            "user",
            "permission",
            "institution",
            "effect",
            "reason",
            "expires_at",
        ]
    
    def validate(self, attrs):
        user = attrs.get("user")
        institution = attrs.get("institution")
        if user and institution:
            if not user.memberships.filter(institution=institution, status="active").exists():
                raise serializers.ValidationError(
                    "User must have an active membership in this institution."
                )
        return attrs


class UserPermissionsSummarySerializer(serializers.Serializer):
    """Serializer for a user's effective permissions in an institution."""
    user_id = serializers.IntegerField()
    username = serializers.CharField()
    institution_id = serializers.IntegerField()
    institution_name = serializers.CharField()
    role_permissions = serializers.ListField(
        child=serializers.DictField(),
        help_text="Permissions granted via roles"
    )
    user_allow_permissions = serializers.ListField(
        child=serializers.DictField(),
        help_text="Permissions explicitly allowed for this user"
    )
    user_deny_permissions = serializers.ListField(
        child=serializers.DictField(),
        help_text="Permissions explicitly denied for this user"
    )
    effective_permissions = serializers.ListField(
        child=serializers.CharField(),
        help_text="All effective permission codenames"
    )


class SchoolAdminProvisionSerializer(serializers.Serializer):
    """Validates the School Admin block of the super-admin school-create API.

    All fields are optional — the provisioning service derives a per-school
    username, placeholder email and a secure temporary password when a field
    is left blank. Passwords are write-only and validated against the Django
    password validators before any account is created.
    """
    username = serializers.CharField(
        required=False, allow_blank=True, max_length=150,
        help_text="Admin username; unique within the new school.",
    )
    email = serializers.EmailField(
        required=False, allow_blank=True,
        help_text="Admin email; uniqueness is enforced school-wide.",
    )
    password = serializers.CharField(
        required=False, allow_blank=True, write_only=True,
        style={"input_type": "password"},
        help_text="Optional explicit password. Omit to generate a secure "
                  "temporary password (must-change).",
    )
    first_name = serializers.CharField(
        required=False, allow_blank=True, max_length=150,
    )
    last_name = serializers.CharField(
        required=False, allow_blank=True, max_length=150,
    )
    phone = serializers.CharField(
        required=False, allow_blank=True, max_length=20,
    )

    def validate_password(self, value):
        if not value:
            return value
        from django.contrib.auth.password_validation import (
            validate_password as django_validate_password,
        )
        from django.core.exceptions import ValidationError as DjangoValidationError

        try:
            django_validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from exc
        return value

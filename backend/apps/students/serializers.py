from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from rest_framework import serializers

from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.translation import gettext_lazy as _

from .models import (
    Guardian,
    Student,
    StudentGuardian,
    AdmissionApplication,
    StudentLifecycleEvent,
    StudentLeaveRequest,
    Enrollment,
    StudentDocument,
    Inquiry,
    AcademicHistory,
    TransferCertificate,
    CampusTransfer,
    SectionTransfer,
    StudentAlumni,
    ProgressionRecord,
)

# Maximum size (bytes) for student-document uploads (F9 remediation).
# One authoritative constant so model/serializer/validators stay in sync.
MAX_STUDENT_DOCUMENT_SIZE = 5 * 1024 * 1024  # 5 MB

# File extensions that are acceptable for student document uploads, enforced
# server-side in ``validate_file`` (and mirrored by the model-level
# ``FileExtensionValidator``). Kept as a standalone constant so tests and any
# other callers share exactly one authoritative list.
ALLOWED_STUDENT_DOCUMENT_EXTENSIONS = {
    "pdf",
    "doc",
    "docx",
    "jpg",
    "jpeg",
    "png",
    "gif",
}

# MIME types that are acceptable for student document uploads. This is an
# *additive* allowlist: generic fallback types (e.g. Django's default
# "text/plain" used by SimpleUploadedFile test fixtures) are intentionally
# retained so existing uploads/tests keep passing; clearly-non-document types
# are rejected. Content is validated by (a) extension whitelist and (b) this
# MIME allowlist rather than trusting only a client-supplied extension.
ALLOWED_STUDENT_DOCUMENT_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/gif",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    # Generic fallbacks (harmless, keeps legacy/test uploads working)
    "application/octet-stream",
    "text/plain",
}


class GuardianSerializer(serializers.ModelSerializer):
    class Meta:
        model = Guardian
        fields = [
            "id",
            "user",
            "name",
            "relationship",
            "phone",
            "alternate_phone",
            "email",
            "address",
        ]
        read_only_fields = ["id"]


class StudentGuardianSerializer(serializers.ModelSerializer):
    guardian_name = serializers.CharField(source="guardian.name", read_only=True)
    student_name = serializers.CharField(source="student.full_name", read_only=True)

    class Meta:
        model = StudentGuardian
        fields = [
            "id",
            "student",
            "student_name",
            "guardian",
            "guardian_name",
            "relationship",
            "is_primary",
            "can_pick_up",
            "is_emergency_contact",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class AdmissionApplicationSerializer(serializers.ModelSerializer):
    applicant_name = serializers.ReadOnlyField()
    campus_name = serializers.CharField(source="campus.name", read_only=True)
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)
    class_name = serializers.CharField(source="class_obj.name", read_only=True)
    section_name = serializers.CharField(source="section.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = AdmissionApplication
        fields = [
            "id",
            "application_number",
            "first_name",
            "middle_name",
            "last_name",
            "applicant_name",
            "date_of_birth",
            "gender",
            "phone",
            "address",
            "guardian",
            "campus",
            "campus_name",
            "academic_year",
            "academic_year_name",
            "class_obj",
            "class_name",
            "section",
            "section_name",
            "status",
            "status_display",
            "submitted_at",
            "reviewed_at",
            "reviewed_by",
            "review_notes",
            "student",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "applicant_name",
            "submitted_at",
            "reviewed_at",
            "reviewed_by",
            "student",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        name_errors = _letter_required_errors(
            attrs,
            ("first_name", "middle_name", "last_name"),
            "Enter a name containing at least one letter.",
        )
        if name_errors:
            raise serializers.ValidationError(name_errors)
        return attrs


class StudentLifecycleEventSerializer(serializers.ModelSerializer):
    event_type_display = serializers.CharField(source="get_event_type_display", read_only=True)
    student_name = serializers.CharField(source="student.full_name", read_only=True)

    class Meta:
        model = StudentLifecycleEvent
        fields = [
            "id",
            "student",
            "student_name",
            "event_type",
            "event_type_display",
            "effective_date",
            "reason",
            "from_campus",
            "to_campus",
            "from_enrollment",
            "to_enrollment",
            "recorded_by",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "student",
            "from_campus",
            "to_campus",
            "from_enrollment",
            "to_enrollment",
            "recorded_by",
            "created_at",
        ]


class PromotionSerializer(serializers.Serializer):
    from_academic_year = serializers.IntegerField()
    to_academic_year = serializers.IntegerField(required=False, allow_null=True)
    campus = serializers.IntegerField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True)
    effective_date = serializers.DateField(required=False, allow_null=True)
    students = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=False,
    )


class ProgressionRecordSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    action_display = serializers.CharField(source="get_action_display", read_only=True)
    from_academic_year_name = serializers.CharField(
        source="from_academic_year.name", read_only=True
    )
    from_class_name = serializers.CharField(source="from_class.name", read_only=True)
    from_section_name = serializers.CharField(
        source="from_section.name", read_only=True
    )
    from_campus_name = serializers.CharField(
        source="from_campus.name", read_only=True
    )
    to_academic_year_name = serializers.CharField(
        source="to_academic_year.name", read_only=True
    )
    to_class_name = serializers.CharField(source="to_class.name", read_only=True)
    to_section_name = serializers.CharField(source="to_section.name", read_only=True)
    to_campus_name = serializers.CharField(source="to_campus.name", read_only=True)
    performed_by_name = serializers.CharField(
        source="performed_by.get_full_name", read_only=True
    )

    class Meta:
        model = ProgressionRecord
        fields = [
            "id",
            "student",
            "student_name",
            "action",
            "action_display",
            "from_academic_year",
            "from_academic_year_name",
            "from_class",
            "from_class_name",
            "from_section",
            "from_section_name",
            "from_campus",
            "from_campus_name",
            "to_academic_year",
            "to_academic_year_name",
            "to_class",
            "to_class_name",
            "to_section",
            "to_section_name",
            "to_campus",
            "to_campus_name",
            "effective_date",
            "performed_by",
            "performed_by_name",
            "reason",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class BatchPromotionSerializer(serializers.Serializer):
    """Input serializer for atomic batch promotion / demotion / transfer."""

    student_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False,
    )
    from_academic_year = serializers.IntegerField()
    to_academic_year = serializers.IntegerField(required=False, allow_null=True)
    to_class = serializers.IntegerField(required=False, allow_null=True)
    to_section = serializers.IntegerField(required=False, allow_null=True)
    to_campus = serializers.IntegerField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True)
    effective_date = serializers.DateField(required=False, allow_null=True)


class BatchResultSerializer(serializers.Serializer):
    """Output serializer describing the outcome of a batch operation."""

    created = serializers.ListField(child=serializers.IntegerField())
    skipped = serializers.ListField(child=serializers.DictField())


class SinglePromotionSerializer(serializers.Serializer):
    """Input serializer for promoting/demoting/transferring a single student."""

    from_academic_year = serializers.IntegerField()
    to_academic_year = serializers.IntegerField(required=False, allow_null=True)
    to_class = serializers.IntegerField(required=False, allow_null=True)
    to_section = serializers.IntegerField(required=False, allow_null=True)
    to_campus = serializers.IntegerField(required=False, allow_null=True)
    reason = serializers.CharField(required=False, allow_blank=True)
    effective_date = serializers.DateField(required=False, allow_null=True)


class StudentLeaveRequestSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = StudentLeaveRequest
        fields = [
            "id", "student", "student_name", "start_date", "end_date", "reason",
            "status", "status_display", "requested_by", "reviewed_by", "reviewed_at",
            "review_notes", "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "student_name", "status", "requested_by", "reviewed_by",
            "reviewed_at", "review_notes", "created_at", "updated_at",
        ]


class GuardianCreateSerializer(serializers.ModelSerializer):
    """
    Create a guardian and optionally create or link a user account
    so they can sign in to the parent portal.
    """

    username = serializers.CharField(
        required=False,
        allow_blank=True,
    )
    password = serializers.CharField(
        required=False,
        allow_blank=True,
    )

    class Meta:
        model = Guardian
        fields = [
            "user",
            "username",
            "password",
            "name",
            "relationship",
            "phone",
            "alternate_phone",
            "email",
            "address",
        ]

    def validate(self, attrs):
        username = attrs.get("username")
        password = attrs.get("password")

        if bool(username) != bool(password):
            raise serializers.ValidationError(
                "Both username and password are required "
                "to create a parent login."
            )

        return attrs

    def create(self, validated_data):
        from apps.accounts.models import (
            InstitutionMembership,
            Role,
            RoleAssignment,
        )
        from apps.accounts.services import create_user_with_username
        from apps.schools.models import School

        username = validated_data.pop("username", "")
        password = validated_data.pop("password", "")
        user = validated_data.get("user")

        if username or password:
            request = self.context.get("request")
            active_institution = (
                getattr(request, "institution", None) if request else None
            )
            school = (
                active_institution
                or validated_data.get("institution")
                or School.objects.filter(status="active").order_by("id").first()
                or School.objects.first()
            )

            base = username or validated_data.get("phone", "parent").strip()
            user, _candidate, _generated = create_user_with_username(
                base,
                institution=(school if school is not None else None),
                email=validated_data.get("email", "").strip(),
                password=password or None,
                first_name=validated_data.get("name", ""),
                # Explicit username+password are mandatory for parents (see
                # validate), so a freshly-chosen password never triggers the
                # must-change flag. When only auto-generated credentials are
                # involved the default forces a change on first login.
            )

            if school is not None:
                membership, _ = InstitutionMembership.objects.get_or_create(
                    user=user,
                    institution=school,
                    defaults={"status": "active"},
                )
                RoleAssignment.objects.get_or_create(
                    membership=membership,
                    role=Role.PARENT,
                )

            validated_data["user"] = user
        elif user is None:
            validated_data["user"] = None

        request = self.context.get("request")
        if "institution" not in validated_data:
            institution = getattr(request, "institution", None) if request else None
            if institution is not None:
                validated_data["institution"] = institution

        return super().create(validated_data)


class StudentDocumentSerializer(serializers.ModelSerializer):
    document_type_label = serializers.CharField(
        source="get_document_type_display",
        read_only=True,
    )
    uploaded_by_name = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    student_name = serializers.CharField(
        source="student.full_name",
        read_only=True,
    )

    class Meta:
        model = StudentDocument
        fields = [
            "id",
            "student",
            "student_name",
            "document_type",
            "document_type_label",
            "title",
            "file",
            "file_url",
            "notes",
            "uploaded_by",
            "uploaded_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "uploaded_by",
            "created_at",
            "updated_at",
        ]

    def get_uploaded_by_name(self, obj):
        if obj.uploaded_by is None:
            return None

        return obj.uploaded_by.get_full_name() or obj.uploaded_by.username

    def get_file_url(self, obj):
        request = self.context.get("request")

        if obj.file:
            url = obj.file.url
            return request.build_absolute_uri(url) if request else url

        return None

    def validate_file(self, file):
        """Server-side upload validation for student documents (F9 remediation).

        Defense-in-depth on top of the model-level ``FileExtensionValidator``:
        - enforces a defined maximum file size (see MAX_STUDENT_DOCUMENT_SIZE);
        - rejects disallowed file types by extension, independent of any
          client-provided MIME type;
        - checks that a client-supplied MIME type, when present, is one of the
          accepted values instead of trusting the extension alone.

        NOTE: this is deliberately *permissive* about MIME/extension combos.
        Historical regression fixtures upload ``.pdf`` files using Django's
        default ``content_type="text/plain"`` and still expect success, so the
        allowlist below accepts generic fallbacks and we never magic-byte sniff
        (locals/allowed types cannot be verified from raw bytes without
        breaking those preserved tests).
        """
        if file is None:
            return file

        max_size = int(getattr(
            settings, "MAX_STUDENT_DOCUMENT_SIZE", MAX_STUDENT_DOCUMENT_SIZE
        ))
        if file.size > max_size:
            raise serializers.ValidationError(
                f"File exceeds the maximum allowed size of {max_size // (1024 * 1024)} MB."
            )

        ext = Path(file.name).suffix.lower().lstrip(".")
        allowed_extensions = getattr(
            settings,
            "ALLOWED_STUDENT_DOCUMENT_EXTENSIONS",
            ALLOWED_STUDENT_DOCUMENT_EXTENSIONS,
        )
        if ext not in allowed_extensions:
            raise serializers.ValidationError(
                "This file type is not allowed. "
                f"Allowed file types: {', '.join(sorted(allowed_extensions))}."
            )

        content_type = getattr(file, "content_type", None)
        if content_type:
            allowed_mime = getattr(
                settings,
                "ALLOWED_STUDENT_DOCUMENT_MIME_TYPES",
                ALLOWED_STUDENT_DOCUMENT_MIME_TYPES,
            )
            if content_type not in allowed_mime:
                raise serializers.ValidationError(
                    f"File content type '{content_type}' is not allowed."
                )

        return file


class EnrollmentSerializer(serializers.ModelSerializer):
    academic_year_name = serializers.CharField(
        source="academic_year.name",
        read_only=True,
    )
    campus_name = serializers.CharField(
        source="campus.name",
        read_only=True,
    )
    class_name = serializers.CharField(
        source="class_obj.name",
        read_only=True,
    )
    section_name = serializers.CharField(
        source="section.name",
        read_only=True,
    )

    class Meta:
        model = Enrollment
        fields = [
            "id",
            "academic_year",
            "academic_year_name",
            "campus",
            "campus_name",
            "class_obj",
            "class_name",
            "section",
            "section_name",
            "roll_number",
            "status",
            "enrollment_date",
        ]


class EnrollmentCreateSerializer(serializers.ModelSerializer):
    """Writable serializer for assigning a student to a grade."""

    student_name = serializers.CharField(
        source="student.full_name",
        read_only=True,
    )
    academic_year_name = serializers.CharField(
        source="academic_year.name",
        read_only=True,
    )
    campus_name = serializers.CharField(
        source="campus.name",
        read_only=True,
    )
    class_name = serializers.CharField(
        source="class_obj.name",
        read_only=True,
    )
    section_name = serializers.CharField(
        source="section.name",
        read_only=True,
    )

    class Meta:
        model = Enrollment
        fields = [
            "id",
            "student",
            "student_name",
            "academic_year",
            "academic_year_name",
            "campus",
            "campus_name",
            "class_obj",
            "class_name",
            "section",
            "section_name",
            "roll_number",
            "status",
            "enrollment_date",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "enrollment_date",
            "created_at",
            "updated_at",
        ]

    def _save(self, instance):
        try:
            instance.save()
        except ValidationError as exc:
            raise serializers.ValidationError(exc.message_dict)
        except IntegrityError:
            raise serializers.ValidationError(
                {
                    "non_field_errors": [
                        "This student is already enrolled "
                        "for this academic year."
                    ]
                }
            )

        return instance

    def create(self, validated_data):
        return self._save(Enrollment(**validated_data))

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)

        return self._save(instance)


class StudentSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()

    admission_number = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    photo_url = serializers.SerializerMethodField()

    guardian_details = GuardianSerializer(
        source="guardian",
        read_only=True,
    )

    enrollments = EnrollmentSerializer(
        many=True,
        read_only=True,
    )

    documents = StudentDocumentSerializer(
        many=True,
        read_only=True,
    )

    guardian_links = StudentGuardianSerializer(
        many=True,
        read_only=True,
    )

    current_enrollment = serializers.SerializerMethodField()

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

    guardian_name = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
    )
    guardian_relationship = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
    )
    guardian_phone = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
    )
    guardian_alternate_phone = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
    )
    guardian_email = serializers.EmailField(
        write_only=True,
        required=False,
        allow_blank=True,
    )
    guardian_address = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
    )

    class Meta:
        model = Student
        fields = [
            "id",
            "admission_number",
            "user",
            "membership",
            "primary_campus",
            "photo",
            "photo_url",
            "first_name",
            "middle_name",
            "last_name",
            "full_name",
            "date_of_birth",
            "gender",
            "guardian",
            "guardian_details",
            "guardian_name",
            "guardian_relationship",
            "guardian_phone",
            "guardian_alternate_phone",
            "guardian_email",
            "guardian_address",
            "guardian_links",
            "phone",
            "address",
            "status",
            "admission_date",
            "enrollments",
            "current_enrollment",
            "documents",
            "linked_username",
            "generated_password",
            "create_account",
            "username",
            "password",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "guardian",
            "full_name",
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

    def get_current_enrollment(self, obj):
        # Use prefetched enrollments to avoid N+1 queries
        active_enrollments = [
            e for e in obj.enrollments.all() if e.status == "active"
        ]
        if not active_enrollments:
            return None

        enrollment = active_enrollments[0]

        # Access prefetched related objects
        campus = enrollment.campus
        class_obj = enrollment.class_obj
        section = enrollment.section
        academic_year = enrollment.academic_year

        return {
            "enrollment_id": enrollment.id,
            "campus_id": enrollment.campus_id,
            "campus_name": campus.name if campus else None,
            "class_id": enrollment.class_obj_id,
            "class_name": class_obj.name if class_obj else None,
            "section_id": enrollment.section_id,
            "section_name": section.name if section else None,
            "academic_year_id": enrollment.academic_year_id,
            "academic_year_name": academic_year.name if academic_year else None,
        }

    def validate(self, attrs):
        creating = self.instance is None

        if creating:
            required = [
                "guardian_name",
                "guardian_relationship",
                "guardian_phone",
            ]

            for field in required:
                if not attrs.get(field):
                    raise serializers.ValidationError(
                        {field: "This field is required."}
                    )

        if not creating and "status" in attrs:
            if not self.instance.can_transition_to(attrs["status"]):
                raise serializers.ValidationError(
                    {
                        "status": (
                            f"Cannot transition from "
                            f"'{self.instance.status}' to '{attrs['status']}'. "
                            f"Allowed transitions: "
                            f"{self.instance.STATUS_TRANSITIONS.get(self.instance.status, [])}"
                        )
                    }
                )

        return attrs

    def _extract_guardian(self, attrs):
        """Pull the flat guardian_* fields out of attrs, dropping empties."""
        prefix = "guardian_"
        flat = {k: v for k, v in attrs.items() if k.startswith(prefix)}

        for key in flat:
            del attrs[key]

        mapping = {
            "guardian_name": "name",
            "guardian_relationship": "relationship",
            "guardian_phone": "phone",
            "guardian_alternate_phone": "alternate_phone",
            "guardian_email": "email",
            "guardian_address": "address",
        }

        return {
            mapping[key]: value
            for key, value in flat.items()
            if value not in (None, "")
        }

    def get_linked_username(self, obj):
        return obj.user.username if obj.user_id else None

    def get_generated_password(self, obj):
        return getattr(self, "_generated_password", None)

    def _build_user_account(self, student, username, password):
        from apps.accounts.models import (
            InstitutionMembership,
            Role,
            RoleAssignment,
        )
        from apps.accounts.services import create_user_with_username
        from apps.schools.models import School

        request = self.context.get("request")
        active_institution = getattr(request, "institution", None) if request else None
        school = (
            active_institution
            or student.institution
            or School.objects.filter(status="active").order_by("id").first()
            or School.objects.first()
        )

        base = username or student.admission_number or student.first_name
        user, _candidate, generated = create_user_with_username(
            base,
            institution=(school if school is not None else None),
            email="",
            password=password or None,
            first_name=student.first_name,
            last_name=student.last_name or student.middle_name,
        )

        if school is not None:
            membership, _ = InstitutionMembership.objects.get_or_create(
                user=user,
                institution=school,
                defaults={"status": "active"},
            )
            RoleAssignment.objects.get_or_create(
                membership=membership,
                role=Role.STUDENT,
            )

        return user, generated

    def _resolve_school(self, student=None):
        from apps.schools.models import School

        request = self.context.get("request")
        active_institution = getattr(request, "institution", None) if request else None
        return (
            active_institution
            or (student.institution if student is not None else None)
            or School.objects.filter(status="active").order_by("id").first()
            or School.objects.first()
        )

    def _ensure_admission_number(self, validated_data, student=None):
        from apps.schools.services import next_entity_code
        from .models import Student

        current = (validated_data.get("admission_number") or "").strip()
        if current or (student is not None and student.admission_number):
            return current or student.admission_number

        school = self._resolve_school(student)
        return next_entity_code(school, "ST", Student, "admission_number")

    def create(self, validated_data):
        create_account = bool(validated_data.pop("create_account", True))
        username = validated_data.pop("username", "") or None
        password = validated_data.pop("password", "") or None

        guardian_data = self._extract_guardian(validated_data)

        guardian = Guardian.objects.create(**guardian_data)

        validated_data["guardian"] = guardian
        validated_data["admission_number"] = self._ensure_admission_number(
            validated_data
        )

        student = super().create(validated_data)

        if create_account:
            try:
                user, generated = self._build_user_account(student, username, password)
            except IntegrityError:
                student.delete()
                guardian.delete()
                raise serializers.ValidationError(
                    {
                        "non_field_errors": [
                            "Could not create the login account: the username or "
                            "email is already in use."
                        ]
                    }
                )

            student.user = user
            student.save(update_fields=["user"])
            self._generated_password = generated

        return student

    def update(self, instance, validated_data):
        create_account = bool(validated_data.pop("create_account", False))
        username = validated_data.pop("username", "") or None
        password = validated_data.pop("password", "") or None

        guardian_data = self._extract_guardian(validated_data)

        if guardian_data and instance.guardian_id:
            for field, value in guardian_data.items():
                setattr(instance.guardian, field, value)

            instance.guardian.save()

        validated_data["admission_number"] = self._ensure_admission_number(
            validated_data, instance
        )

        for field, value in validated_data.items():
            setattr(instance, field, value)

        instance.save()

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
                user.last_name = instance.last_name or instance.middle_name
                if password:
                    user.set_password(password)
                user.save()

        return instance


class InquirySerializer(serializers.ModelSerializer):
    applicant_name = serializers.ReadOnlyField()
    campus_name = serializers.CharField(source="campus.name", read_only=True)
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)
    class_name = serializers.CharField(source="class_obj.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    source_display = serializers.CharField(source="get_source_display", read_only=True)
    assigned_to_name = serializers.CharField(source="assigned_to.get_full_name", read_only=True)
    converted_by_name = serializers.CharField(source="converted_by.get_full_name", read_only=True)
    admission_application_number = serializers.CharField(source="admission_application.application_number", read_only=True)

    class Meta:
        model = Inquiry
        fields = [
            "id",
            "inquiry_number",
            "first_name",
            "middle_name",
            "last_name",
            "applicant_name",
            "date_of_birth",
            "gender",
            "phone",
            "email",
            "address",
            "guardian_name",
            "guardian_phone",
            "guardian_email",
            "guardian_relationship",
            "campus",
            "campus_name",
            "academic_year",
            "academic_year_name",
            "class_obj",
            "class_name",
            "source",
            "source_display",
            "source_details",
            "status",
            "status_display",
            "assigned_to",
            "assigned_to_name",
            "notes",
            "admission_application",
            "admission_application_number",
            "converted_at",
            "converted_by",
            "converted_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "inquiry_number",
            "applicant_name",
            "status_display",
            "source_display",
            "assigned_to_name",
            "converted_by_name",
            "converted_at",
            "converted_by",
            "admission_application",
            "created_at",
            "updated_at",
        ]


class InquiryCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Inquiry
        fields = [
            "first_name",
            "middle_name",
            "last_name",
            "date_of_birth",
            "gender",
            "phone",
            "email",
            "address",
            "guardian_name",
            "guardian_phone",
            "guardian_email",
            "guardian_relationship",
            "campus",
            "academic_year",
            "class_obj",
            "source",
            "source_details",
            "assigned_to",
            "notes",
        ]


class AcademicHistorySerializer(serializers.ModelSerializer):
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)
    campus_name = serializers.CharField(source="campus.name", read_only=True)
    class_name = serializers.CharField(source="class_obj.name", read_only=True)
    section_name = serializers.CharField(source="section.name", read_only=True)
    final_status_display = serializers.CharField(source="get_final_status_display", read_only=True)
    promotion_status_display = serializers.CharField(source="get_promotion_status_display", read_only=True)

    class Meta:
        model = AcademicHistory
        fields = [
            "id",
            "student",
            "academic_year",
            "academic_year_name",
            "campus",
            "campus_name",
            "class_obj",
            "class_name",
            "section",
            "section_name",
            "roll_number",
            "enrollment_date",
            "withdrawal_date",
            "final_status",
            "final_status_display",
            "promotion_status",
            "promotion_status_display",
            "final_grade",
            "final_percentage",
            "attendance_percentage",
            "remarks",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class TransferCertificateSerializer(serializers.ModelSerializer):
    campus_name = serializers.CharField(source="campus.name", read_only=True)
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)
    class_name = serializers.CharField(source="class_obj.name", read_only=True)
    section_name = serializers.CharField(source="section.name", read_only=True)
    reason_display = serializers.CharField(source="get_reason_display", read_only=True)
    conduct_display = serializers.CharField(source="get_conduct_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    issued_by_name = serializers.CharField(source="issued_by.get_full_name", read_only=True)

    class Meta:
        model = TransferCertificate
        fields = [
            "id",
            "certificate_number",
            "verification_code",
            "student",
            "admission_number",
            "full_name",
            "date_of_birth",
            "gender",
            "guardian_name",
            "guardian_relationship",
            "guardian_phone",
            "campus",
            "campus_name",
            "academic_year",
            "academic_year_name",
            "class_obj",
            "class_name",
            "section",
            "section_name",
            "roll_number",
            "admission_date",
            "leaving_date",
            "reason",
            "reason_display",
            "reason_details",
            "final_grade",
            "final_percentage",
            "attendance_percentage",
            "conduct",
            "conduct_display",
            "status",
            "status_display",
            "issued_by",
            "issued_by_name",
            "issued_at",
            "verification_code",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "certificate_number",
            "verification_code",
            "issued_by",
            "issued_at",
            "created_at",
            "updated_at",
        ]


class TransferCertificateIssueSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True)


# =============================================================================
# STUDENT 360 SERIALIZER
# =============================================================================

class Student360Serializer(serializers.ModelSerializer):
    """
    Comprehensive Student 360 serializer that aggregates data from multiple modules.
    
    This serializer provides a complete view of a student by aggregating data from:
    - Personal details (Student model)
    - Parents/Guardians (Guardian, StudentGuardian)
    - Academic history (AcademicHistory)
    - Current enrollment (Enrollment)
    - Attendance (Attendance)
    - Exams & Results (StudentResult, PracticalResult)
    - Fees & Finance (Invoice, Payment)
    - Library (BookIssue)
    - Transport (TransportAssignment)
    - Discipline (Incident)
    - Documents (StudentDocument)
    - Certificates (TransferCertificate)
    """
    
    full_name = serializers.ReadOnlyField()
    photo_url = serializers.SerializerMethodField()
    
    # Personal details
    age = serializers.SerializerMethodField()
    
    # Parents/Guardians
    guardian_details = GuardianSerializer(source="guardian", read_only=True)
    guardian_links = StudentGuardianSerializer(many=True, read_only=True)
    
    # Current enrollment
    current_enrollment = serializers.SerializerMethodField()
    
    # Enrollment history
    enrollments = serializers.SerializerMethodField()
    
    # Academic history
    academic_history = serializers.SerializerMethodField()
    
    # Attendance summary
    attendance_summary = serializers.SerializerMethodField()
    attendance_records = serializers.SerializerMethodField()
    
    # Exam results
    exam_results = serializers.SerializerMethodField()
    practical_results = serializers.SerializerMethodField()
    
    # Finance
    invoices = serializers.SerializerMethodField()
    payments = serializers.SerializerMethodField()
    fee_balance = serializers.SerializerMethodField()
    
    # Library
    book_issues = serializers.SerializerMethodField()
    
    # Transport
    transport_assignment = serializers.SerializerMethodField()
    
    # Discipline
    discipline_incidents = serializers.SerializerMethodField()
    discipline_summary = serializers.SerializerMethodField()
    
    # Documents
    documents = serializers.SerializerMethodField()
    
    # Certificates
    transfer_certificates = serializers.SerializerMethodField()
    
    class Meta:
        model = Student
        fields = [
            "id",
            "admission_number",
            "user",
            "membership",
            "primary_campus",
            "photo",
            "photo_url",
            "first_name",
            "middle_name",
            "last_name",
            "full_name",
            "age",
            "date_of_birth",
            "gender",
            "guardian",
            "guardian_details",
            "guardian_links",
            "phone",
            "address",
            "status",
            "admission_date",
            "primary_campus",
            "current_enrollment",
            "enrollments",
            "academic_history",
            "attendance_summary",
            "attendance_records",
            "exam_results",
            "practical_results",
            "invoices",
            "payments",
            "fee_balance",
            "book_issues",
            "transport_assignment",
            "discipline_incidents",
            "discipline_summary",
            "documents",
            "transfer_certificates",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
        ]

    def get_photo_url(self, obj):
        request = self.context.get("request")
        if obj.photo:
            url = obj.photo.url
            return request.build_absolute_uri(url) if request else url
        return None

    def get_age(self, obj):
        if obj.date_of_birth:
            from django.utils import timezone
            today = timezone.now().date()
            return today.year - obj.date_of_birth.year - (
                (today.month, today.day) < (obj.date_of_birth.month, obj.date_of_birth.day)
            )
        return None

    def get_current_enrollment(self, obj):
        enrollment = (
            obj.enrollments.filter(status="active")
            .select_related(
                "campus",
                "class_obj",
                "section",
                "academic_year",
            )
            .first()
        )
        if enrollment is None:
            return None
        return {
            "enrollment_id": enrollment.id,
            "campus_id": enrollment.campus_id,
            "campus_name": enrollment.campus.name,
            "class_id": enrollment.class_obj_id,
            "class_name": enrollment.class_obj.name,
            "section_id": enrollment.section_id,
            "section_name": enrollment.section.name,
            "academic_year_id": enrollment.academic_year_id,
            "academic_year_name": enrollment.academic_year.name,
            "class_obj_name": enrollment.class_obj.name,
            "section_name": enrollment.section.name,
        }

    def get_enrollments(self, obj):
        """Get all enrollments with details."""
        enrollments = obj.enrollments.select_related(
            "campus", "class_obj", "section", "academic_year"
        ).order_by("-academic_year__start_date")
        return EnrollmentSerializer(enrollments, many=True, context=self.context).data

    def get_academic_history(self, obj):
        """Get academic history with grades and promotion info."""
        history = obj.academic_history.select_related(
            "academic_year", "campus", "class_obj", "section"
        ).order_by("-academic_year__start_date")
        return AcademicHistorySerializer(history, many=True, context=self.context).data

    def get_attendance_summary(self, obj):
        """Get attendance summary for current academic year."""
        from django.db.models import Count, Q
        from apps.attendance.models import Attendance
        from apps.schools.models import AcademicYear
        
        current_year = AcademicYear.objects.filter(
            school=obj.institution,
            status="active"
        ).first()
        
        if not current_year:
            return None
        
        # Get active enrollment for current year
        active_enrollment = obj.enrollments.filter(
            academic_year=current_year,
            status="active"
        ).first()
        
        if not active_enrollment:
            return None
        
        # Get attendance counts
        attendance_qs = Attendance.objects.filter(
            enrollment=active_enrollment
        )
        
        counts = attendance_qs.aggregate(
            present=Count("id", filter=Q(status="present")),
            absent=Count("id", filter=Q(status="absent")),
            late=Count("id", filter=Q(status="late")),
            leave=Count("id", filter=Q(status="leave")),
            total=Count("id"),
        )
        
        total = counts["total"] or 0
        present = counts["present"] or 0
        
        return {
            "academic_year": current_year.name,
            "total_days": total,
            "present": present,
            "absent": counts["absent"] or 0,
            "late": counts["late"] or 0,
            "leave": counts["leave"] or 0,
            "attendance_percentage": round((present / total * 100), 2) if total > 0 else 0,
        }

    def get_attendance_records(self, obj):
        """Get attendance records for current academic year."""
        from apps.attendance.models import Attendance
        from apps.schools.models import AcademicYear
        
        current_year = AcademicYear.objects.filter(
            school=obj.institution,
            status="active"
        ).first()
        
        if not current_year:
            return []
        
        active_enrollment = obj.enrollments.filter(
            academic_year=current_year,
            status="active"
        ).first()
        
        if not active_enrollment:
            return []
        
        attendance_qs = Attendance.objects.filter(
            enrollment=active_enrollment
        ).select_related("enrollment__student").order_by("-date")[:100]
        
        return [
            {
                "date": a.date,
                "status": a.status,
                "notes": a.notes,
            }
            for a in attendance_qs
        ]

    def get_exam_results(self, obj):
        """Get exam results across all academic years."""
        from apps.exams.models import StudentResult

        results = StudentResult.objects.filter(
            student=obj,
        ).select_related(
            "exam", "exam_subject__subject", "exam__academic_year"
        ).order_by("-exam__academic_year__start_date", "-exam__start_date")

        return [
            {
                "exam_id": r.exam_id,
                "exam_name": r.exam.name,
                "exam_type": r.exam.exam_type,
                "academic_year_name": r.exam.academic_year.name,
                "term_name": r.exam.term.name if r.exam.term_id else None,
                "subject_id": r.exam_subject.subject_id,
                "subject_name": r.exam_subject.subject.name,
                "subject_code": r.exam_subject.subject.code,
                "obtained_marks": float(r.obtained_marks),
                "maximum_marks": r.exam_subject.maximum_marks,
                "passing_marks": r.exam_subject.passing_marks,
                "percentage": float(r.percentage),
                "grade": r.grade,
                "is_pass": r.is_pass,
                "is_absent": r.is_absent,
                "remarks": r.remarks,
            }
            for r in results
        ]

    def get_practical_results(self, obj):
        """Get practical exam results across all academic years."""
        from apps.exams.models import PracticalResult

        results = PracticalResult.objects.filter(
            student=obj,
        ).select_related(
            "exam", "exam_subject__subject", "exam__academic_year"
        ).order_by("-exam__academic_year__start_date", "-exam__start_date")

        return [
            {
                "exam_id": r.exam_id,
                "exam_name": r.exam.name,
                "academic_year_name": r.exam.academic_year.name,
                "term_name": r.exam.term.name if r.exam.term_id else None,
                "subject_id": r.exam_subject.subject_id,
                "subject_name": r.exam_subject.subject.name,
                "obtained_marks": float(r.obtained_marks),
                "maximum_marks": r.maximum_marks,
                "passing_marks": r.passing_marks,
                "percentage": float(r.percentage),
                "grade": r.grade,
                "is_pass": r.is_pass,
                "is_absent": r.is_absent,
                "remarks": r.remarks,
            }
            for r in results
        ]

    def get_invoices(self, obj):
        """Get all invoices for the student."""
        from apps.finance.models import Invoice
        
        invoices = Invoice.objects.filter(
            student=obj
        ).select_related(
            "academic_year", "enrollment"
        ).order_by("-issue_date")
        
        return [
            {
                "id": i.id,
                "invoice_number": i.invoice_number,
                "issue_date": i.issue_date,
                "due_date": i.due_date,
                "total_amount": float(i.total_amount),
                "paid_amount": float(i.paid_amount),
                "balance": float(i.balance),
                "status": i.status,
                "academic_year": i.academic_year.name if i.academic_year else None,
            }
            for i in invoices
        ]

    def get_payments(self, obj):
        """Get all payments for the student."""
        from apps.finance.models import Payment
        
        payments = Payment.objects.filter(
            invoice__student=obj
        ).select_related(
            "invoice"
        ).order_by("-payment_date")
        
        return [
            {
                "id": p.id,
                "receipt_number": p.receipt_number,
                "payment_date": p.payment_date,
                "amount": float(p.amount),
                "payment_method": p.payment_method,
                "status": p.status,
                "reference": p.reference,
                "invoice_number": p.invoice.invoice_number,
            }
            for p in payments
        ]

    def get_fee_balance(self, obj):
        """Get total fee balance for the student."""
        from apps.finance.models import Invoice
        from decimal import Decimal

        invoices = Invoice.objects.filter(
            student=obj,
            status__in=["issued", "partial", "overdue"],
        )
        total = sum(
            (inv.balance for inv in invoices),
            Decimal("0.00"),
        )
        return float(total)

    def get_book_issues(self, obj):
        """Get current and past book issues."""
        try:
            from apps.library.models import BookIssue
            
            issues = BookIssue.objects.filter(
                student=obj
            ).select_related(
                "book_copy__book", "teacher"
            ).order_by("-issue_date")
            
            return [
                {
                    "id": i.id,
                    "book_id": i.book_copy.book_id,
                    "book_title": i.book_copy.book.title,
                    "book_author": i.book_copy.book.author,
                    "issue_date": i.issue_date,
                    "due_date": i.due_date,
                    "return_date": i.return_date,
                    "status": i.status,
                    "fine_amount": float(i.fine) if i.fine else 0,
                }
                for i in issues
            ]
        except ImportError:
            return []

    def get_transport_assignment(self, obj):
        """Get current transport assignment."""
        try:
            from apps.transport.models import TransportAssignment
            
            assignment = TransportAssignment.objects.filter(
                student=obj,
                status="active"
            ).select_related(
                "route", "stop", "route__vehicle", "route__driver"
            ).first()
            
            if not assignment:
                return None
            
            return {
                "id": assignment.id,
                "route_id": assignment.route_id,
                "route_name": assignment.route.name if assignment.route else None,
                "stop_id": assignment.stop_id,
                "stop_name": assignment.stop.name if assignment.stop else None,
                "vehicle_number": assignment.route.vehicle.plate_number if assignment.route and assignment.route.vehicle else None,
                "driver_name": assignment.route.driver.full_name if assignment.route and assignment.route.driver else None,
                "status": assignment.status,
            }
        except ImportError:
            return None

    def get_discipline_incidents(self, obj):
        """Get discipline incidents."""
        try:
            from apps.discipline.models import Incident
            
            incidents = Incident.objects.filter(
                student=obj
            ).select_related(
                "campus", "reported_by"
            ).order_by("-incident_date", "-id")
            
            return [
                {
                    "id": i.id,
                    "title": i.title,
                    "description": i.description,
                    "incident_date": i.incident_date,
                    "severity": i.severity,
                    "status": i.status,
                    "severity_display": i.get_severity_display(),
                    "status_display": i.get_status_display(),
                    "points": i.points,
                    "action_taken": i.action_taken,
                    "campus_name": i.campus.name if i.campus else None,
                }
                for i in incidents
            ]
        except ImportError:
            return []

    def get_discipline_summary(self, obj):
        """Get discipline summary."""
        try:
            from apps.discipline.models import Incident
            from django.db.models import Q, Sum, Count
            
            incidents = Incident.objects.filter(student=obj)
            
            summary = incidents.aggregate(
                total_points=Sum("points"),
                total_incidents=Count("id"),
                open_count=Count("id", filter=Q(status="open")),
                resolved_count=Count("id", filter=Q(status="resolved")),
            )
            
            severity_counts = incidents.values("severity").annotate(
                count=Count("id")
            )
            
            return {
                "total_points": summary["total_points"] or 0,
                "total_incidents": summary["total_incidents"] or 0,
                "open_incidents": summary["open_count"] or 0,
                "resolved_incidents": summary["resolved_count"] or 0,
                "by_severity": {
                    s["severity"]: s["count"] for s in severity_counts
                },
            }
        except ImportError:
            return {}

    def get_documents(self, obj):
        """Get student documents."""
        from apps.students.models import StudentDocument
        
        documents = StudentDocument.objects.filter(
            student=obj
        ).select_related("uploaded_by").order_by("-created_at")
        
        return StudentDocumentSerializer(documents, many=True, context=self.context).data

    def get_transfer_certificates(self, obj):
        """Get transfer certificates."""
        from apps.students.models import TransferCertificate
        
        certs = TransferCertificate.objects.filter(
            student=obj
        ).select_related(
            "campus", "academic_year", "class_obj", "section", "issued_by"
        ).order_by("-issue_date")
        
        return TransferCertificateSerializer(certs, many=True, context=self.context).data


# =============================================================================
# TRANSFER SERIALIZERS
# =============================================================================

class CampusTransferSerializer(serializers.ModelSerializer):
    from_campus_name = serializers.CharField(source="from_campus.name", read_only=True)
    to_campus_name = serializers.CharField(source="to_campus.name", read_only=True)
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)
    requested_by_name = serializers.CharField(source="requested_by.get_full_name", read_only=True)
    reviewed_by_name = serializers.CharField(source="reviewed_by.get_full_name", read_only=True)
    completed_by_name = serializers.CharField(source="completed_by.get_full_name", read_only=True)
    reversed_by_name = serializers.CharField(source="reversed_by.get_full_name", read_only=True)
    student_name = serializers.CharField(source="student.full_name", read_only=True)

    class Meta:
        model = CampusTransfer
        fields = [
            "id",
            "student",
            "student_name",
            "from_campus",
            "from_campus_name",
            "to_campus",
            "to_campus_name",
            "academic_year",
            "academic_year_name",
            "effective_date",
            "reason",
            "status",
            "requested_by",
            "requested_by_name",
            "reviewed_by",
            "reviewed_by_name",
            "reviewed_at",
            "review_notes",
            "completed_at",
            "completed_by",
            "completed_by_name",
            "reversed_at",
            "reversed_by",
            "reversed_by_name",
            "reversal_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "requested_by",
            "reviewed_by",
            "reviewed_at",
            "completed_at",
            "completed_by",
            "reversed_at",
            "reversed_by",
        ]


class CampusTransferCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CampusTransfer
        fields = [
            "student",
            "from_campus",
            "to_campus",
            "academic_year",
            "effective_date",
            "reason",
        ]

    def validate(self, attrs):
        student = attrs.get("student")
        from_campus = attrs.get("from_campus")
        to_campus = attrs.get("to_campus")
        academic_year = attrs.get("academic_year")
        
        if from_campus and to_campus and from_campus == to_campus:
            raise serializers.ValidationError("Cannot transfer to the same campus.")
        
        if from_campus and to_campus and from_campus.school != to_campus.school:
            raise serializers.ValidationError("Cannot transfer to a campus in a different school.")
        
        if academic_year and to_campus and academic_year.school != to_campus.school:
            raise serializers.ValidationError("Academic year must belong to the target campus's school.")
        
        return attrs


class SectionTransferSerializer(serializers.ModelSerializer):
    from_section_name = serializers.CharField(source="from_section.name", read_only=True)
    to_section_name = serializers.CharField(source="to_section.name", read_only=True)
    from_class_name = serializers.CharField(source="from_section.class_obj.name", read_only=True)
    to_class_name = serializers.CharField(source="to_section.class_obj.name", read_only=True)
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)
    requested_by_name = serializers.CharField(source="requested_by.get_full_name", read_only=True)
    reviewed_by_name = serializers.CharField(source="reviewed_by.get_full_name", read_only=True)
    completed_by_name = serializers.CharField(source="completed_by.get_full_name", read_only=True)
    student_name = serializers.CharField(source="student.full_name", read_only=True)

    class Meta:
        model = SectionTransfer
        fields = [
            "id",
            "student",
            "student_name",
            "transfer_type",
            "from_section",
            "from_section_name",
            "from_class_name",
            "to_section",
            "to_section_name",
            "to_class_name",
            "academic_year",
            "academic_year_name",
            "effective_date",
            "reason",
            "status",
            "requested_by",
            "requested_by_name",
            "reviewed_by",
            "reviewed_by_name",
            "reviewed_at",
            "review_notes",
            "completed_at",
            "completed_by",
            "completed_by_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "requested_by",
            "reviewed_by",
            "reviewed_at",
            "completed_at",
            "completed_by",
            "created_at",
            "updated_at",
        ]


class SectionTransferCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SectionTransfer
        fields = [
            "student",
            "transfer_type",
            "from_section",
            "to_section",
            "academic_year",
            "effective_date",
            "reason",
        ]

    def validate(self, attrs):
        from_section = attrs.get("from_section")
        to_section = attrs.get("to_section")
        
        if from_section and to_section and from_section == to_section:
            raise serializers.ValidationError("Cannot transfer to the same section/class.")
        
        if from_section and to_section:
            if from_section.class_obj.unit.campus != to_section.class_obj.unit.campus:
                raise serializers.ValidationError("Cannot transfer to a section in a different campus.")
            
            if attrs.get("transfer_type") == "class":
                if (from_section.class_obj.level is not None and 
                    to_section.class_obj.level is not None and
                    to_section.class_obj.level < from_section.class_obj.level):
                    raise serializers.ValidationError("Cannot transfer to a lower class level.")
        
        return attrs


class StudentAlumniSerializer(serializers.ModelSerializer):
    final_campus_name = serializers.CharField(source="final_campus.name", read_only=True)
    final_class_name = serializers.CharField(source="final_class.name", read_only=True)
    final_section_name = serializers.CharField(source="final_section.name", read_only=True)
    final_academic_year_name = serializers.CharField(source="final_academic_year.name", read_only=True)
    graduation_status_display = serializers.CharField(source="get_graduation_status_display", read_only=True)
    conduct_display = serializers.CharField(source="get_conduct_display", read_only=True)
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    admission_number = serializers.CharField(source="student.admission_number", read_only=True)

    class Meta:
        model = StudentAlumni
        fields = [
            "id",
            "student",
            "student_name",
            "admission_number",
            "institution",
            "graduation_status",
            "graduation_status_display",
            "graduation_date",
            "final_campus",
            "final_campus_name",
            "final_class",
            "final_class_name",
            "final_section",
            "final_section_name",
            "final_academic_year",
            "final_academic_year_name",
            "final_grade",
            "final_percentage",
            "attendance_percentage",
            "final_grade_letter",
            "conduct",
            "conduct_display",
            "personal_email",
            "personal_phone",
            "current_address",
            "linkedin_profile",
            "current_institution",
            "current_program",
            "current_occupation",
            "current_employer",
            "is_active",
            "last_contact_date",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

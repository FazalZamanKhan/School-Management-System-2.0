from django.core.exceptions import ValidationError
from django.db import IntegrityError
from rest_framework import serializers

from .models import Teacher, TeacherAssignment


def _has_letter(value):
    return any(char.isalpha() for char in str(value or ""))


def _phone_error(value):
    text = str(value or "").strip()
    if not text:
        return None
    allowed = set("0123456789+-() ")
    if not any(char.isdigit() for char in text) or any(char not in allowed for char in text):
        return "Enter a valid phone number using digits, spaces, +, -, or parentheses."
    return None


class TeacherSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    employee_number = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    photo_url = serializers.SerializerMethodField()

    primary_campus_name = serializers.CharField(
        source="primary_campus.name",
        read_only=True,
    )

    class_teacher_classes = serializers.SerializerMethodField()

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
        model = Teacher
        fields = [
            "id",
            "employee_number",
            "user",
            "membership",
            "primary_campus",
            "primary_campus_name",
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
            "campus",
            "joining_date",
            "designation",
            "department",
            "qualification",
            "experience_years",
            "address",
            "status",
            "create_account",
            "username",
            "password",
            "class_teacher_classes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "full_name",
            "photo_url",
            "primary_campus_name",
            "class_teacher_classes",
            "created_at",
            "updated_at",
        ]

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip()

    def get_linked_username(self, obj):
        return obj.user.username if obj.user_id else None

    def get_generated_password(self, obj):
        return getattr(self, "_generated_password", None)

    def validate(self, attrs):
        errors = {}
        for field in ("first_name", "last_name"):
            value = attrs.get(
                field,
                getattr(self.instance, field, "") if self.instance is not None else "",
            )
            if value and not _has_letter(value):
                errors[field] = "Enter a name containing at least one letter."
        phone_error = _phone_error(
            attrs.get("phone", getattr(self.instance, "phone", "") if self.instance is not None else "")
        )
        if phone_error:
            errors["phone"] = phone_error
        date_of_birth = attrs.get(
            "date_of_birth",
            getattr(self.instance, "date_of_birth", None) if self.instance is not None else None,
        )
        if date_of_birth and date_of_birth > timezone.localdate():
            errors["date_of_birth"] = "Date of birth cannot be in the future."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs

    def _resolve_school(self, teacher=None):
        from apps.schools.models import School

        request = self.context.get("request")
        active_institution = getattr(request, "institution", None) if request else None
        return (
            active_institution
            or (teacher.institution if teacher is not None else None)
            or School.objects.filter(status="active").order_by("id").first()
            or School.objects.first()
        )

    def _ensure_employee_number(self, validated_data, teacher=None):
        from apps.schools.services import next_entity_code

        current = (validated_data.get("employee_number") or "").strip()
        if current or (teacher is not None and teacher.employee_number):
            return current or teacher.employee_number

        school = self._resolve_school(teacher)
        return next_entity_code(school, "EMP", Teacher, "employee_number")

    def _build_user_account(self, teacher, username, password):
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
            or teacher.institution
            or School.objects.filter(status="active").order_by("id").first()
            or School.objects.first()
        )

        base = username or teacher.employee_number
        user, _candidate, generated = create_user_with_username(
            base,
            institution=(school if school is not None else None),
            email=(teacher.email or "").strip(),
            password=password or None,
            first_name=teacher.first_name,
            last_name=teacher.last_name,
        )

        if school is not None:
            membership, _ = InstitutionMembership.objects.get_or_create(
                user=user,
                institution=school,
                defaults={"status": "active"},
            )
            RoleAssignment.objects.get_or_create(
                membership=membership,
                role=Role.TEACHER,
            )

        return user, generated

    def create(self, validated_data):
        create_account = bool(validated_data.pop("create_account", False))
        username = validated_data.pop("username", "") or None
        password = validated_data.pop("password", "") or None

        validated_data["employee_number"] = self._ensure_employee_number(
            validated_data
        )

        teacher = Teacher(**validated_data)
        try:
            teacher.save()
        except IntegrityError:
            raise serializers.ValidationError(
                {
                    "employee_number": [
                        "A teacher with this employee number already exists."
                    ]
                }
            )

        if create_account:
            try:
                user, generated = self._build_user_account(teacher, username, password)
            except IntegrityError:
                teacher.delete()
                raise serializers.ValidationError(
                    {
                        "non_field_errors": [
                            "Could not create the login account: the username or "
                            "email is already in use."
                        ]
                    }
                )

            teacher.user = user
            teacher.save(update_fields=["user"])
            self._generated_password = generated

        return teacher

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
                        "A teacher with this employee number already exists."
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

    def get_class_teacher_classes(self, obj):
        assignments = obj.assignments.filter(
            role="class_teacher",
            status="active",
        ).select_related(
            "class_obj",
            "section",
            "campus",
            "academic_year",
        )

        result = []

        for assignment in assignments:
            student_ids = teacher_student_ids_for_assignment(assignment)
            result.append(
                {
                    "id": assignment.id,
                    "class_id": assignment.class_obj_id,
                    "class_name": assignment.class_obj.name,
                    "section_id": assignment.section_id,
                    "section_name": assignment.section.name,
                    "campus_id": assignment.campus_id,
                    "campus_name": assignment.campus.name,
                    "academic_year_id": assignment.academic_year_id,
                    "academic_year_name": assignment.academic_year.name,
                    "student_count": len(student_ids),
                }
            )

        return result


def teacher_student_ids_for_assignment(assignment):
    from apps.students.models import Enrollment

    return list(
        Enrollment.objects.filter(
            class_obj=assignment.class_obj,
            section=assignment.section,
            academic_year=assignment.academic_year,
            status="active",
        ).values_list("student_id", flat=True)
    )


class TeacherAssignmentSerializer(serializers.ModelSerializer):
    """Assign a teacher to a grade (class/section/subject)."""

    teacher_name = serializers.CharField(
        source="teacher.full_name",
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
    subject_name = serializers.CharField(
        source="subject.name",
        read_only=True,
    )
    academic_year_name = serializers.CharField(
        source="academic_year.name",
        read_only=True,
    )
    role_label = serializers.CharField(
        source="get_role_display",
        read_only=True,
    )

    class Meta:
        model = TeacherAssignment
        fields = [
            "id",
            "teacher",
            "teacher_name",
            "campus",
            "campus_name",
            "class_obj",
            "class_name",
            "section",
            "section_name",
            "subject",
            "subject_name",
            "academic_year",
            "academic_year_name",
            "role",
            "role_label",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
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
                        "This teacher is already assigned to this "
                        "class, section and subject for the year."
                    ]
                }
            )

        return instance

    def create(self, validated_data):
        return self._save(TeacherAssignment(**validated_data))

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)

        return self._save(instance)

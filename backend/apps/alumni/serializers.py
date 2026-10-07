from django.utils import timezone
from rest_framework import serializers

from .models import AlumniProfile


class AlumniProfileSerializer(serializers.ModelSerializer):
    campus_name = serializers.CharField(
        source="campus.name",
        read_only=True,
        default="",
    )

    class Meta:
        model = AlumniProfile
        fields = [
            "id",
            "student",
            "campus",
            "campus_name",
            "full_name",
            "batch_year",
            "email",
            "phone",
            "occupation",
            "organization",
            "city",
            "notes",
            "is_active_member",
            "created_at",
        ]

    def validate_batch_year(self, value):
        current_year = timezone.localdate().year
        if value < 1980 or value > current_year:
            raise serializers.ValidationError(
                f"Batch year must be between 1980 and {current_year}."
            )

        return value

    def validate_campus(self, value):
        """The campus must be inside the acting user's scope.

        A global user's scope is their active institution; a campus-scoped
        user is further limited to their own campuses. Cross-tenant campus
        assignment is rejected with 403.
        """
        if value is None:
            return value

        request = self.context.get("request")
        user = getattr(request, "user", None) if request is not None else None

        if user is None or not getattr(user, "is_authenticated", False):
            return value

        from apps.accounts.access import assert_campus_allowed

        assert_campus_allowed(user, value.pk, request)
        return value

    def validate(self, attrs):
        """Tenant ownership of the linked student and campus.

        The student is the server-side source of truth: its institution (or
        campus) must match the acting user's active institution, and a given
        campus must match the student's own campus (the model defines no
        cross-campus student linkage).
        """
        request = self.context.get("request")
        user = getattr(request, "user", None) if request is not None else None

        campus = attrs.get("campus")
        student = attrs.get("student")

        if self.instance is not None:
            if campus is None:
                campus = self.instance.campus
            if student is None:
                student = self.instance.student

        if campus is None and student is None:
            return attrs

        if user is None or not getattr(user, "is_authenticated", False):
            return attrs

        from apps.accounts.access import get_institution
        from apps.students.models import Enrollment

        if request is not None:
            institution = get_institution(request)
        else:
            institution = None

        if institution is None:
            institution = getattr(user, "primary_institution", None)

        if student is not None:
            student_campus = (
                student.primary_campus if student.primary_campus_id else None
            )

            if student_campus is None:
                from apps.schools.models import Campus

                enrollment_campus_id = (
                    Enrollment.objects.filter(
                        student=student, status="active"
                    )
                    .values_list("campus_id", flat=True)
                    .first()
                )
                if enrollment_campus_id is not None:
                    student_campus = (
                        Campus.objects.filter(pk=enrollment_campus_id).first()
                    )

            student_institution_id = student.institution_id or (
                student_campus.school_id
                if student_campus is not None
                else None
            )

            if (
                institution is not None
                and student_institution_id is not None
                and student_institution_id != institution.pk
            ):
                raise serializers.ValidationError({
                    "student": (
                        "The selected student does not belong to your "
                        "institution."
                    )
                })

            if campus is not None and student_campus is not None:
                if campus.pk != student_campus.pk:
                    raise serializers.ValidationError({
                        "campus": (
                            "The campus does not match the selected "
                            "student's campus."
                        )
                    })

        return attrs

    def create(self, validated_data):
        request = self.context.get("request")

        if validated_data.get("institution") is None:
            from apps.accounts.access import get_institution

            institution = (
                get_institution(request) if request is not None else None
            )

            if institution is None and request is not None:
                user = getattr(request, "user", None)
                institution = (
                    getattr(user, "primary_institution", None)
                    if user is not None
                    else None
                )

            validated_data["institution"] = institution

        return super().create(validated_data)

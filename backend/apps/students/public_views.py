"""Public (unauthenticated) admission application endpoints for the
school website. Heavily throttled; write-only except structure lookups."""

from django.utils import timezone
from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.schools.models import AcademicYear, Campus, Class, Section


class PublicAdmissionOptionsView(APIView):
    """GET /api/students/admissions/public/options/

    Returns the campuses, classes and academic years a website
    visitor can pick from. Read-only, no auth.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        years = list(
            AcademicYear.objects.filter(status="active")
            .order_by("-start_date")
            .values("id", "name", "school_id")
        )

        if not years:
            return Response({"academic_years": [], "campuses": []})

        school_ids = {y["school_id"] for y in years}

        campuses = list(
            Campus.objects.filter(
                status="active",
                school_id__in=school_ids,
            ).values("id", "name", "school_id")
        )

        classes = list(
            Class.objects.filter(
                unit__campus__in=[c["id"] for c in campuses],
                status="active",
            )
            .order_by("level", "name")
            .values("id", "name", "unit__campus_id")
        )

        sections = list(
            Section.objects.filter(
                class_obj__in=[c["id"] for c in classes],
                status="active",
            ).values("id", "name", "class_obj_id")
        )

        return Response({
            "academic_years": years,
            "campuses": campuses,
            "classes": [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "campus_id": row["unit__campus_id"],
                }
                for row in classes
            ],
            "sections": sections,
        })


class PublicAdmissionApplyView(APIView):
    """POST /api/students/admissions/public/ — submit an application."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_apply"

    REQUIRED = (
        "first_name",
        "last_name",
        "gender",
        "date_of_birth",
        "guardian_name",
        "guardian_phone",
        "campus",
        "class_obj",
    )

    def post(self, request):
        from apps.students.models import AdmissionApplication

        data = request.data or {}

        missing = [
            field
            for field in self.REQUIRED
            if not str(data.get(field) or "").strip()
        ]

        if missing:
            return Response(
                {"detail": f"Missing required fields: {', '.join(missing)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        gender = str(data.get("gender")).strip().lower()

        if gender not in ("male", "female"):
            return Response(
                {"detail": "gender must be male or female."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        campus = Campus.objects.filter(
            pk=data.get("campus"),
            status="active",
        ).first()

        class_obj = Class.objects.filter(pk=data.get("class_obj")).first()

        if campus is None or class_obj is None:
            return Response(
                {"detail": "Invalid campus or class."}, status=400
            )

        year = (
            AcademicYear.objects.filter(
                school=campus.school, status="active"
            ).order_by("-start_date").first()
        )

        if year is None:
            return Response(
                {"detail": "No active academic year."}, status=400
            )

        section = None

        if data.get("section"):
            section = Section.objects.filter(
                pk=data.get("section"),
                class_obj=class_obj,
            ).first()

        guardian_phone = str(data.get("guardian_phone") or "").strip()
        duplicate = AdmissionApplication.objects.filter(
            institution=campus.school,
            campus=campus,
            academic_year=year,
            first_name__iexact=str(data.get("first_name")).strip(),
            middle_name__iexact=str(data.get("middle_name") or "").strip(),
            last_name__iexact=str(data.get("last_name")).strip(),
            date_of_birth=data.get("date_of_birth") or None,
            review_notes__icontains=f"({guardian_phone})",
        ).exclude(status__in=("rejected", "withdrawn")).first()

        if duplicate:
            return Response(
                {
                    "detail": "A matching application is already on file.",
                    "application_number": duplicate.application_number,
                },
                status=status.HTTP_409_CONFLICT,
            )

        application_number = (
            f"PUB-{timezone.localdate().year}-"
            f"{AdmissionApplication.objects.count() + 1:05d}"
        )

        try:
            application = AdmissionApplication.objects.create(
                institution=campus.school,
                application_number=application_number,
                first_name=str(data.get("first_name")).strip()[:100],
                middle_name=str(data.get("middle_name") or "").strip()[:100],
                last_name=str(data.get("last_name")).strip()[:100],
                date_of_birth=data.get("date_of_birth") or None,
                gender=gender,
                phone=str(data.get("phone") or "").strip()[:30],
                address=str(data.get("address") or "").strip(),
                campus=campus,
                academic_year=year,
                class_obj=class_obj,
                section=section,
            review_notes=(
                f"Guardian: {data.get('guardian_name')} "
                f"({guardian_phone})"
                ),
                status="submitted",
                submitted_at=timezone.now(),
            )
        except ValidationError as exc:
            return Response(
                getattr(exc, "message_dict", {"detail": exc.messages}),
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "application_number": application.application_number,
                "status": application.status,
                "detail": (
                    "Application received. The school will contact you."
                ),
            },
            status=status.HTTP_201_CREATED,
        )

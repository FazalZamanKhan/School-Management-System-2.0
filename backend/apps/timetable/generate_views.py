"""API endpoint to run the timetable generator (admins only)."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.access import is_global
from apps.accounts.middleware import require_active_school
from apps.schools.models import AcademicYear, Campus, Class, Section


class TimetableGenerateView(APIView):
    """POST /api/timetable/generate/

    Body:
        campus: int | str        (id or exact name)
        academic_year: int       (optional, default latest active)
        lessons_per_subject: int (optional, default 5)
        days: [str]              (optional)
        class_id: int            (optional, generate for specific class)
        section_id: int          (optional, generate for specific section)
        confirm: true            REQUIRED — generation replaces entries.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not is_global(request.user):
            return Response(
                {"detail": "Only administrators can generate timetables."},
                status=403,
            )

        institution = require_active_school(request)
        if institution is None:
            return Response({"detail": "Select a school before generating a timetable."}, status=400)

        if request.data.get("confirm") is not True:
            return Response(
                {
                    "detail": (
                        "Pass confirm:true — generation replaces the "
                        "existing timetable for the campus/class/section."
                    )
                },
                status=400,
            )

        from apps.timetable.generator import generate_timetable

        campus_raw = request.data.get("campus")

        if not campus_raw:
            return Response(
                {"detail": "campus is required."}, status=400
            )

        campus = None

        if str(campus_raw).isdigit():
            campus = Campus.objects.filter(pk=campus_raw, school=institution).first()

        if campus is None:
            campus = Campus.objects.filter(
                name__iexact=str(campus_raw), school=institution
            ).first()

        if campus is None:
            return Response(
                {"detail": f"Campus '{campus_raw}' not found."}, status=404
            )

        year_id = request.data.get("academic_year")

        year = (
            AcademicYear.objects.filter(pk=year_id, school=institution).first()
            if year_id
            else (
                AcademicYear.objects.filter(
                    school=campus.school, status="active"
                ).order_by("-start_date").first()
                or AcademicYear.objects.filter(
                    school=campus.school
                ).order_by("-start_date").first()
            )
        )

        if year is None:
            return Response(
                {"detail": "No academic year found for this school."},
                status=400,
            )

        # Optional class/section scoping
        class_id = request.data.get("class_id")
        section_id = request.data.get("section_id")

        if class_id:
            from apps.schools.models import Class
            if not Class.objects.filter(pk=class_id, unit__campus=campus).exists():
                return Response(
                    {"detail": "Class not found in this campus."}, status=404
                )

        if section_id:
            from apps.schools.models import Section
            if not Section.objects.filter(pk=section_id, class_obj__unit__campus=campus).exists():
                return Response(
                    {"detail": "Section not found in this campus."}, status=404
                )

        raw_lessons = request.data.get("lessons_per_subject", 5)
        if isinstance(raw_lessons, bool) or not str(raw_lessons).strip().lstrip("-").isdigit():
            return Response({"detail": "Lessons per subject must be a whole number from 1 to 20."}, status=400)
        lessons = int(raw_lessons)
        if not 1 <= lessons <= 20:
            return Response({"detail": "Lessons per subject must be between 1 and 20."}, status=400)

        days = request.data.get("days") or [
            "monday", "tuesday", "wednesday", "thursday", "friday",
        ]

        try:
            stats = generate_timetable(
                campus=campus,
                academic_year=year,
                lessons_per_subject=lessons,
                days=[str(day).lower() for day in days],
                replace=True,
                class_id=class_id,
                section_id=section_id,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        stats["campus"] = campus.name
        stats["academic_year"] = year.name

        return Response(stats)

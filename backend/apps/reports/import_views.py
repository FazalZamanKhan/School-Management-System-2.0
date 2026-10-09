"""Data import endpoints: CSV template download, dry-run preview and
commit. Pairs with ``export_views`` under Data Ops. Imports are
stateless: both preview and commit re-parse the uploaded file so an
upload never needs server-side session storage."""

import csv
from datetime import date

from django.db import transaction
from django.http import HttpResponse
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.access import get_institution
from apps.accounts.permissions import IsAdminRole


class ImportError_(Exception):
    pass


STUDENT_HEADERS = [
    "admission_number",
    "first_name",
    "middle_name",
    "last_name",
    "gender",
    "date_of_birth",
    "campus",
    "class_name",
    "section_name",
    "roll_number",
    "guardian_name",
    "guardian_phone",
    "guardian_relationship",
]

TEACHER_HEADERS = [
    "employee_number",
    "first_name",
    "last_name",
    "gender",
    "designation",
    "qualification",
    "experience_years",
    "campus",
]

IMPORT_KEYS = ("students", "teachers")


def _clean(value):
    return str(value or "").strip()


def _parse_gender(value):
    value = _clean(value).lower()

    if value in ("male", "m"):
        return "male"

    if value in ("female", "f"):
        return "female"

    raise ImportError_(
        f"gender must be male or female (got '{value or 'empty'}')"
    )


def _parse_date(value, field):
    value = _clean(value)

    if not value:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ImportError_(
            f"{field} must be YYYY-MM-DD (got '{value}')"
        )


def _read_rows(request):
    """Return a list of dicts from an uploaded CSV or JSON rows body."""
    upload = request.FILES.get("file")

    if upload is not None:
        try:
            text = upload.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ImportError_("File must be UTF-8 encoded CSV.")

        reader = csv.DictReader(text.splitlines())

        if not reader.fieldnames:
            raise ImportError_("The CSV file has no header row.")

        headers = [_clean(h).lower() for h in reader.fieldnames]
        reader.fieldnames = headers
        return list(reader)

    rows = request.data.get("rows")

    if isinstance(rows, list):
        return rows

    raise ImportError_("Attach a CSV 'file' or post JSON {'rows': [...]}")


def _resolve_structure(institution, campus_name):
    from apps.schools.models import Campus

    name = _clean(campus_name)

    if not name:
        raise ImportError_("campus is required.")

    campus = Campus.objects.filter(
        school=institution,
        name__iexact=name,
    ).first()

    if campus is None:
        raise ImportError_(f"Campus '{name}' was not found.")

    return campus


def _validate_student_row(row, index, institution, seen_admissions):
    from apps.schools.models import Class, Section

    errors = []
    clean = {}

    def need(field):
        value = _clean(row.get(field))

        if not value:
            errors.append(f"{field} is required.")

        return value

    clean["admission_number"] = need("admission_number")
    clean["first_name"] = need("first_name")

    if not _clean(row.get("last_name")) and not clean.get("first_name"):
        errors.append("last_name is required.")

    try:
        clean["gender"] = _parse_gender(row.get("gender"))
    except ImportError_ as exc:
        errors.append(str(exc))

    try:
        clean["date_of_birth"] = _parse_date(row.get("date_of_birth"), "date_of_birth")
    except ImportError_ as exc:
        errors.append(str(exc))

    admission = clean.get("admission_number")

    if admission:
        if admission in seen_admissions:
            errors.append(
                f"admission_number '{admission}' appears twice in this file."
            )

        seen_admissions.add(admission)

    for field in (
        "middle_name",
        "last_name",
        "class_name",
        "section_name",
        "roll_number",
        "guardian_name",
        "guardian_phone",
    ):
        clean[field] = _clean(row.get(field))

    if not clean["guardian_name"]:
        errors.append("guardian_name is required.")

    if not clean["guardian_phone"]:
        errors.append("guardian_phone is required.")

    clean["guardian_relationship"] = (
        _clean(row.get("guardian_relationship")) or "Father"
    )

    campus_name = _clean(row.get("campus"))

    try:
        clean["campus_obj"] = _resolve_structure(institution, campus_name)
    except ImportError_ as exc:
        clean["campus_obj"] = None
        errors.append(str(exc))

    clean["class_obj"] = None
    clean["section_obj"] = None

    if clean.get("campus_obj") and clean["class_name"]:
        class_obj = (
            Class.objects
            .filter(
                unit__campus=clean["campus_obj"],
                name__iexact=clean["class_name"],
            )
            .first()
        )

        if class_obj is None:
            errors.append(
                f"Class '{clean['class_name']}' was not found "
                f"in {clean['campus_obj'].name}."
            )
        else:
            clean["class_obj"] = class_obj

            if clean["section_name"]:
                section = Section.objects.filter(
                    class_obj=class_obj,
                    name__iexact=clean["section_name"],
                ).first()

                if section is None:
                    errors.append(
                        f"Section '{clean['section_name']}' was not "
                        f"found in {class_obj.name}."
                    )
                else:
                    clean["section_obj"] = section
            else:
                errors.append("section_name is required.")

    elif clean.get("campus_obj"):
        errors.append("class_name is required.")

    return clean, errors


def _student_exists(institution, admission_number):
    from apps.students.models import Student

    return Student.objects.filter(
        institution=institution,
        admission_number=admission_number,
    ).exists()


def _create_student(clean, institution):
    from apps.students.models import Guardian, Student

    guardian, _ = Guardian.objects.get_or_create(
        institution=institution,
        phone=clean["guardian_phone"],
        defaults={
            "name": clean["guardian_name"],
            "relationship": clean["guardian_relationship"],
        },
    )

    student = Student.objects.create(
        institution=institution,
        admission_number=clean["admission_number"],
        first_name=clean["first_name"],
        middle_name=clean["middle_name"],
        last_name=clean["last_name"],
        gender=clean["gender"],
        date_of_birth=clean["date_of_birth"],
        guardian=guardian,
        primary_campus=clean["campus_obj"],
        status="active",
    )

    return student


def _create_enrollment(student, clean, academic_year):
    from apps.students.models import Enrollment

    enrollment, created = Enrollment.objects.get_or_create(
        student=student,
        academic_year=academic_year,
        defaults={
            "campus": clean["campus_obj"],
            "class_obj": clean["class_obj"],
            "section": clean["section_obj"],
            "roll_number": clean["roll_number"],
            "status": "active",
        },
    )

    return enrollment, created


def _validate_teacher_row(row, institution, seen_numbers):
    errors = []
    clean = {}

    clean["employee_number"] = _clean(row.get("employee_number"))

    if not clean["employee_number"]:
        errors.append("employee_number is required.")
    elif clean["employee_number"] in seen_numbers:
        errors.append(
            f"employee_number '{clean['employee_number']}' appears twice."
        )

    seen_numbers.add(clean["employee_number"])

    clean["first_name"] = _clean(row.get("first_name"))

    if not clean["first_name"]:
        errors.append("first_name is required.")

    try:
        clean["gender"] = _parse_gender(row.get("gender"))
    except ImportError_ as exc:
        errors.append(str(exc))
        clean["gender"] = ""

    for field in (
        "last_name",
        "designation",
        "qualification",
    ):
        clean[field] = _clean(row.get(field))

    experience = _clean(row.get("experience_years"))

    if experience:
        try:
            clean["experience_years"] = int(experience)
            if clean["experience_years"] < 0:
                errors.append("experience_years must be zero or greater.")
        except ValueError:
            errors.append(f"experience_years must be a number (got '{experience}')")
            clean["experience_years"] = None
    else:
        clean["experience_years"] = None

    clean["campus_obj"] = None

    try:
        clean["campus_obj"] = _resolve_structure(
            institution,
            row.get("campus"),
        )
    except ImportError_ as exc:
        errors.append(str(exc))

    return clean, errors


def _create_teacher(clean, institution):
    from apps.teachers.models import Teacher

    teacher = Teacher.objects.create(
        institution=institution,
        employee_number=clean["employee_number"],
        first_name=clean["first_name"],
        last_name=clean["last_name"],
        gender=clean["gender"],
        designation=clean["designation"] or "Teacher",
        qualification=clean["qualification"],
        experience_years=clean["experience_years"] or 0,
        primary_campus=clean["campus_obj"],
        status="active",
    )

    return teacher


def _get_institution_or_raise(request):
    institution = get_institution(request)

    if institution is None:
        raise ImportError_(
            "No active institution could be resolved for this account."
        )

    return institution


def _get_active_academic_year(request, institution):
    from apps.schools.models import AcademicYear

    qs = AcademicYear.objects.filter(school=institution)

    year_id = request.data.get("academic_year") or request.query_params.get("academic_year")

    if year_id:
        year = qs.filter(pk=year_id).first()

        if year is None:
            raise ImportError_(
                "Selected academic year was not found in your institution."
            )

        return year

    year = (
        qs.filter(status="active")
        .order_by("-start_date")
        .first()
    ) or qs.order_by("-start_date").first()

    if year is None:
        raise ImportError_("No academic year exists in your institution.")

    return year


class ImportTemplateView(APIView):
    """Download a ready-to-fill CSV template for an import key."""

    permission_classes = [IsAuthenticated, IsAdminRole]

    TEMPLATES = {
        "students": {
            "headers": STUDENT_HEADERS,
            "example": [
                "PF-2027-001",
                "Ayesha",
                "",
                "Khan",
                "female",
                "2014-05-12",
                "Junior Campus",
                "Grade 3",
                "A",
                "",
                "Imran Khan",
                "0300-1234567",
                "Father",
            ],
        },
        "teachers": {
            "headers": TEACHER_HEADERS,
            "example": [
                "JC-T-101",
                "Bilal",
                "Ahmed",
                "male",
                "Teacher",
                "MSc Mathematics",
                "5",
                "Junior Campus",
            ],
        },
    }

    def get(self, request, import_key):
        if import_key not in self.TEMPLATES:
            return Response(
                {"detail": f"Unknown import key '{import_key}'."},
                status=404,
            )

        template = self.TEMPLATES[import_key]

        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = (
            f'attachment; filename="{import_key}_import_template.csv"'
        )

        response.write("\ufeff")

        writer = csv.writer(response)
        writer.writerow(template["headers"])
        writer.writerow(template["example"])

        return response


class ImportPreviewView(APIView):
    """Dry-run validation of an import file. Nothing is saved."""

    permission_classes = [IsAuthenticated, IsAdminRole]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        try:
            institution = _get_institution_or_raise(request)
            key = _clean(request.query_params.get("key")) or _clean(
                request.data.get("key")
            )

            if key not in IMPORT_KEYS:
                return Response(
                    {"detail": "Provide ?key=students or ?key=teachers."},
                    status=400,
                )

            rows = _read_rows(request)
        except ImportError_ as exc:
            return Response({"detail": str(exc)}, status=400)

        seen_students = set()
        seen_teachers = set()
        errors = []
        valid = []

        for index, row in enumerate(rows, start=2):  # line 1 = header
            if key == "students":
                clean, row_errors = _validate_student_row(
                    row,
                    index,
                    institution,
                    seen_students,
                )

                admission = clean.get("admission_number")

                if (
                    admission
                    and not any(
                        str(admission) in e for e in row_errors
                    )
                    and _student_exists(institution, admission)
                ):
                    row_errors.append(
                        f"admission_number '{admission}' already exists."
                    )
            else:
                clean, row_errors = _validate_teacher_row(
                    row,
                    institution,
                    seen_teachers,
                )

            if row_errors:
                errors.append({"row": index, "errors": row_errors})
            else:
                valid.append({"row": index, "data": clean})

        return Response(
            {
                "key": key,
                "total_rows": len(rows),
                "valid_rows": len(valid),
                "error_rows": len(errors),
                "can_commit": len(rows) > 0 and len(errors) == 0,
                "errors": errors[:100],
                "sample": [
                    {
                        "row": item["row"],
                        "summary": ", ".join(
                            f"{value}"
                            for key_, value in item["data"].items()
                            if key_.endswith(("number", "name"))
                            and value
                            and not key_.endswith("_obj")
                        ),
                    }
                    for item in valid[:20]
                ],
            }
        )


class ImportCommitView(APIView):
    """Create records from an uploaded CSV. Rows with validation errors
    abort nothing individually — they are reported and skipped; every
    fully-valid row is imported inside one transaction."""

    permission_classes = [IsAuthenticated, IsAdminRole]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        try:
            institution = _get_institution_or_raise(request)
            key = _clean(request.query_params.get("key")) or _clean(
                request.data.get("key")
            )

            if key not in IMPORT_KEYS:
                return Response(
                    {"detail": "Provide ?key=students or ?key=teachers."},
                    status=400,
                )

            rows = _read_rows(request)

            if key == "students":
                academic_year = _get_active_academic_year(request, institution)

            seen_students = set()
            seen_teachers = set()
            errors = []
            created_students = 0
            skipped_students = 0
            enrollments_created = 0
            created_teachers = 0
            skipped_teachers = 0

            to_create = []

            for index, row in enumerate(rows, start=2):
                if key == "students":
                    clean, row_errors = _validate_student_row(
                        row,
                        index,
                        institution,
                        seen_students,
                    )
                else:
                    clean, row_errors = _validate_teacher_row(
                        row,
                        institution,
                        seen_teachers,
                    )

                if row_errors:
                    errors.append({"row": index, "errors": row_errors})
                    continue

                if key == "students":
                    if _student_exists(institution, clean["admission_number"]):
                        skipped_students += 1
                        continue

                    to_create.append(clean)
                else:
                    to_create.append(clean)

            with transaction.atomic():
                for clean in to_create:
                    if key == "students":
                        student = _create_student(clean, institution)
                        created_students += 1

                        _, enrollment_created = _create_enrollment(
                            student,
                            clean,
                            academic_year,
                        )

                        if enrollment_created:
                            enrollments_created += 1
                    else:
                        _create_teacher(clean, institution)
                        created_teachers += 1

            if key == "students":
                return Response(
                    {
                        "detail": "Import finished.",
                        "students_created": created_students,
                        "students_skipped_existing": skipped_students,
                        "enrollments_created": enrollments_created,
                        "rows_with_errors": len(errors),
                        "academic_year": academic_year.name,
                        "errors": errors[:100],
                    }
                )

            return Response(
                {
                    "detail": "Import finished.",
                    "teachers_created": created_teachers,
                    "teachers_skipped_duplicates": skipped_teachers,
                    "rows_with_errors": len(errors),
                    "errors": errors[:100],
                }
            )
        except ImportError_ as exc:
            return Response({"detail": str(exc)}, status=400)

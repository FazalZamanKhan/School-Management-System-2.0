"""Data export views for bulk CSV/JSON downloads."""

import csv
import io
import json

from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdminRole
from apps.accounts.access import apply_campus_scope, get_institution


EXPORT_CONFIGS = {
    "students": {
        "label": "Students",
        "model_path": "apps.students.models.Student",
        "fields": [
            "id", "admission_number", "first_name", "last_name",
            "date_of_birth", "gender", "status",
        ],
        "related_fields": {
            "email": "email",
            "phone": "phone",
            "guardian_name": "guardian__name",
            "guardian_phone": "guardian__phone",
        },
        "select_related": ["user", "guardian"],
        "filename": "students_export",
    },
    "teachers": {
        "label": "Teachers",
        "model_path": "apps.teachers.models.Teacher",
        "fields": [
            "id", "employee_number", "first_name", "last_name",
            "designation", "qualification", "experience_years",
        ],
        "related_fields": {
            "email": "email",
            "phone": "phone",
        },
        "select_related": ["user"],
        "filename": "teachers_export",
    },
    "invoices": {
        "label": "Finance - Invoices",
        "model_path": "apps.finance.models.Invoice",
        "fields": [
            "id", "invoice_number", "status", "issue_date",
            "due_date", "total_amount", "paid_amount", "discount",
        ],
        "related_fields": {
            "student_name": "enrollment__student__first_name",
            "student_admission": "enrollment__student__admission_number",
            "campus": "enrollment__campus__name",
            "class_name": "enrollment__class_obj__name",
        },
        "select_related": [
            "enrollment",
            "enrollment__student",
            "enrollment__campus",
            "enrollment__class_obj",
            "academic_year",
        ],
        "prefetch_related": [
            "items",
            "payments",
            "payments__refunds",
            "payments__reversals",
            "concessions",
        ],
        "filename": "invoices_export",
    },
    "payments": {
        "label": "Finance - Payments",
        "model_path": "apps.finance.models.Payment",
        "fields": [
            "id", "receipt_number", "payment_date", "payment_method",
            "amount", "net_amount", "notes",
        ],
        "related_fields": {
            "student_name": "invoice__enrollment__student__first_name",
            "invoice_number": "invoice__invoice_number",
            "campus": "invoice__enrollment__campus__name",
        },
        "select_related": [
            "invoice",
            "invoice__enrollment",
            "invoice__enrollment__student",
            "invoice__enrollment__campus",
        ],
        "prefetch_related": ["refunds", "reversals"],
        "filename": "payments_export",
    },
    "attendance": {
        "label": "Attendance Records",
        "model_path": "apps.attendance.models.Attendance",
        "fields": [
            "id", "date", "status", "notes",
        ],
        "related_fields": {
            "student_name": "student__first_name",
            "admission_number": "student__admission_number",
            "class_name": "class_obj__name",
            "campus": "campus__name",
        },
        "select_related": ["student", "class_obj", "campus"],
        "filename": "attendance_export",
    },
    "enrollments": {
        "label": "Enrollments",
        "model_path": "apps.students.models.Enrollment",
        "fields": [
            "id", "status", "enrollment_date", "roll_number",
        ],
        "related_fields": {
            "student_name": "student__first_name",
            "admission_number": "student__admission_number",
            "class_name": "class_obj__name",
            "section": "section__name",
            "campus": "campus__name",
            "academic_year": "academic_year__name",
        },
        "select_related": [
            "student",
            "class_obj",
            "section",
            "campus",
            "academic_year",
        ],
        "filename": "enrollments_export",
    },
    "results": {
        "label": "Exam Results",
        "model_path": "apps.exams.models.StudentResult",
        "fields": [
            "id", "obtained_marks", "percentage", "grade", "is_pass",
        ],
        "related_fields": {
            "student_name": "student__first_name",
            "admission_number": "student__admission_number",
            "exam_name": "exam__name",
            "subject_name": "exam_subject__subject__name",
            "max_marks": "exam_subject__maximum_marks",
            "class_name": "exam__class_obj__name",
        },
        "select_related": [
            "student",
            "exam",
            "exam_subject__subject",
            "exam__class_obj",
        ],
        "filename": "results_export",
    },
    "fees": {
        "label": "Fee Collection",
        "model_path": "apps.finance.models.Invoice",
        "fields": [
            "id", "invoice_number", "issue_date", "due_date", "total_amount", "paid_amount", "discount", "status",
        ],
        "related_fields": {
            "student_name": "enrollment__student__first_name",
            "admission_number": "enrollment__student__admission_number",
            "class_name": "enrollment__class_obj__name",
            "campus": "enrollment__campus__name",
        },
        "select_related": [
            "enrollment",
            "enrollment__student",
            "enrollment__class_obj",
            "enrollment__campus",
            "academic_year",
        ],
        "prefetch_related": [
            "items",
            "payments",
        ],
        "filename": "fees_export",
    },
    "staff": {
        "label": "Staff Directory",
        "model_path": "apps.accounts.models.StaffProfile",
        "fields": [
            "id", "employee_number", "first_name", "last_name", "gender", "status", "designation", "department",
        ],
        "related_fields": {
            "email": "email",
            "phone": "phone",
            "campus": "primary_campus__name",
        },
        "select_related": ["user", "primary_campus"],
        "filename": "staff_export",
    },
    "subjects": {
        "label": "Subject Performance",
        "model_path": "apps.schools.models.Subject",
        "fields": [
            "id", "name", "code", "description",
        ],
        "related_fields": {},
        "filename": "subjects_export",
    },
    "student_status": {
        "label": "Student Status",
        "model_path": "apps.students.models.Student",
        "fields": [
            "id", "admission_number", "first_name", "last_name", "gender", "status", "date_of_birth",
        ],
        "related_fields": {
            "campus": "primary_campus__name",
            "class_name": "enrollments__class_obj__name",
        },
        "select_related": ["primary_campus"],
        "prefetch_related": ["enrollments__class_obj"],
        "filename": "student_status_export",
    },
    "fee_categories": {
        "label": "Fee Categories",
        "model_path": "apps.finance.models.FeeCategory",
        "fields": [
            "id", "name", "description", "frequency", "status",
        ],
        "related_fields": {},
        "filename": "fee_categories_export",
    },
}


class DataExportListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        exports = []
        for key, config in EXPORT_CONFIGS.items():
            exports.append({
                "key": key,
                "label": config["label"],
                "filename": config["filename"],
            })
        return Response(exports)


class DataExportView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request, export_key):
        if export_key not in EXPORT_CONFIGS:
            return Response({"detail": f"Unknown export: {export_key}"}, status=404)

        config = EXPORT_CONFIGS[export_key]
        fmt = request.query_params.get("format", "csv")

        from django.utils.module_loading import import_string

        model = import_string(config["model_path"])
        queryset = model.objects.all()

        if config.get("select_related"):
            queryset = queryset.select_related(*config["select_related"])

        if config.get("prefetch_related"):
            queryset = queryset.prefetch_related(*config["prefetch_related"])

        fields = config["fields"]
        related = config.get("related_fields", {})

        queryset = _scope_export_queryset(request, queryset, export_key)
        queryset = _apply_filters(request, queryset, export_key)

        data_rows = []
        headers = fields + list(related.keys())

        for obj in queryset[:5000]:
            row = []
            for f in fields:
                row.append(_get_nested(obj, f))
            for alias, path in related.items():
                row.append(_get_nested(obj, path))
            data_rows.append(row)

        if fmt == "json":
            json_data = []
            for row in data_rows:
                json_data.append(dict(zip(headers, row)))
            response = HttpResponse(
                json.dumps(json_data, default=str, indent=2, ensure_ascii=False),
                content_type="application/json; charset=utf-8",
            )
            response["Content-Disposition"] = f'attachment; filename="{config["filename"]}.json"'
            return response

        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{config["filename"]}.csv"'
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(headers)
        writer.writerows(data_rows)
        return response


class DataBackupView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        backup_data = {}

        for key, config in EXPORT_CONFIGS.items():
            from django.utils.module_loading import import_string

            model = import_string(config["model_path"])
            fields = config["fields"]
            related = config.get("related_fields", {})
            headers = fields + list(related.keys())

            queryset = model.objects.all()

            if config.get("select_related"):
                queryset = queryset.select_related(*config["select_related"])

            if config.get("prefetch_related"):
                queryset = queryset.prefetch_related(*config["prefetch_related"])

            queryset = _scope_export_queryset(request, queryset, key)
            rows = []
            for obj in queryset:
                row = {}
                for f in fields:
                    row[f] = str(_get_nested(obj, f))
                for alias, path in related.items():
                    row[alias] = str(_get_nested(obj, path))
                rows.append(row)

            backup_data[key] = {
                "label": config["label"],
                "count": len(rows),
                "headers": headers,
                "rows": rows,
            }

        response = HttpResponse(
            json.dumps(backup_data, default=str, indent=2, ensure_ascii=False),
            content_type="application/json; charset=utf-8",
        )
        response["Content-Disposition"] = 'attachment; filename="full_backup.json"'
        return response


def _get_nested(obj, path):
    """Safely traverse a dotted path like 'student__first_name'."""
    current = obj
    parts = path.split("__")
    for index, part in enumerate(parts):
        if current is None:
            return ""
        current = getattr(current, part, None)
        if callable(current):
            current = current()
        if hasattr(current, "all"):
            remaining = "__".join(parts[index + 1:])
            return "; ".join(str(_get_nested(item, remaining)) for item in current.all())
    return current if current is not None else ""


def _scope_export_queryset(request, queryset, export_key):
    """Back up only records belonging to the active school and allowed campuses."""
    paths = {
        "students": ("primary_campus_id", "institution_id"),
        "student_status": ("primary_campus_id", "institution_id"),
        "teachers": ("primary_campus_id", "institution_id"),
        "staff": ("primary_campus_id", "institution_id"),
        "subjects": (None, "institution_id"),
        "fee_categories": (None, "institution_id"),
        "invoices": ("enrollment__campus_id", "institution_id"),
        "fees": ("enrollment__campus_id", "institution_id"),
        "payments": ("invoice__enrollment__campus_id", "invoice__institution_id"),
        "attendance": ("campus_id", "academic_year__school_id"),
        "enrollments": ("campus_id", "academic_year__school_id"),
        "results": ("exam__campus_id", "exam__academic_year__school_id"),
    }
    campus_path, institution_path = paths[export_key]
    institution = get_institution(request)
    if institution is None:
        return queryset.none()
    queryset = queryset.filter(**{institution_path: institution.pk})
    return apply_campus_scope(queryset, request, campus_path, institution_field=None)


def _apply_filters(request, queryset, export_key):
    """Apply common query params."""
    search = request.query_params.get("search", "").strip()
    status = request.query_params.get("status", "")
    if status and hasattr(queryset.model, "status"):
        queryset = queryset.filter(status=status)

    if search:
        if export_key == "students":
            from django.db.models import Q
            queryset = queryset.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(admission_number__icontains=search)
            )
        elif export_key == "teachers":
            from django.db.models import Q
            queryset = queryset.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(employee_number__icontains=search)
            )

    return queryset

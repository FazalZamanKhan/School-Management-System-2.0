"""Shared school/campus ownership rules for student lists and aggregates."""

from django.db.models import Q

from apps.accounts.access import apply_campus_scope, campus_access
from apps.accounts.middleware import require_active_school


def school_scoped_students(queryset, request):
    institution = require_active_school(request)
    if institution is None:
        # Preserve the executive dashboard's platform-wide super-admin view
        # when no school is selected. Ordinary users always fail closed.
        if request.user.is_superuser or request.user.has_any_role(["super_admin"]):
            return apply_campus_scope(queryset, request, "primary_campus_id", institution_field=None).distinct()
        return queryset.none()

    # Explicit ownership wins. Only untagged legacy records can derive their
    # school from an enrollment; NULL is not a license to count in every school.
    queryset = queryset.filter(
        Q(institution=institution)
        | Q(institution__isnull=True, enrollments__academic_year__school=institution)
    )
    access = campus_access(request)
    if not access["global"]:
        queryset = queryset.filter(
            enrollments__campus_id__in=access["allowed_ids"] or [-1],
            enrollments__status="active",
        )
    elif access["requested"]:
        queryset = queryset.filter(
            enrollments__campus_id=access["requested"], enrollments__status="active",
        )
    return queryset.distinct()

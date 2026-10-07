"""Authenticated media serving.

All uploaded files (photos, documents, branding assets) are served
through this view instead of being publicly accessible. Users can only
access files belonging to their own institution.

Public branding assets (school logos, favicons, login backgrounds) are
exempted — they need to be accessible on public login pages.
"""

import mimetypes
import os

from django.conf import settings
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist
from django.http import FileResponse, Http404
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.accounts.access import user_allowed_campus_ids, is_global
from apps.accounts.scopes import is_manager, is_teacher, is_parent, is_student, parent_student_ids, teacher_student_ids
from apps.students.models import Student
from apps.teachers.models import Teacher

# Paths that are always public (login-page assets, favicon)
PUBLIC_PREFIXES = [
    "school/branding/",
]

# Extensions that are safe to serve publicly regardless of prefix
PUBLIC_EXTENSIONS = {".ico", ".svg", ".png", ".jpg", ".jpeg", ".gif"}


def _is_public_path(file_path):
    """Check if this file should be served without authentication."""
    normalized = file_path.replace("\\", "/")

    for prefix in PUBLIC_PREFIXES:
        if normalized.startswith(prefix):
            # Branding images are public only if they're image extensions
            _, ext = os.path.splitext(normalized)
            return ext.lower() in PUBLIC_EXTENSIONS

    return False


def _check_student_document_access(file_path, user, institution):
    """Verify access to student document by exact file path match."""
    if not file_path.startswith("students/documents/"):
        return False

    try:
        from apps.students.models import StudentDocument
        doc = StudentDocument.objects.select_related(
            "student", "student__primary_campus", "student__user"
        ).get(file=file_path)
    except StudentDocument.DoesNotExist:
        return False
    except StudentDocument.MultipleObjectsReturned:
        # Fallback: deny if ambiguous
        return False

    # Institution match
    if institution is not None and doc.institution_id != institution.id:
        return False

    # Campus access for non-global
    if not is_global(user):
        student = doc.student
        # Get allowed campus ids for user
        allowed_campus_ids = user_allowed_campus_ids(user, institution=institution)
        student_campus_ids = set(
            student.enrollments.filter(status="active").values_list("campus_id", flat=True)
        )
        if not student_campus_ids & allowed_campus_ids:
            return False

    # Role-based access: uploader, parent of student, student self, teacher of student, manager
    if doc.uploaded_by_id == user.id:
        return True
    if is_manager(user):
        return True
    if is_parent(user):
        return doc.student_id in parent_student_ids(user)
    if is_student(user):
        return doc.student.user_id == user.id
    if is_teacher(user):
        return doc.student_id in teacher_student_ids(user)

    return False


def _check_employee_document_access(file_path, user, institution):
    """Verify access to employee document by exact file path match."""
    if not file_path.startswith("hr/documents/"):
        return False

    try:
        from apps.hr.models import EmployeeDocument
        doc = EmployeeDocument.objects.select_related(
            "employee", "employee__institution", "employee__primary_campus",
            "employee__teacher", "employee__teacher__user",
            "employee__staff_profile", "employee__staff_profile__user",
        ).get(file=file_path)
    except EmployeeDocument.DoesNotExist:
        return False
    except EmployeeDocument.MultipleObjectsReturned:
        return False

    # Institution match
    if institution is not None and doc.employee.institution_id != institution.id:
        return False

    # Campus access for non-global
    if not is_global(user):
        allowed_campus_ids = user_allowed_campus_ids(user, institution=institution)
        if doc.employee.primary_campus_id not in allowed_campus_ids:
            return False

    # Role-based access: uploader, employee self, manager, accountant/hr
    if doc.uploaded_by_id == user.id:
        return True
    # Employee self: check via teacher or staff_profile user
    employee_user_id = None
    if doc.employee.teacher_id:
        employee_user_id = doc.employee.teacher.user_id
    elif doc.employee.staff_profile_id:
        employee_user_id = doc.employee.staff_profile.user_id
    if employee_user_id == user.id:
        return True
    if is_manager(user):
        return True
    # Accountant/HR roles
    if user.has_any_role(["accountant", "hr", "payroll_admin"]):
        return True

    return False


def _check_profile_access(file_path, user, institution):
    """Authorize the exact profile file recorded on its owner model."""
    def same_school(profile):
        if institution is None:
            return user.is_superuser
        school_id = profile.institution_id
        if school_id is None and profile.primary_campus_id:
            school_id = profile.primary_campus.school_id
        return school_id == institution.pk

    def manager_can_view(campus_id):
        return is_manager(user) and (
            is_global(user)
            or campus_id in user_allowed_campus_ids(user, institution=institution)
        )

    try:
        if file_path.startswith("profiles/students/"):
            student = Student.objects.select_related("primary_campus", "user").get(photo=file_path)
            if not same_school(student):
                return False
            if student.user_id == user.id:
                return True
            if is_parent(user) and student.pk in parent_student_ids(user):
                return True
            if is_teacher(user) and student.pk in teacher_student_ids(user):
                return True
            return manager_can_view(student.primary_campus_id)

        if file_path.startswith("profiles/teachers/"):
            teacher = Teacher.objects.select_related("primary_campus", "user").get(photo=file_path)
            return same_school(teacher) and (
                teacher.user_id == user.id or manager_can_view(teacher.primary_campus_id)
            )

        if file_path.startswith("profiles/staff/"):
            from apps.accounts.models import StaffProfile
            staff = StaffProfile.objects.select_related("primary_campus", "user").get(photo=file_path)
            return same_school(staff) and (
                staff.user_id == user.id or manager_can_view(staff.primary_campus_id)
            )

        if file_path.startswith("profiles/users/"):
            from apps.accounts.models import User
            target = User.objects.select_related(
                "student_profile", "teacher_profile", "staff_profile"
            ).get(photo=file_path)
            if target.pk == user.pk:
                return True
            if institution is not None and target.institution_id != institution.pk:
                return False
            campus_id = next(
                (
                    profile.primary_campus_id
                    for profile in (
                        getattr(target, "staff_profile", None),
                        getattr(target, "teacher_profile", None),
                        getattr(target, "student_profile", None),
                    )
                    if profile is not None and profile.primary_campus_id
                ),
                None,
            )
            return manager_can_view(campus_id)
    except (ObjectDoesNotExist, MultipleObjectsReturned):
        return False

    return False


def _file_belongs_to_user_school(file_path, user, institution):
    """Check if the user's active institution matches the file's owner.

    For documents: strict DB lookup by exact file path.
    For profiles: heuristic with institution equality.
    """

    if institution is None and not (user and user.is_superuser):
        return False

    # Student documents - strict DB check
    if file_path.startswith("students/documents/"):
        return _check_student_document_access(file_path, user, institution)

    # Employee documents - strict DB check
    if file_path.startswith("hr/documents/"):
        return _check_employee_document_access(file_path, user, institution)

    # Profile images - heuristic with institution check
    if file_path.startswith("profiles/"):
        return _check_profile_access(file_path, user, institution)

    # Other paths: deny by default for non-superuser
    if user and user.is_superuser:
        return True

    return False


class ProtectedMediaView(APIView):
    """Serve media files with authentication."""

    permission_classes = [IsAuthenticated]

    def get(self, request, file_path=""):
        # Normalize path to prevent directory traversal
        clean = os.path.normpath(file_path).replace("\\", "/")

        if clean.startswith("..") or clean.startswith("/"):
            raise Http404

        full_path = os.path.join(settings.MEDIA_ROOT, clean)

        if not os.path.isfile(full_path):
            raise Http404

        # Public assets (branding logos on login pages)
        if _is_public_path(clean):
            return self._serve(full_path)

        # Everything else requires authentication
        if not request.user.is_authenticated:
            raise Http404

        # Tenant isolation: user must belong to an institution
        institution = getattr(request, "institution", None)

        if institution is None and not request.user.is_superuser:
            raise Http404

        # Campus-level authorization with ownership verification
        if not _file_belongs_to_user_school(clean, request.user, institution):
            raise Http404

        return self._serve(full_path)

    def _serve(self, full_path):
        content_type, _ = mimetypes.guess_type(full_path)

        if content_type is None:
            content_type = "application/octet-stream"

        response = FileResponse(
            open(full_path, "rb"),
            content_type=content_type,
        )

        response["Cache-Control"] = "private, max-age=3600"

        return response


class PublicBrandingMediaView(APIView):
    """Serve ONLY branding files without auth (for login pages)."""

    permission_classes = []
    authentication_classes = []

    def get(self, request, file_path=""):
        clean = os.path.normpath(file_path).replace("\\", "/")

        if clean.startswith("..") or clean.startswith("/"):
            raise Http404

        # Only allow image extensions
        _, ext = os.path.splitext(clean)
        if ext.lower() not in PUBLIC_EXTENSIONS:
            raise Http404

        # Reconstruct the full path under school/branding/
        full_path = os.path.join(settings.MEDIA_ROOT, "school", "branding", clean)

        if not os.path.isfile(full_path):
            raise Http404

        content_type, _ = mimetypes.guess_type(full_path)

        return FileResponse(
            open(full_path, "rb"),
            content_type=content_type or "application/octet-stream",
        )

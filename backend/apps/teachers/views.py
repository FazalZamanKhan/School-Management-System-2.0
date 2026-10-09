from django.db.models import Q
from rest_framework import generics
from rest_framework.exceptions import NotFound, ValidationError, PermissionDenied

from apps.accounts.access import apply_campus_scope, restrict_to_allowed_campuses, assert_campus_allowed
from apps.accounts.permissions import IsAdminOrReadOnly
from apps.accounts.scopes import get_teacher_profile, is_manager

from .models import Teacher, TeacherAssignment
from .serializers import (
    TeacherAssignmentSerializer,
    TeacherSerializer,
)


class TeacherListCreateView(generics.ListCreateAPIView):
    serializer_class = TeacherSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        queryset = Teacher.objects.all().order_by(
            "first_name", "last_name"
        )

        user = self.request.user

        if self.request.institution is not None:
            queryset = queryset.filter(
                Q(institution=self.request.institution)
                | Q(membership__institution=self.request.institution)
            )
        else:
            # If no institution on request, scope by user's active membership
            from apps.accounts.managers import get_current_institution
            institution = get_current_institution()
            if institution is not None:
                queryset = queryset.filter(
                    Q(institution=institution)
                    | Q(membership__institution=institution)
                )

        if not is_manager(user):
            profile = get_teacher_profile(user)

            if profile is not None:
                queryset = queryset.filter(pk=profile.pk)
            else:
                # No teacher profile and not a manager: this role has no
                # business seeing the teacher directory at all. Fail closed
                # instead of falling through to the unfiltered,
                # institution-wide queryset.
                queryset = queryset.none()

        search = self.request.query_params.get("search")

        if search:
            queryset = queryset.filter(
                Q(employee_number__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(phone__icontains=search)
                | Q(email__icontains=search)
            )

        status = self.request.query_params.get("status")

        if status:
            queryset = queryset.filter(status=status)

        gender = self.request.query_params.get("gender")

        if gender:
            queryset = queryset.filter(gender=gender)

        campus = self.request.query_params.get("campus")

        if campus:
            from apps.accounts.managers import get_current_institution

            institution = get_current_institution()
            if institution is not None:
                from apps.schools.models import Campus

                campus_qs = Campus.objects.filter(
                    school=institution, iexact=campus
                )
                if campus_qs.exists():
                    queryset = queryset.filter(campus__iexact=campus)

        queryset = restrict_to_allowed_campuses(
            queryset,
            user,
            "primary_campus_id",
        )

        return queryset

    def perform_create(self, serializer):
        institution = getattr(self.request, "institution", None)
        if institution is None:
            raise ValidationError(
                {"institution": "Select a school before adding a teacher."}
            )

        primary_campus = serializer.validated_data.get("primary_campus")
        if primary_campus is not None:
            if primary_campus.school_id != institution.id:
                raise ValidationError(
                    {
                        "primary_campus": (
                            "The selected campus does not belong to the "
                            "active school."
                        )
                    }
                )

        serializer.save(institution=institution)


class TeacherDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = TeacherSerializer

    def get_queryset(self):
        queryset = Teacher.objects.all()

        user = self.request.user
        institution = getattr(self.request, "institution", None)

        if institution is None and user.is_authenticated:
            from apps.accounts.managers import get_current_institution

            institution = get_current_institution()

        if institution is not None:
            institution_filter = Q(institution=institution) | Q(
                membership__institution=institution
            )
        else:
            # No active institution context: fail closed. An empty Q() would
            # expose every tenant's teachers to managers.
            return queryset.none()

        if not is_manager(user):
            profile = get_teacher_profile(user)

            if profile is not None:
                queryset = queryset.filter(
                    institution_filter,
                    pk=profile.pk,
                )
            else:
                queryset = queryset.none()
        else:
            queryset = queryset.filter(institution_filter)

        return queryset


class TeacherMyView(generics.RetrieveAPIView):
    """The logged-in teacher's own profile and assigned classes."""

    permission_classes = [IsAdminOrReadOnly]
    serializer_class = TeacherSerializer

    def get_object(self):
        profile = get_teacher_profile(self.request.user)

        if profile is None:
            raise NotFound(
                "No teacher profile is linked to this account."
            )

        return profile


class TeacherAssignmentListCreateView(generics.ListCreateAPIView):
    """Assign a teacher to a grade (class/section/subject)."""

    serializer_class = TeacherAssignmentSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        queryset = (
            TeacherAssignment.objects
            .select_related(
                "teacher",
                "campus",
                "class_obj",
                "section",
                "subject",
                "academic_year",
            )
            .order_by("class_obj__name", "section__name", "teacher__first_name")
        )

        teacher = self.request.query_params.get("teacher")

        if teacher:
            queryset = queryset.filter(teacher_id=teacher)

        class_obj = self.request.query_params.get("class")

        if class_obj:
            queryset = queryset.filter(class_obj_id=class_obj)

        role = self.request.query_params.get("role")

        if role:
            queryset = queryset.filter(role=role)

        academic_year = self.request.query_params.get("year")

        if academic_year:
            queryset = queryset.filter(
                academic_year_id=academic_year
            )

        # Scope to the active institution via the teacher's institution.
        institution = getattr(self.request, "institution", None)
        if institution is not None:
            queryset = queryset.filter(teacher__institution=institution)
        else:
            queryset = queryset.none()

        # Campus restriction for non-global roles (keeps a campus_admin or
        # principal from seeing assignments at other campuses of the school).
        return apply_campus_scope(queryset, self.request, "campus_id", institution_field=None)

    def _validate_write_scope(self, serializer):
        institution = getattr(self.request, "institution", None)
        if institution is not None:
            teacher = serializer.validated_data.get("teacher")
            if teacher is not None and teacher.institution_id != institution.id:
                raise PermissionDenied(
                    "Teacher does not belong to the active institution."
                )
        campus = serializer.validated_data.get("campus")
        if campus is not None:
            assert_campus_allowed(self.request.user, campus.pk, request=self.request)

    def perform_create(self, serializer):
        self._validate_write_scope(serializer)
        serializer.save()

    def perform_update(self, serializer):
        self._validate_write_scope(serializer)
        serializer.save()

    def perform_destroy(self, instance):
        institution = getattr(self.request, "institution", None)
        if institution is not None and instance.teacher.institution_id != institution.id:
            raise PermissionDenied(
                "Assignment belongs to a different institution."
            )
        instance.delete()


class TeacherAssignmentDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = TeacherAssignmentSerializer

    def get_queryset(self):
        queryset = (
            TeacherAssignment.objects
            .select_related(
                "teacher",
                "campus",
                "class_obj",
                "section",
                "subject",
                "academic_year",
            )
        )

        # Scope to the active institution via the teacher's institution.
        institution = getattr(self.request, "institution", None)
        if institution is not None:
            queryset = queryset.filter(teacher__institution=institution)
        else:
            queryset = queryset.none()

        return apply_campus_scope(
            queryset, self.request, "campus_id", institution_field=None
        )

    def perform_update(self, serializer):
        institution = getattr(self.request, "institution", None)
        teacher = serializer.validated_data.get("teacher") or serializer.instance.teacher
        if institution is not None and teacher.institution_id != institution.id:
            raise PermissionDenied(
                "Teacher does not belong to the active institution."
            )
        campus = serializer.validated_data.get("campus")
        if campus is None and serializer.instance:
            campus = serializer.instance.campus
        if campus is not None:
            assert_campus_allowed(self.request.user, campus.pk, request=self.request)
        serializer.save()

    def perform_destroy(self, instance):
        institution = getattr(self.request, "institution", None)
        if institution is not None and instance.teacher.institution_id != institution.id:
            raise PermissionDenied(
                "Assignment belongs to a different institution."
            )
        instance.delete()

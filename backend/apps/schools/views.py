import logging

from django.db.models import Count, Q
from rest_framework import generics, status, viewsets
from rest_framework.views import APIView
from rest_framework.mixins import (
    DestroyModelMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
)
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework import serializers
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404
from datetime import date

logger = logging.getLogger(__name__)

from apps.accounts.access import apply_campus_scope, assert_campus_allowed, institution_scope
from apps.accounts.permissions import HasActiveInstitution, IsAdminOrReadOnly, IsSuperAdmin
from apps.accounts.models import Role, InstitutionMembership, RoleAssignment, User
from apps.students.models import Student, Enrollment
from .models import (
    AcademicUnit,
    AcademicYear,
    AcademicCalendar,
    Campus,
    Class,
    School,
    Section,
    Subject,
    SubjectOffering,
    Term,
)
from .serializers import (
    AcademicCalendarSerializer,
    AcademicUnitSerializer,
    AcademicYearSerializer,
    CampusSerializer,
    ClassSerializer,
    SchoolSerializer,
    SectionSerializer,
    SubjectOfferingSerializer,
    SubjectSerializer,
    TermSerializer,
)


class NoPaginationMixin:
    pagination_class = None


def populate_campus_counts(queryset):
    class_counts = (
        Class.objects.filter(status="active")
        .values("unit__campus_id")
        .annotate(total=Count("id"))
    )
    class_map = {
        item["unit__campus_id"]: item["total"]
        for item in class_counts
    }

    section_counts = (
        Section.objects.filter(status="active")
        .values("class_obj__unit__campus_id")
        .annotate(total=Count("id"))
    )
    section_map = {
        item["class_obj__unit__campus_id"]: item["total"]
        for item in section_counts
    }

    student_counts = (
        Enrollment.objects.filter(status="active")
        .values("campus_id")
        .annotate(total=Count("student", distinct=True))
    )
    student_map = {
        item["campus_id"]: item["total"]
        for item in student_counts
    }

    for campus in queryset:
        campus.class_count = class_map.get(campus.id, 0)
        campus.section_count = section_map.get(campus.id, 0)
        campus.student_count = student_map.get(campus.id, 0)

    return queryset


class SchoolViewSet(NoPaginationMixin, viewsets.GenericViewSet, generics.ListAPIView):
    serializer_class = SchoolSerializer
    permission_classes = [HasActiveInstitution, IsAdminOrReadOnly]

    def get_queryset(self):
        return School.objects.filter(
            pk=self.request.institution.pk
        ).order_by("name")

    def _is_platform_admin(self):
        user = self.request.user
        return bool(user.is_superuser or user.has_any_role(["super_admin"]))

    def _resolve_school(self, pk):
        """Pick the target school for admin-management actions.

        Platform admins may target any tenant by URL pk (mirrors
        TenantDetailView's cross-tenant resolution). Everyone else is locked
        to their active institution, so a school can never manage another
        school's admins (fail closed).
        """
        if self._is_platform_admin():
            return get_object_or_404(School, pk=pk)
        return self.get_object()

    @action(detail=True, methods=["post"], permission_classes=[HasActiveInstitution, IsSuperAdmin])
    def pause(self, request, pk=None):
        """Pause the school - prevents login, attendance, fees, etc."""
        school = self.get_object()
        school.pause(request.user)
        return Response({"detail": "School paused successfully."})

    @action(detail=True, methods=["post"], permission_classes=[HasActiveInstitution, IsSuperAdmin])
    def activate(self, request, pk=None):
        """Activate the school - resume all operations."""
        school = self.get_object()
        school.activate()
        return Response({"detail": "School activated successfully."})

    @action(detail=True, methods=["post"], permission_classes=[HasActiveInstitution, IsSuperAdmin])
    def archive(self, request, pk=None):
        """Archive the school."""
        school = self.get_object()
        school.archive(request.user)
        return Response({"detail": "School archived successfully."})

    @action(detail=True, methods=["post"], permission_classes=[HasActiveInstitution, IsSuperAdmin])
    def unarchive(self, request, pk=None):
        """Unarchive the school."""
        school = self.get_object()
        school.unarchive()
        return Response({"detail": "School unarchived successfully."})

    # =============================================================================
    # SCHOOL ADMIN MANAGEMENT
    # =============================================================================

    class SchoolAdminSerializer(serializers.Serializer):
        """Serializer for school admin assignment."""
        user_id = serializers.IntegerField(help_text="ID of the user to assign as admin")
        username = serializers.CharField(read_only=True)
        email = serializers.CharField(read_only=True)

    class SchoolAdminAssignSerializer(serializers.Serializer):
        """Serializer for assigning an existing user as school admin."""
        user_id = serializers.IntegerField(help_text="ID of the existing user to assign as school admin")

        def validate_user_id(self, value):
            from apps.accounts.models import User, InstitutionMembership
            try:
                user = User.objects.get(pk=value)
            except User.DoesNotExist:
                raise serializers.ValidationError("User not found.")

            # Check user is active
            if not user.is_active:
                raise serializers.ValidationError("User is not active.")

            # Check user has active membership in this school
            school = self.context.get("school")
            if not school:
                raise serializers.ValidationError("School context required.")

            membership = InstitutionMembership.objects.filter(
                user=user,
                institution=school,
                status="active",
            ).first()
            if not membership:
                raise serializers.ValidationError("User does not have an active membership in this school.")

            # Check user doesn't already have ADMIN role in this school
            from apps.accounts.models import RoleAssignment, Role
            if RoleAssignment.objects.filter(
                membership=membership,
                role=Role.ADMIN,
            ).exists():
                raise serializers.ValidationError("User is already a school admin.")

            return value

    @action(detail=True, methods=["get"], permission_classes=[HasActiveInstitution, IsAdminOrReadOnly])
    def admins(self, request, pk=None):
        """List all school admins for this school."""
        school = self._resolve_school(pk)

        from apps.accounts.models import RoleAssignment, Role, InstitutionMembership

        # Get all active memberships in this school with ADMIN role (campus=NULL)
        admin_assignments = RoleAssignment.objects.filter(
            membership__institution=school,
            membership__status="active",
            role=Role.ADMIN,
            campus__isnull=True,
        ).select_related("membership__user")

        admins = []
        for assignment in admin_assignments:
            user = assignment.membership.user
            admins.append({
                "user_id": user.id,
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "is_active": user.is_active,
                "assigned_at": assignment.created_at,
            })

        return Response({"admins": admins, "count": len(admins)})

    @action(detail=True, methods=["post"], permission_classes=[HasActiveInstitution, IsAdminOrReadOnly])
    def assign_admin(self, request, pk=None):
        """Assign an existing user as school admin."""
        school = self._resolve_school(pk)

        serializer = self.SchoolAdminAssignSerializer(
            data=request.data,
            context={"school": school, "request": request},
        )
        serializer.is_valid(raise_exception=True)

        user_id = serializer.validated_data["user_id"]

        from apps.accounts.models import User, InstitutionMembership, RoleAssignment, Role
        from apps.accounts.models import assign_role_safely

        user = User.objects.get(pk=user_id)
        membership = InstitutionMembership.objects.get(
            user=user,
            institution=school,
            status="active",
        )

        # Assign ADMIN role (school-level, campus=NULL)
        assignment, created, note = assign_role_safely(membership, Role.ADMIN)

        if not created and note:
            return Response(
                {"detail": note, "user_id": user.id},
                status=status.HTTP_409_CONFLICT,
            )

        # Update denormalized institution FK if not set
        if user.institution_id != school.id:
            user.institution = school
            user.save(update_fields=["institution"])

        return Response({
            "detail": "User assigned as school admin successfully.",
            "user_id": user.id,
            "username": user.username,
            "email": user.email,
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], permission_classes=[HasActiveInstitution, IsAdminOrReadOnly])
    def remove_admin(self, request, pk=None):
        """Remove school admin assignment."""
        school = self._resolve_school(pk)

        user_id = request.data.get("user_id")
        if not user_id:
            return Response(
                {"detail": "user_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from apps.accounts.models import User, InstitutionMembership, RoleAssignment, Role

        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response(
                {"detail": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        membership = InstitutionMembership.objects.filter(
            user=user,
            institution=school,
            status="active",
        ).first()

        if not membership:
            return Response(
                {"detail": "User does not have an active membership in this school."},
                status=status.HTTP_404_NOT_FOUND,
            )

        assignment = RoleAssignment.objects.filter(
            membership=membership,
            role=Role.ADMIN,
            campus__isnull=True,
        ).first()

        if not assignment:
            return Response(
                {"detail": "User is not a school admin."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Prevent removing the last admin? Not required per spec (0..N allowed)
        # But we should prevent self-removal if only one admin? Let's not enforce - let the admin decide.

        assignment.delete()

        return Response({"detail": "School admin removed successfully."})


class CampusViewSet(
    NoPaginationMixin,
    RetrieveModelMixin,
    UpdateModelMixin,
    DestroyModelMixin,
    viewsets.GenericViewSet,
    generics.ListCreateAPIView,
):
    serializer_class = CampusSerializer
    permission_classes = [HasActiveInstitution, IsAdminOrReadOnly]

    def _is_platform_admin(self):
        user = self.request.user
        return bool(user.is_superuser or user.has_any_role(["super_admin"]))

    def _resolve_campus(self, pk):
        """Pick the target campus for admin-management actions.

        Platform admins may target any campus by URL pk (cross-tenant
        management regardless of the active institution). Everyone else stays
        locked to their active institution via the scoped queryset (fail
        closed).
        """
        if self._is_platform_admin():
            return get_object_or_404(Campus, pk=pk)
        return self.get_object()

    def get_queryset(self):
        if self._is_platform_admin():
            queryset = Campus.objects.all()
            school_param = self.request.query_params.get("school")

            if school_param:
                queryset = queryset.filter(school_id=school_param)
            else:
                # Platform admin without a school filter keeps the current
                # institution scope so other pages behave unchanged.
                queryset = queryset.filter(school=self.request.institution)
        else:
            queryset = Campus.objects.filter(
                school=self.request.institution
            )

        queryset = queryset.select_related("school").order_by("name")

        search = self.request.query_params.get("search")

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(city__icontains=search)
            )

        status = self.request.query_params.get("status")

        if status:
            queryset = queryset.filter(status=status)

        return populate_campus_counts(queryset)

    def _resolve_school(self):
        """Pick the owning school: platform admins may choose any school,
        everyone else is locked to their active institution."""
        requested = self.request.data.get("school")

        if self._is_platform_admin() and requested:
            school = School.objects.filter(pk=requested).first()

            if school is None:
                raise serializers.ValidationError(
                    {"school": "School not found."}
                )

            return school

        return self.request.institution

    def perform_create(self, serializer):
        # Check if admin data is provided in the request
        admin_data = self.request.data.get("admin", {})

        campus = serializer.save(school=self._resolve_school())

        # If admin data is provided, create the admin user linked to the school
        if admin_data:
            admin_user, admin_password = self._create_admin_user(serializer.validated_data, admin_data, campus)
            # Store admin credentials in serializer context for response
            serializer.context["admin_credentials"] = {
                "username": admin_user.username,
                "email": admin_user.email,
                "password": admin_password,
                "position": admin_data.get("position", "").strip().lower(),
            }

    def _create_admin_user(self, validated_data, admin_data, campus=None):
        """Create a user account and assign Principal/Vice Principal/Campus Admin role linked to the campus.

        Username and password are optional - they will be auto-generated if not provided.
        """
        from django.db import transaction
        from django.db.utils import IntegrityError
        from rest_framework.exceptions import ValidationError
        from apps.accounts.services import create_user_with_username
        from apps.accounts.models import Role, InstitutionMembership, RoleAssignment

        username = admin_data.get("username", "").strip()
        email = admin_data.get("email", "").strip()
        password = admin_data.get("password", "")
        first_name = admin_data.get("first_name", "")
        last_name = admin_data.get("last_name", "")
        phone = admin_data.get("phone", "")
        position = admin_data.get("position", "").strip().lower()

        # Email is still required for identification
        if not email:
            raise ValidationError(
                {"admin": "Email is required for admin creation."}
            )

        if position not in ("principal", "vice_principal", "campus_admin"):
            raise ValidationError(
                {"admin": "Position must be 'principal', 'vice_principal', or 'campus_admin'."}
            )

        role_map = {
            "principal": Role.PRINCIPAL,
            "vice_principal": Role.VICE_PRINCIPAL,
            "campus_admin": Role.CAMPUS_ADMIN,
        }

        # Auto-generate username if not provided
        if not username:
            role_prefix = {
                "principal": "principal",
                "vice_principal": "vp",
                "campus_admin": "cadmin",
            }
            if campus is None:
                raise ValidationError(
                    {"admin": "Campus is required when the username is auto-generated."}
                )
            username = f"{role_prefix[position]}-{campus.name.lower().replace(' ', '-')}"

        # Password is optional - will be auto-generated if not provided
        must_change_password = password == ""
        if not password:
            password = None  # Will be auto-generated by create_user_with_username

        role = role_map[position]

        try:
            with transaction.atomic():
                if campus is None:
                    campus = self.get_object()
                school = campus.school

                user, generated_username, generated_password = create_user_with_username(
                    base=username,
                    institution=school,
                    email=email,
                    password=password,
                    first_name=first_name or "Campus",
                    last_name=last_name or school.name,
                    must_change_password=must_change_password,
                )
                if phone:
                    user.phone = phone
                    user.save(update_fields=["phone"])

                membership, _ = InstitutionMembership.objects.get_or_create(
                    user=user,
                    institution=school,
                    defaults={"status": "active"},
                )

                # Check for existing role assignment for this campus
                existing = RoleAssignment.objects.filter(
                    campus=campus,
                    role=role,
                ).first()
                if existing:
                    role_display = role_map[position].label
                    raise ValidationError(
                        {"admin": f"A {role_display} already exists for this campus."}
                    )

                # Create campus-level role assignment (explicit campus FK)
                RoleAssignment.objects.create(
                    membership=membership,
                    role=role,
                    campus=campus,
                )

                # Auto-set user's primary_campus for profile consistency
                if hasattr(user, "staff_profile"):
                    user.staff_profile.primary_campus = campus
                    user.staff_profile.save(update_fields=["primary_campus"])
                else:
                    from apps.accounts.models import StaffProfile
                    StaffProfile.objects.create(
                        user=user,
                        institution=school,
                        primary_campus=campus,
                        employee_number=f"EMP-{user.username}",
                        first_name=first_name or "Campus",
                        last_name=last_name or school.name,
                        status="active",
                    )

                return user, generated_password
        except IntegrityError:
            raise ValidationError(
                {"admin": "Failed to create admin user - username or email already exists."}
            )

    def update(self, request, *args, **kwargs):
        # Non-platform users must never move a campus across schools.
        if not self._is_platform_admin():
            data = request.data

            if isinstance(data, dict):
                data.pop("school", None)

        return super().update(request, *args, **kwargs)

    def retrieve(self, request, pk=None):
        campus = self.get_object()
        row = populate_campus_counts(
            Campus.objects.filter(pk=campus.pk)
        )[0]
        return Response(self.get_serializer(row).data)

    def destroy(self, request, pk=None):
        """Delete campus - allowed for School Admin in their own school, or Super Admin."""
        if not self._is_platform_admin():
            # Non-platform admins can only delete campuses in their own institution
            campus = self.get_object()
            if campus.school_id != request.institution.id:
                return Response(
                    {"detail": "Permission denied."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        else:
            campus = self.get_object()

        logger.info(
            "Campus delete attempt: actor_role=%s campus_id=%s",
            request.user.primary_role if hasattr(request.user, "primary_role") else "unknown",
            campus.id,
        )

        try:
            campus.delete()
        except ProtectedError:
            return Response(
                {"detail": "Cannot delete campus: related records exist."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            {"detail": "Campus deleted successfully."},
            status=status.HTTP_200_OK,
        )

    # =============================================================================
    # CAMPUS ADMIN MANAGEMENT
    # =============================================================================

    class CampusAdminSerializer(serializers.Serializer):
        """Serializer for campus admin."""
        user_id = serializers.IntegerField(read_only=True)
        username = serializers.CharField(read_only=True)
        email = serializers.CharField(read_only=True)
        role = serializers.CharField(read_only=True)
        role_display = serializers.CharField(read_only=True)
        assigned_at = serializers.DateTimeField(read_only=True)

    class CampusAdminAssignSerializer(serializers.Serializer):
        """Serializer for assigning an existing user as campus admin."""
        user_id = serializers.IntegerField(help_text="ID of the existing user to assign as campus admin")
        role = serializers.ChoiceField(
            choices=[("campus_admin", "Campus Admin"), ("principal", "Principal"), ("vice_principal", "Vice Principal")],
            default="campus_admin",
            help_text="Role to assign (default: campus_admin)"
        )

        def validate_user_id(self, value):
            from apps.accounts.models import User, InstitutionMembership
            try:
                user = User.objects.get(pk=value)
            except User.DoesNotExist:
                raise serializers.ValidationError("User not found.")

            if not user.is_active:
                raise serializers.ValidationError("User is not active.")

            campus = self.context.get("campus")
            if not campus:
                raise serializers.ValidationError("Campus context required.")

            school = campus.school
            membership = InstitutionMembership.objects.filter(
                user=user,
                institution=school,
                status="active",
            ).first()
            if not membership:
                raise serializers.ValidationError("User does not have an active membership in this school.")

            # Check for existing role assignment for this campus
            from apps.accounts.models import RoleAssignment, Role
            role_map = {
                "principal": Role.PRINCIPAL,
                "vice_principal": Role.VICE_PRINCIPAL,
                "campus_admin": Role.CAMPUS_ADMIN,
            }
            role_value = role_map[self.initial_data.get("role", "campus_admin")]

            if RoleAssignment.objects.filter(
                membership=membership,
                role=role_value,
                campus=campus,
            ).exists():
                raise serializers.ValidationError(f"User already has {role_value} role for this campus.")

            # Check singleton constraint for the role on this campus
            if RoleAssignment.objects.filter(
                campus=campus,
                role=role_value,
            ).exists():
                raise serializers.ValidationError(f"A {role_value} already exists for this campus.")

            return value

    @action(detail=True, methods=["get"], permission_classes=[HasActiveInstitution, IsAdminOrReadOnly])
    def admin(self, request, pk=None):
        """Get the campus admin for this campus."""
        campus = self._resolve_campus(pk)

        from apps.accounts.models import RoleAssignment, Role

        # Get campus-level role assignments for this campus
        campus_roles = [Role.CAMPUS_ADMIN, Role.PRINCIPAL, Role.VICE_PRINCIPAL]
        assignments = RoleAssignment.objects.filter(
            campus=campus,
            role__in=campus_roles,
        ).select_related("membership__user")

        admins = []
        for assignment in assignments:
            user = assignment.membership.user
            admins.append({
                "user_id": user.id,
                "username": user.username,
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "role": assignment.role,
                "role_display": assignment.get_role_display(),
                "is_active": user.is_active,
                "assigned_at": assignment.created_at,
            })

        return Response({"admins": admins, "count": len(admins)})

    @action(detail=True, methods=["post"], permission_classes=[HasActiveInstitution, IsAdminOrReadOnly])
    def assign_admin(self, request, pk=None):
        """Assign an existing user as campus admin (Campus Admin, Principal, or Vice Principal)."""
        campus = self._resolve_campus(pk)

        serializer = self.CampusAdminAssignSerializer(
            data=request.data,
            context={"campus": campus, "request": request},
        )
        serializer.is_valid(raise_exception=True)

        user_id = serializer.validated_data["user_id"]
        role_value = serializer.validated_data["role"]

        from apps.accounts.models import User, InstitutionMembership, RoleAssignment, Role
        from apps.accounts.models import assign_role_safely

        role_map = {
            "campus_admin": Role.CAMPUS_ADMIN,
            "principal": Role.PRINCIPAL,
            "vice_principal": Role.VICE_PRINCIPAL,
        }
        role = role_map[role_value]

        user = User.objects.get(pk=user_id)
        school = campus.school
        membership = InstitutionMembership.objects.get(
            user=user,
            institution=school,
            status="active",
        )

        # Assign campus-level role with explicit campus FK
        assignment, created, note = assign_role_safely(membership, role, campus=campus)

        if not created and note:
            return Response(
                {"detail": note, "user_id": user.id},
                status=status.HTTP_409_CONFLICT,
            )

        # Update denormalized institution FK if not set
        if user.institution_id != school.id:
            user.institution = school
            user.save(update_fields=["institution"])

        # Update StaffProfile primary_campus for consistency
        if hasattr(user, "staff_profile"):
            user.staff_profile.primary_campus = campus
            user.staff_profile.save(update_fields=["primary_campus"])
        else:
            from apps.accounts.models import StaffProfile
            StaffProfile.objects.create(
                user=user,
                institution=school,
                primary_campus=campus,
                employee_number=f"EMP-{user.username}",
                first_name=user.first_name or "Campus",
                last_name=user.last_name or school.name,
                status="active",
            )

        return Response({
            "detail": f"User assigned as {role_value.replace('_', ' ').title()} successfully.",
            "user_id": user.id,
            "username": user.username,
            "email": user.email,
            "role": role,
        }, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], permission_classes=[HasActiveInstitution, IsAdminOrReadOnly])
    def remove_admin(self, request, pk=None):
        """Remove campus admin assignment."""
        campus = self._resolve_campus(pk)

        user_id = request.data.get("user_id")
        role = request.data.get("role")  # Optional: if not provided, remove all campus-level roles for this user on this campus

        if not user_id:
            return Response(
                {"detail": "user_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from apps.accounts.models import User, InstitutionMembership, RoleAssignment, Role

        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response(
                {"detail": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        school = campus.school
        membership = InstitutionMembership.objects.filter(
            user=user,
            institution=school,
            status="active",
        ).first()

        if not membership:
            return Response(
                {"detail": "User does not have an active membership in this school."},
                status=status.HTTP_404_NOT_FOUND,
            )

        campus_roles = [Role.CAMPUS_ADMIN, Role.PRINCIPAL, Role.VICE_PRINCIPAL]
        if role:
            # Remove specific role
            if role not in campus_roles:
                return Response(
                    {"detail": "Invalid role."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            assignments = RoleAssignment.objects.filter(
                membership=membership,
                role=role,
                campus=campus,
            )
        else:
            # Remove all campus-level roles for this user on this campus
            assignments = RoleAssignment.objects.filter(
                membership=membership,
                role__in=campus_roles,
                campus=campus,
            )

        if not assignments.exists():
            return Response(
                {"detail": "No matching campus admin assignment found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        assignments.delete()

        return Response({"detail": "Campus admin(s) removed successfully."})


def _raise_parent_not_in_school(label):
    raise serializers.ValidationError(
        {label: f"Selected {label} does not belong to your school."}
    )


class AcademicUnitListView(NoPaginationMixin, generics.ListCreateAPIView):
    serializer_class = AcademicUnitSerializer
    permission_classes = [HasActiveInstitution, IsAdminOrReadOnly]

    def get_queryset(self):
        queryset = (
            AcademicUnit.objects.filter(campus__school=self.request.institution)
            .select_related("campus")
            .order_by("campus__name", "name")
        )

        queryset = apply_campus_scope(
            queryset,
            self.request,
            "campus_id",
        )

        return queryset

    def perform_create(self, serializer):
        campus_id = serializer.validated_data.get("campus")
        ok = campus_id and Campus.objects.filter(
            pk=campus_id.pk,
            school=self.request.institution,
        ).exists()

        if not ok:
            _raise_parent_not_in_school("campus")

        serializer.save()


class ClassListView(NoPaginationMixin, generics.ListCreateAPIView):
    serializer_class = ClassSerializer
    permission_classes = [HasActiveInstitution, IsAdminOrReadOnly]

    def get_queryset(self):
        queryset = (
            Class.objects.filter(unit__campus__school=self.request.institution)
            .select_related("unit", "unit__campus")
            .annotate(
                student_count=Count(
                    "student_enrollments",
                    filter=Q(student_enrollments__status="active"),
                    distinct=True,
                ),
                section_count=Count("sections", distinct=True),
            )
            .order_by("level", "name")
        )

        queryset = apply_campus_scope(
            queryset,
            self.request,
            "unit__campus_id",
        )

        status = self.request.query_params.get("status")

        if status:
            queryset = queryset.filter(status=status)

        return queryset

    def perform_create(self, serializer):
        unit = serializer.validated_data.get("unit")
        ok = unit and AcademicUnit.objects.filter(
            pk=unit.pk,
            campus__school=self.request.institution,
        ).exists()

        if not ok:
            _raise_parent_not_in_school("unit")

        serializer.save()


class SectionListView(NoPaginationMixin, generics.ListCreateAPIView):
    serializer_class = SectionSerializer
    permission_classes = [HasActiveInstitution, IsAdminOrReadOnly]

    def get_queryset(self):
        queryset = section_queryset(self.request)

        class_obj = self.request.query_params.get("class")

        if class_obj:
            queryset = queryset.filter(class_obj_id=class_obj)

        return queryset

    def perform_create(self, serializer):
        class_obj = serializer.validated_data.get("class_obj")
        ok = class_obj and Class.objects.filter(
            pk=class_obj.pk,
            unit__campus__school=self.request.institution,
        ).exists()

        if not ok:
            _raise_parent_not_in_school("class_obj")

        serializer.save()


class SectionDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = SectionSerializer
    permission_classes = [HasActiveInstitution, IsAdminOrReadOnly]
    queryset = Section.objects.all()

    def get_queryset(self):
        return section_queryset(self.request)

    def perform_destroy(self, instance):
        assert_campus_allowed(self.request.user, instance.class_obj.unit.campus_id)
        instance.delete()

    def perform_update(self, serializer):
        instance = self.get_object()
        assert_campus_allowed(self.request.user, instance.class_obj.unit.campus_id)
        serializer.save()


def section_queryset(request):
    """Base queryset for Section views, scoped to the current institution
    and campus, with the class parent validated against the institution."""
    queryset = (
        Section.objects.filter(
            class_obj__unit__campus__school=request.institution
        )
        .select_related("class_obj", "class_obj__unit__campus")
        .annotate(
            student_count=Count(
                "student_enrollments",
                filter=Q(student_enrollments__status="active"),
                distinct=True,
            ),
        )
        .order_by("class_obj__name", "name")
    )

    return apply_campus_scope(
        queryset,
        request,
        "class_obj__unit__campus_id",
    )


class AcademicYearListView(NoPaginationMixin, generics.ListCreateAPIView):
    serializer_class = AcademicYearSerializer
    permission_classes = [HasActiveInstitution, IsAdminOrReadOnly]

    def get_queryset(self):
        return AcademicYear.objects.filter(
            school=self.request.institution
        ).select_related("school").order_by("-start_date")

    def perform_create(self, serializer):
        serializer.save(school=self.request.institution)


class AcademicYearDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AcademicYearSerializer
    permission_classes = [HasActiveInstitution, IsAdminOrReadOnly]

    def get_queryset(self):
        return AcademicYear.objects.filter(
            school=self.request.institution
        ).select_related("school")


class AcademicYearActionView(APIView):
    """Set an academic year's status (e.g. activate/complete).

    Activating a year automatically completes any other active year so
    there is exactly one active year per school.
    """

    permission_classes = [HasActiveInstitution, IsAdminOrReadOnly]

    def post(self, request, pk, action):
        year = get_object_or_404(
            AcademicYear.objects.filter(school=request.institution),
            pk=pk,
        )
        status_map = {
            "activate": "active",
            "complete": "completed",
            "mark-upcoming": "upcoming",
        }
        if action not in status_map:
            return Response(
                {"detail": "Invalid action."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        new_status = status_map[action]
        with transaction.atomic():
            if new_status == "active":
                AcademicYear.objects.filter(
                    school=request.institution,
                    status="active",
                ).exclude(pk=year.pk).update(status="completed")
            year.status = new_status
            year.save(update_fields=["status", "updated_at"])

        return Response(AcademicYearSerializer(year).data)


class TermListView(NoPaginationMixin, generics.ListCreateAPIView):
    serializer_class = TermSerializer
    permission_classes = [HasActiveInstitution, IsAdminOrReadOnly]

    def get_queryset(self):
        return Term.objects.filter(
            academic_year__school=self.request.institution
        ).select_related("academic_year").order_by(
            "academic_year", "start_date"
        )

    def perform_create(self, serializer):
        academic_year = serializer.validated_data.get("academic_year")
        ok = academic_year and AcademicYear.objects.filter(
            pk=academic_year.pk,
            school=self.request.institution,
        ).exists()

        if not ok:
            _raise_parent_not_in_school("academic_year")

        serializer.save()


class TermDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TermSerializer
    permission_classes = [HasActiveInstitution, IsAdminOrReadOnly]

    def get_queryset(self):
        return Term.objects.filter(
            academic_year__school=self.request.institution
        ).select_related("academic_year")


class TermActionView(APIView):
    """Set a term's status (activate/complete/mark-upcoming).

    Activating a term completes the other terms of its academic year.
    """

    permission_classes = [HasActiveInstitution, IsAdminOrReadOnly]

    def post(self, request, pk, action):
        term = get_object_or_404(
            Term.objects.filter(academic_year__school=request.institution),
            pk=pk,
        )
        status_map = {
            "activate": "active",
            "complete": "completed",
            "mark-upcoming": "upcoming",
        }
        if action not in status_map:
            return Response(
                {"detail": "Invalid action."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        new_status = status_map[action]
        with transaction.atomic():
            if new_status == "active":
                term.academic_year.terms.exclude(pk=term.pk).update(
                    status="completed"
                )
            term.status = new_status
            term.save(update_fields=["status", "updated_at"])

        return Response(TermSerializer(term).data)


class SubjectListView(NoPaginationMixin, generics.ListAPIView):
    serializer_class = SubjectSerializer
    permission_classes = [HasActiveInstitution, IsAdminOrReadOnly]

    def get_queryset(self):
        return institution_scope(Subject.objects.all(), self.request).order_by("name")


class SubjectOfferingListView(NoPaginationMixin, generics.ListAPIView):
    serializer_class = SubjectOfferingSerializer
    permission_classes = [HasActiveInstitution, IsAdminOrReadOnly]

    def get_queryset(self):
        queryset = (
            SubjectOffering.objects.filter(
                class_obj__unit__campus__school=self.request.institution
            )
            .select_related(
                "subject",
                "class_obj",
                "class_obj__unit__campus",
                "academic_year",
            )
            .order_by("class_obj__name", "subject__name")
        )

        queryset = apply_campus_scope(
            queryset,
            self.request,
            "class_obj__unit__campus_id",
        )

        class_obj = self.request.query_params.get("class")

        if class_obj:
            queryset = queryset.filter(class_obj_id=class_obj)

        return queryset

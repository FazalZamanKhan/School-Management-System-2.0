from datetime import date
from uuid import uuid4
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework import generics, status
from rest_framework.exceptions import (
    NotFound,
    PermissionDenied,
    ValidationError as RestValidationError,
)
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from decimal import Decimal

from apps.accounts.access import apply_campus_scope, assert_campus_allowed, campus_access, get_institution
from apps.accounts.middleware import require_active_school
from apps.accounts.permissions import (
    IsAdminOrReadOnly,
    IsAdminRole,
    IsAcademicMemberRole,
    IsStaffRole,
)
from apps.accounts.scopes import (
    get_guardian_profile,
    get_student_profile,
    is_manager,
    is_parent,
    is_student,
    parent_student_ids,
    parent_scope_filter,
    teacher_scope_filter,
)
from apps.schools.models import AcademicYear, Campus

from .models import (
    Guardian,
    Student,
    StudentGuardian,
    AdmissionApplication,
    StudentLifecycleEvent,
    StudentLeaveRequest,
    Enrollment,
    StudentDocument,
    Inquiry,
    AcademicHistory,
    TransferCertificate,
    CampusTransfer,
    SectionTransfer,
    StudentAlumni,
    ProgressionRecord,
)
from .progression import bulk_promote, promote_student
from .serializers import (
    EnrollmentCreateSerializer,
    GuardianCreateSerializer,
    GuardianSerializer,
    StudentDocumentSerializer,
    StudentSerializer,
    StudentGuardianSerializer,
    AdmissionApplicationSerializer,
    StudentLifecycleEventSerializer,
    ProgressionRecordSerializer,
    BatchPromotionSerializer,
    BatchResultSerializer,
    SinglePromotionSerializer,
    StudentLeaveRequestSerializer,
    InquirySerializer,
    InquiryCreateSerializer,
    AcademicHistorySerializer,
    TransferCertificateSerializer,
    TransferCertificateIssueSerializer,
    Student360Serializer,
    CampusTransferSerializer,
    CampusTransferCreateSerializer,
    SectionTransferSerializer,
    SectionTransferCreateSerializer,
    StudentAlumniSerializer,
)


def institution_queryset(queryset, request):
    institution = getattr(request, "institution", None)
    if institution is None:
        return queryset.none()
    return queryset.filter(academic_year__school=institution)


def campus_scoped(queryset, request, field="campus_id"):
    access = campus_access(request)
    if access["global"]:
        if access["requested"]:
            return queryset.filter(**{field: access["requested"]})
        return queryset
    return queryset.filter(**{f"{field}__in": access["allowed_ids"] or [-1]})


class NoPaginationMixin:
    pagination_class = None


class AdmissionApplicationListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminRole]
    serializer_class = AdmissionApplicationSerializer

    def get_queryset(self):
        queryset = institution_queryset(
            AdmissionApplication.objects.select_related(
                "guardian", "campus", "academic_year", "class_obj", "section"
            ),
            self.request,
        )
        queryset = campus_scoped(queryset, self.request)
        status = self.request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)
        campus = self.request.query_params.get("campus")
        if campus:
            assert_campus_allowed(self.request.user, campus)
            queryset = queryset.filter(campus_id=campus)
        return queryset


class AdmissionApplicationDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAdminRole]
    serializer_class = AdmissionApplicationSerializer

    def get_queryset(self):
        return campus_scoped(
            institution_queryset(AdmissionApplication.objects.all(), self.request),
            self.request,
        )


class AdmissionApplicationReviewView(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request, pk):
        application = get_object_or_404(
            campus_scoped(
                institution_queryset(AdmissionApplication.objects.select_related("guardian"), request),
                request,
            ),
            pk=pk,
        )
        action = request.data.get("action")
        if action not in ("submit", "under_review", "reject"):
            return Response({"detail": "Invalid review action."}, status=400)
        if action == "submit":
            application.status = "submitted"
            from django.utils import timezone
            application.submitted_at = timezone.now()
        elif action == "under_review":
            application.status = "under_review"
        else:
            application.status = "rejected"
            application.review_notes = request.data.get("review_notes", "")
        application.reviewed_by = request.user
        from django.utils import timezone
        application.reviewed_at = timezone.now()
        application.save(update_fields=["status", "submitted_at", "reviewed_by", "reviewed_at", "review_notes", "updated_at"])
        return Response(AdmissionApplicationSerializer(application, context={"request": request}).data)


class AdmissionApplicationAcceptView(APIView):
    permission_classes = [IsAdminRole]

    @transaction.atomic
    def post(self, request, pk):
        application = get_object_or_404(
            campus_scoped(
                institution_queryset(AdmissionApplication.objects.select_related("guardian"), request),
                request,
            ),
            pk=pk,
        )
        if application.status not in ("submitted", "under_review"):
            return Response({"detail": "Only submitted applications can be accepted."}, status=400)
        if application.guardian_id is None:
            return Response({"detail": "A guardian is required before acceptance."}, status=400)
        if application.section_id is None:
            return Response({"detail": "A section is required before acceptance."}, status=400)
        admission_number = request.data.get("admission_number") or application.application_number
        # Scope admission number uniqueness to the active institution.
        institution = get_institution(request)
        if institution is None:
            from apps.accounts.managers import get_current_institution
            institution = get_current_institution()
        if institution is not None:
            exists = Student.objects.filter(
                admission_number=admission_number,
                institution=institution,
            ).exists()
        else:
            # No institution available — reject to prevent cross-school IDOR.
            return Response(
                {"detail": "Unable to determine institution for admission number check."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if exists:
            return Response({"detail": "This admission number is already in use."}, status=400)
        student = Student.objects.create(
            admission_number=admission_number,
            primary_campus=application.campus,
            first_name=application.first_name,
            middle_name=application.middle_name,
            last_name=application.last_name,
            date_of_birth=application.date_of_birth,
            gender=application.gender,
            guardian=application.guardian,
            phone=application.phone,
            address=application.address,
            status="active",
            admission_date=date.today(),
        )
        StudentGuardian.objects.create(
            student=student,
            guardian=application.guardian,
            relationship=application.guardian.relationship,
            is_primary=True,
            is_emergency_contact=True,
        )
        enrollment = Enrollment.objects.create(
            student=student,
            academic_year=application.academic_year,
            campus=application.campus,
            class_obj=application.class_obj,
            section=application.section,
            status="active",
        )
        from django.utils import timezone
        application.status = "accepted"
        application.student = student
        application.reviewed_by = request.user
        application.reviewed_at = timezone.now()
        application.save(update_fields=["status", "student", "reviewed_by", "reviewed_at", "updated_at"])
        return Response({"student": StudentSerializer(student, context={"request": request}).data, "enrollment_id": enrollment.id}, status=201)


class StudentGuardianListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = StudentGuardianSerializer

    def get_queryset(self):
        queryset = StudentGuardian.objects.select_related("student", "guardian")
        queryset = queryset.filter(
            student__enrollments__academic_year__school=self.request.institution
        )
        queryset = queryset.filter(
            student__enrollments__campus_id__in=campus_access(self.request)["allowed_ids"]
            or [-1]
        ) if not campus_access(self.request)["global"] else queryset
        student = self.request.query_params.get("student")
        if student:
            queryset = queryset.filter(student_id=student)
        return queryset

    def perform_create(self, serializer):
        student = serializer.validated_data["student"]
        if not Student.objects.filter(
            pk=student.pk,
            enrollments__academic_year__school=self.request.institution,
        ).exists():
            raise PermissionDenied("Student is outside the active institution.")
        assert_campus_allowed(
            self.request.user,
            student.enrollments.filter(status="active").values_list("campus_id", flat=True).first(),
        )
        guardian = serializer.validated_data.get("guardian")
        if guardian is not None and guardian.institution_id != self.request.institution.id:
            raise PermissionDenied("Guardian is outside the active institution.")
        serializer.save()


class StudentLifecycleListView(generics.ListAPIView):
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = StudentLifecycleEventSerializer

    def get_queryset(self):
        return StudentLifecycleEvent.objects.select_related(
            "student", "from_campus", "to_campus"
        ).filter(student__enrollments__academic_year__school=self.request.institution)


class StudentLifecycleActionView(APIView):
    permission_classes = [IsAdminRole]

    @transaction.atomic
    def post(self, request, pk):
        student = get_object_or_404(
            Student.objects.prefetch_related("enrollments").filter(
                enrollments__academic_year__school=request.institution,
            ),
            pk=pk,
        )
        active = student.enrollments.filter(status="active").select_related("campus").first()
        event_type = request.data.get("event_type")
        if event_type not in dict(StudentLifecycleEvent.EVENT_CHOICES):
            return Response({"detail": "Invalid lifecycle event."}, status=400)
        effective_date = request.data.get("effective_date")
        try:
            effective_date = date.fromisoformat(effective_date) if effective_date else date.today()
        except ValueError:
            return Response({"detail": "effective_date must be YYYY-MM-DD."}, status=400)
        if active:
            assert_campus_allowed(request.user, active.campus_id)
        if event_type in ("withdrawn", "graduated", "inactive"):
            if active:
                active.status = "withdrawn" if event_type == "withdrawn" else "completed"
                active.save(update_fields=["status", "updated_at"])
            student.status = event_type
            student.save(update_fields=["status", "updated_at"])
            event = StudentLifecycleEvent.objects.create(
                student=student,
                event_type=event_type,
                effective_date=effective_date,
                reason=request.data.get("reason", ""),
                from_campus=active.campus if active else None,
                from_enrollment=active,
                recorded_by=request.user,
            )
            return Response(StudentLifecycleEventSerializer(event).data, status=201)
        if event_type == "activated":
            student.status = "active"
            student.save(update_fields=["status", "updated_at"])
            event = StudentLifecycleEvent.objects.create(
                student=student, event_type=event_type, effective_date=effective_date,
                reason=request.data.get("reason", ""), recorded_by=request.user,
            )
            return Response(StudentLifecycleEventSerializer(event).data, status=201)
        required = ["to_academic_year", "to_campus", "to_class_obj", "to_section"]
        missing = [field for field in required if not request.data.get(field)]
        if missing or active is None:
            return Response({"detail": "Transfer requires an active enrollment and destination fields.", "missing": missing}, status=400)
        assert_campus_allowed(request.user, request.data["to_campus"])
        target = Enrollment(
            student=student,
            academic_year_id=request.data["to_academic_year"],
            campus_id=request.data["to_campus"],
            class_obj_id=request.data["to_class_obj"],
            section_id=request.data["to_section"],
            status="active",
        )
        active.status = "completed"
        active.save(update_fields=["status", "updated_at"])
        target.save()
        student.primary_campus_id = target.campus_id
        student.save(update_fields=["primary_campus", "updated_at"])
        event = StudentLifecycleEvent.objects.create(
            student=student, event_type="transferred", effective_date=effective_date,
            reason=request.data.get("reason", ""), from_campus=active.campus,
            to_campus=target.campus, from_enrollment=active, to_enrollment=target,
            recorded_by=request.user,
        )
        return Response(StudentLifecycleEventSerializer(event).data, status=201)


class StudentLeaveRequestListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAcademicMemberRole]
    serializer_class = StudentLeaveRequestSerializer

    def get_queryset(self):
        queryset = StudentLeaveRequest.objects.select_related(
            "student", "requested_by", "reviewed_by"
        ).filter(student__enrollments__academic_year__school=self.request.institution)
        user = self.request.user
        if is_parent(user):
            queryset = queryset.filter(student_id__in=parent_student_ids(user))
        elif is_student(user):
            queryset = queryset.filter(student=get_student_profile(user))
        elif not is_manager(user):
            return queryset.none()
        return queryset.distinct()

    def perform_create(self, serializer):
        user = self.request.user
        student = serializer.validated_data["student"]
        allowed = is_manager(user) or (
            is_parent(user) and student.pk in parent_student_ids(user)
        ) or (
            is_student(user) and get_student_profile(user) == student
        )
        if not allowed:
            raise PermissionDenied("You can only request leave for your own student record.")
        serializer.save(requested_by=user)


class StudentLeaveRequestActionView(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request, pk):
        leave = get_object_or_404(
            StudentLeaveRequest.objects.filter(
                student__enrollments__academic_year__school=request.institution,
            ),
            pk=pk,
        )
        action = request.data.get("action")
        if action not in ("approve", "reject", "cancel"):
            return Response({"detail": "Invalid leave action."}, status=400)
        from django.utils import timezone
        leave.status = {"approve": "approved", "reject": "rejected", "cancel": "cancelled"}[action]
        leave.reviewed_by = request.user
        leave.reviewed_at = timezone.now()
        leave.review_notes = request.data.get("review_notes", "")
        leave.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_notes", "updated_at"])
        return Response(StudentLeaveRequestSerializer(leave).data)


class PromotionView(APIView):
    """
    Batch promotion / demotion / transfer for a set of students.

    Uses a single database transaction: if any student fails validation the
    entire operation rolls back so that no records are partially created.
    """
    permission_classes = [IsAdminRole]

    def post(self, request):
        serializer = BatchPromotionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        from_year = _get_valid_academic_year(request, data["from_academic_year"])

        # Campus-level authorization for the source year's campus.
        target_campus = data.get("to_campus")
        if target_campus:
            assert_campus_allowed(request.user, target_campus)
        else:
            _assert_source_campus(request, data["student_ids"], from_year.pk)

        result = bulk_promote(
            data["student_ids"],
            from_year.pk,
            user=request.user,
            to_academic_year_id=data.get("to_academic_year"),
            to_class_id=data.get("to_class"),
            to_section_id=data.get("to_section"),
            to_campus_id=target_campus,
            reason=data.get("reason", ""),
            effective_date=data.get("effective_date"),
        )
        return Response(BatchResultSerializer(result).data, status=status.HTTP_201_CREATED)


class SinglePromotionView(APIView):
    """Promote / demote / transfer a single student and keep full history."""
    permission_classes = [IsAdminRole]

    def post(self, request, pk):
        serializer = SinglePromotionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        from_year = _get_valid_academic_year(request, data["from_academic_year"])
        target_campus = data.get("to_campus")
        if target_campus:
            assert_campus_allowed(request.user, target_campus)
        else:
            _assert_source_campus(request, [pk], from_year.pk)

        try:
            record = promote_student(
                pk,
                from_year.pk,
                user=request.user,
                to_academic_year_id=data.get("to_academic_year"),
                to_class_id=data.get("to_class"),
                to_section_id=data.get("to_section"),
                to_campus_id=target_campus,
                reason=data.get("reason", ""),
                effective_date=data.get("effective_date"),
            )
        except ValidationError as exc:
            return Response(
                {"detail": _flatten_validation_errors(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            ProgressionRecordSerializer(record, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class ProgressionHistoryView(NoPaginationMixin, generics.ListAPIView):
    """List a student's academic progression / transfer history."""
    serializer_class = ProgressionRecordSerializer
    permission_classes = [IsAdminRole]

    def get_queryset(self):
        queryset = (
            ProgressionRecord.objects
            .filter(student__institution=self.request.institution)
            .select_related(
                "student",
                "from_academic_year", "to_academic_year",
                "from_class", "to_class",
                "from_section", "to_section",
                "from_campus", "to_campus",
                "performed_by",
            )
            .order_by("-effective_date", "-created_at")
        )

        student = self.request.query_params.get("student")
        if student:
            queryset = queryset.filter(student_id=student)

        action = self.request.query_params.get("action")
        if action:
            queryset = queryset.filter(action=action)

        return queryset


def _get_valid_academic_year(request, year_id):
    try:
        return AcademicYear.objects.get(pk=year_id, school=request.institution)
    except AcademicYear.DoesNotExist:
        raise NotFound("Academic year not found for the active institution.")


def _assert_source_campus(request, student_ids, from_year_id):
    """
    Ensure the requesting user is allowed to operate on the source campuses
    for all students being progressed.
    """
    campus_ids = list(
        Enrollment.objects.filter(
            student_id__in=student_ids,
            academic_year_id=from_year_id,
            status="active",
        ).values_list("campus_id", flat=True)
    )
    for campus_id in set(campus_ids):
        assert_campus_allowed(request.user, campus_id)


def _flatten_validation_errors(exc):
    if hasattr(exc, "message_dict"):
        parts = []
        for field, value in exc.message_dict.items():
            if isinstance(value, (list, tuple)):
                parts.extend(str(v) for v in value)
            else:
                parts.append(str(value))
        return "; ".join(parts)
    return str(exc)

STUDENT_QUERYSET = (
    Student.objects
    .select_related("guardian", "user", "primary_campus")
    .prefetch_related(
        "enrollments__academic_year",
        "enrollments__campus",
        "enrollments__class_obj",
        "enrollments__section",
        "documents",
        "guardian_links__guardian",
    )
)


class StudentListCreateView(generics.ListCreateAPIView):
    serializer_class = StudentSerializer
    permission_classes = [IsAdminOrReadOnly]

    def perform_create(self, serializer):
        institution = getattr(self.request, "institution", None)

        if institution is None:
            raise RestValidationError(
                {"institution": "Select a school before adding a student."}
            )

        primary_campus = serializer.validated_data.get("primary_campus")

        if primary_campus is not None and primary_campus.school_id != institution.id:
            raise RestValidationError(
                {
                    "primary_campus": (
                        "The selected campus does not belong to the "
                        "active school."
                    )
                }
            )

        serializer.save(institution=institution)

    def get_queryset(self):
        queryset = STUDENT_QUERYSET.order_by("first_name", "last_name")
        institution = require_active_school(self.request)

        # Active-school failure policy: the student selector (used by the
        # Hostel Allocation form) must fail closed. With no valid active
        # school the queryset is empty — a bare ``school=None`` filter would
        # still match students that have no enrollment rows (NULL join). A
        # stale/unauthorized or inactive school context raises a 403 instead
        # of silently falling back.
        if institution is None:
            return queryset.none()

        # Institution-tagged students are always visible; legacy records
        # without a school tag are resolved through their enrollments.
        # Never expose a student of another active school.
        queryset = queryset.filter(
            Q(institution=institution)
            | Q(enrollments__academic_year__school=institution)
        )

        user = self.request.user

        if not is_manager(user):
            if is_parent(user):
                queryset = queryset.filter(parent_scope_filter(user))
            else:
                queryset = queryset.filter(teacher_scope_filter(user))

        search = self.request.query_params.get("search")

        if search:
            queryset = queryset.filter(
                Q(admission_number__icontains=search)
                | Q(first_name__icontains=search)
                | Q(middle_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(phone__icontains=search)
            )

        status = self.request.query_params.get("status")

        if status:
            queryset = queryset.filter(status=status)

        gender = self.request.query_params.get("gender")

        if gender:
            queryset = queryset.filter(gender=gender)

        access = campus_access(self.request)

        if not access["global"]:
            allowed = access["allowed_ids"]
            queryset = queryset.filter(
                enrollments__campus_id__in=allowed or [-1],
                enrollments__status="active",
            )
        elif access["requested"]:
            queryset = queryset.filter(
                enrollments__campus_id=access["requested"],
                enrollments__status="active",
            )

        section = self.request.query_params.get("section")

        if section:
            queryset = queryset.filter(
                enrollments__section_id=section,
                enrollments__status="active",
            )

        class_obj = self.request.query_params.get("class_obj")

        if class_obj:
            queryset = queryset.filter(
                enrollments__class_obj_id=class_obj,
                enrollments__status="active",
            )

        return queryset


class StudentDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = StudentSerializer

    def get_queryset(self):
        queryset = STUDENT_QUERYSET
        institution = require_active_school(self.request)

        # Active-school failure policy: fail closed when no valid active
        # school — never expose a cross-school student via a NULL join; a
        # stale/unauthorized or inactive school context raises a 403 instead
        # of silently falling back.
        if institution is None:
            return queryset.none()

        queryset = queryset.filter(
            enrollments__academic_year__school=institution
        )

        user = self.request.user

        if not is_manager(user):
            if is_parent(user):
                queryset = queryset.filter(parent_scope_filter(user))
            else:
                queryset = queryset.filter(teacher_scope_filter(user))

        access = campus_access(self.request)

        if not access["global"]:
            allowed = access["allowed_ids"]
            queryset = queryset.filter(
                enrollments__campus_id__in=allowed or [-1],
                enrollments__status="active",
            )
        elif access["requested"]:
            queryset = queryset.filter(
                enrollments__campus_id=access["requested"],
                enrollments__status="active",
            )

        return queryset


class StudentMyView(generics.RetrieveAPIView):
    """The student's own profile."""

    permission_classes = [IsAdminOrReadOnly]
    serializer_class = StudentSerializer

    def get_queryset(self):
        return STUDENT_QUERYSET

    def get_object(self):
        profile = get_student_profile(self.request.user)

        if profile is None:
            raise NotFound(
                "No student profile is linked to this account."
            )

        return profile


class GuardianListCreateView(generics.ListCreateAPIView):
    """Guardian registry; admins can create a parent login."""

    permission_classes = [IsAdminRole]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return GuardianCreateSerializer

        return GuardianSerializer

    def get_queryset(self):
        return Guardian.objects.filter(
            students__enrollments__academic_year__school=self.request.institution
        ).select_related("user").distinct().order_by("name")


class GuardianDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminRole]
    serializer_class = GuardianSerializer

    def get_queryset(self):
        return Guardian.objects.filter(
            students__enrollments__academic_year__school=self.request.institution
        ).select_related("user").distinct()


class GuardianMyView(generics.RetrieveAPIView):
    """The logged-in parent's own guardian profile."""

    permission_classes = [IsAcademicMemberRole]
    serializer_class = GuardianSerializer

    def get_queryset(self):
        return Guardian.objects.select_related("user")

    def get_object(self):
        profile = get_guardian_profile(self.request.user)

        if profile is None:
            raise NotFound(
                "No guardian profile is linked to this account."
            )

        return profile


class StudentDocumentListCreateView(generics.ListCreateAPIView):
    serializer_class = StudentDocumentSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        queryset = StudentDocument.objects.select_related(
            "student",
            "uploaded_by",
        )

        student = self.request.query_params.get("student")

        if student:
            queryset = queryset.filter(student_id=student)

        document_type = self.request.query_params.get("document_type")

        if document_type:
            queryset = queryset.filter(document_type=document_type)

        return apply_campus_scope(
            queryset,
            self.request,
            "student__enrollments__campus_id",
            institution_field="institution_id",
        )

    def perform_create(self, serializer):
        institution = getattr(self.request, "institution", None)
        student = serializer.validated_data.get("student")
        if student:
            # Verify student is within user's allowed scope
            allowed_queryset = apply_campus_scope(
                Student.objects.all(),
                self.request,
                "enrollments__campus_id",
                institution_field="institution_id",
            )
            if not allowed_queryset.filter(pk=student.pk).exists():
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied("Student is outside your allowed scope.")
        serializer.save(uploaded_by=self.request.user, institution=institution)


class StudentDocumentDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = StudentDocumentSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        queryset = StudentDocument.objects.select_related(
            "student",
            "uploaded_by",
        )

        return apply_campus_scope(
            queryset,
            self.request,
            "student__enrollments__campus_id",
            institution_field="institution_id",
        )

    def perform_update(self, serializer):
        institution = getattr(self.request, "institution", None)
        serializer.save(uploaded_by=self.request.user, institution=institution)


class EnrollmentListCreateView(generics.ListCreateAPIView):
    """Assign students to a grade (class/section) for a year."""

    serializer_class = EnrollmentCreateSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        queryset = (
            Enrollment.objects
            .select_related(
                "student",
                "academic_year",
                "campus",
                "class_obj",
                "section",
            )
            .order_by("-enrollment_date", "student__first_name")
        )
        queryset = queryset.filter(
            academic_year__school=self.request.institution
        )
        queryset = campus_scoped(queryset, self.request)

        student = self.request.query_params.get("student")

        if student:
            queryset = queryset.filter(student_id=student)

        class_obj = self.request.query_params.get("class")

        if class_obj:
            queryset = queryset.filter(class_obj_id=class_obj)

        section = self.request.query_params.get("section")

        if section:
            queryset = queryset.filter(section_id=section)

        academic_year = self.request.query_params.get("year")

        if academic_year:
            queryset = queryset.filter(
                academic_year_id=academic_year
            )

        status = self.request.query_params.get("status")

        if status:
            queryset = queryset.filter(status=status)

        return queryset

    def perform_create(self, serializer):
        student = serializer.validated_data.get("student")
        institution = getattr(self.request, "institution", None)

        if student is not None and student.institution_id != (institution.id if institution else None):
            raise PermissionDenied(
                "Student does not belong to the active institution."
            )
        serializer.save()

    def perform_update(self, serializer):
        student = serializer.validated_data.get("student")
        institution = getattr(self.request, "institution", None)

        if student is not None and student.institution_id != (institution.id if institution else None):
            raise PermissionDenied(
                "Student does not belong to the active institution."
            )
        serializer.save()


class EnrollmentDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = EnrollmentCreateSerializer

    def get_queryset(self):
        return campus_scoped((
            Enrollment.objects
            .select_related(
                "student",
                "academic_year",
                "campus",
                "class_obj",
                "section",
            )
        ).filter(academic_year__school=self.request.institution), self.request)

    def perform_update(self, serializer):
        student = serializer.validated_data.get("student")
        institution = getattr(self.request, "institution", None)

        if student is not None and student.institution_id != (institution.id if institution else None):
            raise PermissionDenied(
                "Student does not belong to the active institution."
            )
        serializer.save()


# =============================================================================
# INQUIRY VIEWS
# =============================================================================

class InquiryListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminOrReadOnly]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return InquiryCreateSerializer
        return InquirySerializer

    def get_queryset(self):
        queryset = Inquiry.objects.select_related(
            "campus", "academic_year", "class_obj", "assigned_to", "converted_by"
        ).filter(
            institution=self.request.institution
        )

        status = self.request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)

        campus = self.request.query_params.get("campus")
        if campus:
            assert_campus_allowed(self.request.user, campus)
            queryset = queryset.filter(campus_id=campus)

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(phone__icontains=search)
                | Q(email__icontains=search)
                | Q(inquiry_number__icontains=search)
            )

        return queryset

    def perform_create(self, serializer):
        institution = require_active_school(self.request)
        if institution is None:
            raise RestValidationError({"institution": "Select a school before logging an inquiry."})

        campus = serializer.validated_data.get("campus")
        academic_year = serializer.validated_data.get("academic_year")
        class_obj = serializer.validated_data.get("class_obj")
        if campus:
            assert_campus_allowed(self.request.user, campus.pk, request=self.request)
        if academic_year and academic_year.school_id != institution.pk:
            raise RestValidationError({"academic_year": "Choose a year from the active school."})
        if class_obj and class_obj.unit.campus.school_id != institution.pk:
            raise RestValidationError({"class_obj": "Choose a class from the active school."})
        if campus and class_obj and class_obj.unit.campus_id != campus.pk:
            raise RestValidationError({"class_obj": "Choose a class from the selected campus."})

        serializer.save(
            institution=institution,
            inquiry_number=f"INQ-{uuid4().hex.upper()}",
        )


class InquiryDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = InquirySerializer

    def get_queryset(self):
        return Inquiry.objects.filter(institution=self.request.institution)


class InquiryConvertView(APIView):
    """Convert an inquiry to an admission application."""

    permission_classes = [IsAdminRole]

    def post(self, request, pk):
        inquiry = get_object_or_404(
            Inquiry.objects.filter(institution=request.institution),
            pk=pk,
        )

        if inquiry.status == "converted":
            return Response({"detail": "Inquiry already converted."}, status=400)

        application_data = request.data.get("application_data", {})

        try:
            application = inquiry.convert_to_application(
                request.user,
                **application_data,
            )
        except ValidationError as e:
            return Response({"detail": str(e)}, status=400)

        return Response(
            {"application": AdmissionApplicationSerializer(application, context={"request": request}).data},
            status=201,
        )


# =============================================================================
# ACADEMIC HISTORY VIEWS
# =============================================================================

class AcademicHistoryListView(generics.ListAPIView):
    serializer_class = AcademicHistorySerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        queryset = AcademicHistory.objects.select_related(
            "student", "academic_year", "campus", "class_obj", "section"
        ).filter(student__institution=self.request.institution)

        student = self.request.query_params.get("student")
        if student:
            queryset = queryset.filter(student_id=student)

        academic_year = self.request.query_params.get("academic_year")
        if academic_year:
            queryset = queryset.filter(academic_year_id=academic_year)

        campus = self.request.query_params.get("campus")
        if campus:
            assert_campus_allowed(self.request.user, campus)
            queryset = queryset.filter(campus_id=campus)

        final_status = self.request.query_params.get("final_status")
        if final_status:
            queryset = queryset.filter(final_status=final_status)

        return queryset


class AcademicHistoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AcademicHistorySerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        return AcademicHistory.objects.filter(student__institution=self.request.institution)


# =============================================================================
# TRANSFER CERTIFICATE VIEWS
# =============================================================================

class TransferCertificateListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminOrReadOnly]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return TransferCertificateSerializer
        return TransferCertificateSerializer

    def get_queryset(self):
        queryset = TransferCertificate.objects.select_related(
            "student", "campus", "academic_year", "class_obj", "section", "issued_by"
        ).filter(institution=self.request.institution)

        campus = self.request.query_params.get("campus")
        if campus:
            assert_campus_allowed(self.request.user, campus)
            queryset = queryset.filter(campus_id=campus)

        student = self.request.query_params.get("student")
        if student:
            queryset = queryset.filter(student_id=student)

        status = self.request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)

        return queryset

    def perform_create(self, serializer):
        serializer.save(institution=self.request.institution)


class TransferCertificateDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TransferCertificateSerializer
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        return TransferCertificate.objects.filter(institution=self.request.institution)


class TransferCertificateIssueView(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request, pk):
        certificate = get_object_or_404(
            TransferCertificate.objects.filter(institution=request.institution),
            pk=pk,
        )

        if certificate.status == "issued":
            return Response({"detail": "Certificate already issued."}, status=400)

        if certificate.status == "cancelled":
            return Response({"detail": "Cannot issue a cancelled certificate."}, status=400)

        certificate.issue(request.user)
        return Response(TransferCertificateSerializer(certificate, context={"request": request}).data)


class TransferCertificateCancelView(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request, pk):
        certificate = get_object_or_404(
            TransferCertificate.objects.filter(institution=request.institution),
            pk=pk,
        )

        if certificate.status == "draft":
            return Response({"detail": "Cannot cancel a draft certificate. Delete it instead."}, status=400)

        certificate.cancel(request.user)
        return Response(TransferCertificateSerializer(certificate, context={"request": request}).data)


class TransferCertificateVerifyView(APIView):
    """Public endpoint to verify a transfer certificate by verification code.

    Returns a deliberately minimal payload confirming that the certificate
    exists and is currently issued. Sensitive student PII (date of birth,
    admission number, reason, conduct, issuer) is intentionally NOT exposed
    here - use the authenticated detail endpoints for those fields.

    Unknown, cancelled or draft certificates return 404. Because the endpoint
    is public, requests are throttled per client via the
    ``transfer_certificate_verify`` throttle scope.
    """

    permission_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "transfer_certificate_verify"

    def get(self, request, code):
        certificate = get_object_or_404(
            TransferCertificate.objects.filter(
                institution__isnull=False,
                verification_code=code.upper(),
                status="issued",
            )
        )
        data = {
            "certificate_number": certificate.certificate_number,
            "student_name": certificate.full_name,
            "campus": certificate.campus.name,
            "issued_at": certificate.issued_at,
            "status": certificate.status,
        }
        return Response(data)


# =============================================================================
# STUDENT 360 VIEW
# =============================================================================

class Student360View(APIView):
    """
    Comprehensive Student 360 view that aggregates data from multiple modules.
    
    Provides a complete view of a student by aggregating data from:
    - Personal details (Student model)
    - Parents/Guardians (Guardian, StudentGuardian)
    - Academic history (AcademicHistory)
    - Current enrollment (Enrollment)
    - Attendance (Attendance)
    - Exams & Results (StudentResult, PracticalResult)
    - Fees & Finance (Invoice, Payment)
    - Library (BookIssue)
    - Transport (TransportAssignment)
    - Discipline (Incident)
    - Documents (StudentDocument)
    - Certificates (TransferCertificate)
    
    Access Control:
    - Admin/Manager roles: Can view any student in their institution
    - Teachers: Can view students in their classes
    - Parents: Can view their own children
    - Students: Can view their own profile
    """
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request, student_id):
        from apps.students.models import Student
        from apps.accounts.access import assert_campus_allowed
        from apps.accounts.scopes import (
            get_student_profile, get_guardian_profile,
            is_manager, is_parent, is_student,
            parent_student_ids, is_parent_of,
        )
        from apps.students.serializers import Student360Serializer
        
        # Get the current user's institution
        institution = getattr(request, 'institution', None)
        
        # Build student queryset with institution scoping
        student_qs = Student.objects.select_related(
            "guardian", "primary_campus", "user", "membership", "institution"
        ).prefetch_related(
            "enrollments__campus",
            "enrollments__class_obj",
            "enrollments__section",
            "enrollments__academic_year",
            "guardian_links__guardian",
            "documents",
        )
        
        # Always scope to institution; if not set, return empty queryset
        # to prevent cross-school data access without institution context.
        if institution is not None:
            student_qs = student_qs.filter(institution=institution)
        else:
            student_qs = student_qs.none()
        
        # Get the student
        student = get_object_or_404(
            student_qs,
            pk=student_id,
        )
        
        # Check authorization
        user = request.user
        user_id = user.id if user and user.is_authenticated else None
        
        # Allow if user is the student themselves (by user ID)
        if user_id == student.user_id:
            pass  # Allow
        # Allow if user is a parent of the student
        elif is_parent(user) and is_parent_of(user, student):
            pass  # Allow
        # Allow if user is a student viewing their own profile
        elif is_student(user) and user_id == student.user_id:
            pass  # Allow
        # Allow if user is a teacher of the student
        elif hasattr(user, 'teacher_profile'):
            teacher = user.teacher_profile
            active_enrollment = student.enrollments.filter(status="active").first()
            if active_enrollment and teacher_can_access_student(teacher, active_enrollment):
                pass  # Allow
        # Otherwise require admin/manager role within the institution
        elif is_manager(user):
            pass  # Allow - managers can view any student
        # Deny with a clear message
        else:
            raise PermissionDenied("You do not have permission to view this student's profile.")
        
        # Campus access check (only if institution and enrollment are available)
        active_enrollment = student.enrollments.filter(status="active").first()
        if active_enrollment and institution:
            try:
                assert_campus_allowed(user, active_enrollment.campus_id)
            except PermissionDenied:
                raise PermissionDenied("You do not have access to this campus.")
        
        # Serialize and return
        serializer = Student360Serializer(student, context={"request": request})
        return Response(serializer.data)


def teacher_can_access_student(teacher, enrollment):
    """Check if a teacher can access a student's data."""
    from apps.teachers.models import TeacherAssignment
    
    if not enrollment:
        return False
    
    # Check if teacher is class teacher for this student's section
    return TeacherAssignment.objects.filter(
        teacher=teacher,
        class_obj=enrollment.class_obj,
        section=enrollment.section,
        role="class_teacher",
        status="active",
    ).exists()


# =============================================================================
# CAMPUS TRANSFER VIEWS
# =============================================================================

class CampusTransferListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminRole]
    
    def get_serializer_class(self):
        if self.request.method == "POST":
            return CampusTransferCreateSerializer
        return CampusTransferSerializer
    
    def get_queryset(self):
        queryset = CampusTransfer.objects.select_related(
            "student", "from_campus", "to_campus", "academic_year",
            "requested_by", "reviewed_by", "completed_by", "reversed_by"
        ).filter(student__institution=self.request.institution)
        
        status = self.request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)
        
        campus = self.request.query_params.get("campus")
        if campus:
            assert_campus_allowed(self.request.user, campus)
            queryset = queryset.filter(Q(from_campus_id=campus) | Q(to_campus_id=campus))
        
        student = self.request.query_params.get("student")
        if student:
            queryset = queryset.filter(student_id=student)
        
        return queryset


class CampusTransferDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CampusTransferSerializer
    permission_classes = [IsAdminRole]
    
    def get_queryset(self):
        return CampusTransfer.objects.filter(
            student__institution=self.request.institution
        )
    
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        
        if instance.status == "completed":
            return Response(
                {"detail": "Cannot modify a completed transfer."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        return super().update(request, *args, **partial)


class CampusTransferApproveView(APIView):
    permission_classes = [IsAdminRole]
    
    def post(self, request, pk):
        transfer = get_object_or_404(
            CampusTransfer.objects.filter(student__institution=request.institution),
            pk=pk,
        )
        
        if transfer.status != "requested":
            return Response(
                {"detail": "Only requested transfers can be approved."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        notes = request.data.get("review_notes", "")
        transfer.approve(request.user, notes)
        
        return Response(CampusTransferSerializer(transfer, context={"request": request}).data)


class CampusTransferRejectView(APIView):
    permission_classes = [IsAdminRole]
    
    def post(self, request, pk):
        transfer = get_object_or_404(
            CampusTransfer.objects.filter(student__institution=request.institution),
            pk=pk,
        )
        
        if transfer.status != "requested":
            return Response(
                {"detail": "Only requested transfers can be rejected."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        notes = request.data.get("review_notes", "")
        transfer.reject(request.user, notes)
        
        return Response(CampusTransferSerializer(transfer, context={"request": request}).data)


class CampusTransferCompleteView(APIView):
    permission_classes = [IsAdminRole]
    
    def post(self, request, pk):
        transfer = get_object_or_404(
            CampusTransfer.objects.filter(student__institution=request.institution),
            pk=pk,
        )
        
        if transfer.status != "approved":
            return Response(
                {"detail": "Only approved transfers can be completed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        transfer.complete(request.user)
        
        return Response(CampusTransferSerializer(transfer, context={"request": request}).data)


class CampusTransferCancelView(APIView):
    permission_classes = [IsAdminRole]
    
    def post(self, request, pk):
        transfer = get_object_or_404(
            CampusTransfer.objects.filter(student__institution=request.institution),
            pk=pk,
        )
        
        if transfer.status in ["completed", "cancelled"]:
            return Response(
                {"detail": f"Cannot cancel a {transfer.status} transfer."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        transfer.cancel(request.user)
        
        return Response(CampusTransferSerializer(transfer, context={"request": request}).data)


class CampusTransferReverseView(APIView):
    permission_classes = [IsAdminRole]
    
    def post(self, request, pk):
        transfer = get_object_or_404(
            CampusTransfer.objects.filter(student__institution=request.institution),
            pk=pk,
        )
        
        reason = request.data.get("reason", "")
        transfer.reverse(request.user, reason)
        
        return Response(CampusTransferSerializer(transfer, context={"request": request}).data)


# =============================================================================
# SECTION TRANSFER VIEWS
# =============================================================================

class SectionTransferListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminRole]
    
    def get_serializer_class(self):
        if self.request.method == "POST":
            return SectionTransferCreateSerializer
        return SectionTransferSerializer
    
    def get_queryset(self):
        queryset = SectionTransfer.objects.select_related(
            "student", "from_section", "to_section", "academic_year",
            "requested_by", "reviewed_by", "completed_by"
        ).filter(student__institution=self.request.institution)
        
        status = self.request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)
        
        campus = self.request.query_params.get("campus")
        if campus:
            assert_campus_allowed(self.request.user, campus)
            queryset = queryset.filter(from_section__class_obj__unit__campus_id=campus)
        
        return queryset


class SectionTransferDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = SectionTransferSerializer
    permission_classes = [IsAdminRole]
    
    def get_queryset(self):
        return SectionTransfer.objects.filter(
            student__institution=self.request.institution
        )


class SectionTransferApproveView(APIView):
    permission_classes = [IsAdminRole]
    
    def post(self, request, pk):
        transfer = get_object_or_404(
            SectionTransfer.objects.filter(student__institution=request.institution),
            pk=pk,
        )
        
        if transfer.status != "requested":
            return Response(
                {"detail": "Only requested transfers can be approved."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        notes = request.data.get("review_notes", "")
        transfer.approve(request.user, notes)
        
        return Response(SectionTransferSerializer(transfer, context={"request": request}).data)


class SectionTransferRejectView(APIView):
    permission_classes = [IsAdminRole]
    
    def post(self, request, pk):
        transfer = get_object_or_404(
            SectionTransfer.objects.filter(student__institution=request.institution),
            pk=pk,
        )
        
        if transfer.status != "requested":
            return Response(
                {"detail": "Only requested transfers can be rejected."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        notes = request.data.get("review_notes", "")
        transfer.reject(request.user, notes)
        
        return Response(SectionTransferSerializer(transfer, context={"request": request}).data)


class SectionTransferCompleteView(APIView):
    permission_classes = [IsAdminRole]
    
    def post(self, request, pk):
        transfer = get_object_or_404(
            SectionTransfer.objects.filter(student__institution=request.institution),
            pk=pk,
        )
        
        if transfer.status != "approved":
            return Response(
                {"detail": "Only approved transfers can be completed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        transfer.complete(request.user)
        
        return Response(SectionTransferSerializer(transfer, context={"request": request}).data)


class SectionTransferCancelView(APIView):
    permission_classes = [IsAdminRole]
    
    def post(self, request, pk):
        transfer = get_object_or_404(
            SectionTransfer.objects.filter(student__institution=request.institution),
            pk=pk,
        )
        
        if transfer.status in ["completed", "cancelled"]:
            return Response(
                {"detail": f"Cannot cancel a {transfer.status} transfer."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        transfer.cancel(request.user)
        
        return Response(SectionTransferSerializer(transfer, context={"request": request}).data)


# =============================================================================
# ALUMNI VIEWS
# =============================================================================

class StudentGraduateView(APIView):
    """Graduate a student and create alumni record."""
    permission_classes = [IsAdminRole]
    
    @transaction.atomic
    def post(self, request, pk):
        student = get_object_or_404(
            Student.objects.filter(
                institution=request.institution,
                enrollments__academic_year__school=request.institution,
            ),
            pk=pk,
        )
        
        graduation_date = request.data.get("graduation_date")
        reason = request.data.get("reason", "Graduated")
        final_grade = request.data.get("final_grade", "")
        final_percentage = request.data.get("final_percentage")
        final_percentage = Decimal(final_percentage) if final_percentage else None
        
        alumni = student.graduate(
            request.user,
            graduation_date=graduation_date,
            reason=reason,
            final_grade=final_grade,
            final_percentage=final_percentage,
        )
        
        return Response(
            {"student": StudentSerializer(student, context={"request": request}).data,
             "alumni": StudentAlumniSerializer(alumni, context={"request": request}).data},
            status=status.HTTP_201_CREATED,
        )


class StudentBatchGraduateView(APIView):
    """Graduate a batch of students (e.g. a whole graduating class).

    Accepts ``{"student_ids": [...], "graduation_date": "YYYY-MM-DD",
    "reason": "..."}``. Runs atomically on a single transaction and
    returns per-student success/failure details.
    """
    permission_classes = [IsAdminRole]

    @transaction.atomic
    def post(self, request):
        student_ids = request.data.get("student_ids") or []
        if not isinstance(student_ids, (list, tuple)) or not student_ids:
            return Response(
                {"detail": "student_ids is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        graduation_date = request.data.get("graduation_date")
        reason = request.data.get("reason", "Graduated")
        final_grade = request.data.get("final_grade", "")

        students = (
            Student.objects
            .filter(
                institution=request.institution,
                pk__in=student_ids,
                enrollments__academic_year__school=request.institution,
            )
            .distinct()
        )

        results = {"graduated": [], "failed": []}
        for student in students:
            try:
                alumni = student.graduate(
                    request.user,
                    graduation_date=graduation_date,
                    reason=reason,
                    final_grade=final_grade,
                )
                results["graduated"].append(
                    {
                        "student_id": student.pk,
                        "full_name": student.full_name,
                        "alumni_id": alumni.pk,
                    }
                )
            except ValidationError as exc:
                results["failed"].append(
                    {
                        "student_id": student.pk,
                        "full_name": student.full_name,
                        "error": _flatten_validation_errors(exc),
                    }
                )

        not_found = [
            sid for sid in student_ids
            if sid not in [s.pk for s in students]
        ]
        if not_found:
            results["failed"].append(
                {
                    "student_id": None,
                    "full_name": None,
                    "error": f"Student(s) not found or out of scope: {not_found}",
                }
            )

        if not results["graduated"]:
            return Response(
                results,
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(results, status=status.HTTP_201_CREATED)


class StudentWithdrawView(APIView):
    """Withdraw a student."""
    permission_classes = [IsAdminRole]
    
    def post(self, request, pk):
        student = get_object_or_404(
            Student.objects.filter(
                institution=request.institution,
                enrollments__academic_year__school=request.institution,
            ),
            pk=pk,
        )
        
        reason = request.data.get("reason", "")
        effective_date = request.data.get("effective_date")
        
        event = student.withdraw(request.user, reason, effective_date)
        
        return Response(StudentLifecycleEventSerializer(event).data, status=status.HTTP_201_CREATED)


class StudentActivateView(APIView):
    """Reactivate a withdrawn/inactive student."""
    permission_classes = [IsAdminRole]
    
    def post(self, request, pk):
        student = get_object_or_404(
            Student.objects.filter(
                institution=request.institution,
                enrollments__academic_year__school=request.institution,
            ),
            pk=pk,
        )
        
        if student.status not in ["withdrawn", "inactive"]:
            return Response(
                {"detail": "Student is not withdrawn or inactive."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        reason = request.data.get("reason", "Reactivated")
        effective_date = request.data.get("effective_date")
        
        event = student.activate(request.user, reason, effective_date)
        
        return Response(StudentLifecycleEventSerializer(event).data, status=status.HTTP_201_CREATED)


class StudentAlumniDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = StudentAlumniSerializer
    permission_classes = [IsAdminRole]
    
    def get_queryset(self):
        return StudentAlumni.objects.filter(
            student__institution=self.request.institution
        ).select_related("student", "final_campus", "final_class", "final_section", "final_academic_year")


class StudentTransferCreateView(APIView):
    """Create a student transfer request to another campus."""
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request, format=None):
        user = request.user
        to_campus_id = request.data.get("to_campus_id")
        reason = request.data.get("reason", "").strip()
        student_id = request.data.get("student_id")
        
        if not to_campus_id:
            return Response(
                {"detail": "to_campus_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        from apps.accounts.models import StudentTransfer, Role
        from apps.accounts.access import restrict_to_allowed_campuses

        user_roles = user.get_roles(user.primary_institution)
        is_super_admin = Role.SUPER_ADMIN in user_roles
        is_campus_admin = Role.CAMPUS_ADMIN in user_roles

        if not is_super_admin and not is_campus_admin:
            return Response(
                {"detail": "You do not have permission to transfer students."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            campus_filter = {"pk": to_campus_id}
            if not is_super_admin:
                campus_filter["school"] = user.primary_institution
            to_campus = Campus.objects.get(**campus_filter)
        except Campus.DoesNotExist:
            return Response(
                {"detail": "Invalid campus ID."},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        # Identify the student: use provided student_id, otherwise auto-detect
        from apps.students.models import Student, Enrollment
        
        student = None
        if student_id:
            # Super admins can access students across institutions
            student_filter = {"pk": student_id}
            if not is_super_admin:
                student_filter["institution"] = user.primary_institution
            try:
                student = Student.objects.get(**student_filter)
            except Student.DoesNotExist:
                return Response(
                    {"detail": "Student not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
        if student is None:
            # Auto-detect: use the first active enrollment from the user's primary institution
            # Super admins can auto-detect across institutions (but typically won't use auto-detect)
            enrollment_filter = {"status": "active"}
            if not is_super_admin:
                enrollment_filter["institution"] = user.primary_institution
            student = (
                Student.objects
                .filter(**enrollment_filter)
                .order_by("-enrollments__created_at")
                .select_related("primary_campus")
                .first()
            )
            if student is None:
                # Try to find by active enrollment
                enrollment_filter2 = {"status": "active"}
                if not is_super_admin:
                    enrollment_filter2["institution"] = user.primary_institution
                student = (
                    Enrollment.objects
                    .filter(**enrollment_filter2)
                    .values_list("student_id", flat=True)
                    .distinct()
                    .first()
                )
                if student is not None:
                    student = Student.objects.get(pk=student)
        
        if not student:
            return Response(
                {"detail": "No student found in request context."},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        if not is_super_admin and not is_campus_admin:
            return Response(
                {"detail": "You do not have permission to transfer students."},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        # For campus admins, restrict to their assigned campus.
        if not is_super_admin:
            allowed = restrict_to_allowed_campuses(
                Campus.objects.filter(school=user.primary_institution),
                user,
                "pk",
            )
            target_campus_ids = allowed.values_list("id", flat=True)
            if to_campus.id not in target_campus_ids:
                return Response(
                    {"detail": "Target campus is not within your assigned campus."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        
        # Create the transfer record.
        # Determine from_campus: use the student's primary_campus, or the campus
        # from their most recent active enrollment.
        from_campus = student.primary_campus
        if from_campus is None and student.enrollments.exists():
            from_campus = student.enrollments.first().campus
        
        # Ensure from_campus is set (required for audit trail)
        if from_campus is None:
            from_campus = to_campus

        transfer = StudentTransfer.objects.create(
            student=student,
            from_campus=from_campus,
            to_campus=to_campus,
            status="pending",
            reason=reason,
            approved_by=user,
        )
        
        # Record audit log.
        from apps.audit.models import record_audit
        
        record_audit(
            request=request,
            user=user,
            action="student_transfer_initiated",
            details={
                "student_id": student.pk,
                "student_name": str(student),
                "from_campus": str(student.primary_campus) if student and student.primary_campus else None,
                "to_campus": str(to_campus),
                "reason": reason,
            },
        )
        
        return Response(
            {
                "detail": "Transfer request created.",
                "transfer_id": transfer.pk,
                "status": transfer.status,
            },
            status=status.HTTP_201_CREATED,
        )

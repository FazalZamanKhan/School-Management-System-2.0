from datetime import date
from decimal import Decimal

from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.access import apply_campus_scope, assert_campus_allowed
from apps.accounts.permissions import IsAccountantRole, IsAdminOrReadOnly, IsAdminRole
from apps.accounts.scopes import is_manager
from apps.audit.models import record_audit
from apps.accounts.models import StaffProfile
from apps.teachers.models import Teacher

from .models import (
    Employee,
    EmployeeDocument,
    EmploymentContract,
    EmploymentEvent,
    PerformanceReview,
    WorkloadAssignment,
    Department,
    Designation,
    LeaveType,
    LeavePolicy,
    LeaveBalance,
    LeaveRequest,
    Allowance,
    Deduction,
    Bonus,
    Overtime,
    Loan,
    Advance,
    SalaryRevision,
    PayrollPeriod,
    ExitClearance,
    ClearanceItem,
    JobPosition,
    Candidate,
    Application,
    Interview,
)
from .serializers import (
    DepartmentSerializer,
    DesignationSerializer,
    EmployeeSerializer,
    EmployeeDetailSerializer,
    EmployeeDocumentSerializer,
    EmploymentContractSerializer,
    EmploymentEventSerializer,
    PerformanceReviewSerializer,
    WorkloadAssignmentSerializer,
    LeaveTypeSerializer,
    LeavePolicySerializer,
    LeaveBalanceSerializer,
    LeaveRequestSerializer,
    AllowanceSerializer,
    DeductionSerializer,
    BonusSerializer,
    OvertimeSerializer,
    LoanSerializer,
    AdvanceSerializer,
    SalaryRevisionSerializer,
    PayrollPeriodSerializer,
    ExitClearanceSerializer,
    ClearanceItemSerializer,
    JobPositionSerializer,
    CandidateSerializer,
    ApplicationSerializer,
    InterviewSerializer,
    ExitClearanceSerializer,
    ClearanceItemSerializer,
    JobPositionSerializer,
    CandidateSerializer,
    ApplicationSerializer,
    InterviewSerializer,
)


def employee_queryset(request):
    queryset = Employee.objects.select_related(
        "institution", "teacher", "staff_profile", "primary_campus", "department", "designation"
    ).filter(institution=request.institution)
    return apply_campus_scope(queryset, request, "primary_campus_id")


def owned_queryset(model, request):
    return model.objects.filter(employee__in=employee_queryset(request))


def available_employee_profiles(request, profile_type):
    institution = getattr(request, "institution", None)
    model = Teacher if profile_type == "teacher" else StaffProfile
    if institution is None:
        return model.objects.none()
    queryset = model.objects.filter(
        Q(institution=institution)
        | Q(institution__isnull=True, membership__institution=institution)
        | Q(institution__isnull=True, membership__isnull=True, primary_campus__school=institution)
    ).filter(employee_record__isnull=True)
    return apply_campus_scope(queryset, request, "primary_campus_id", institution_field=None)


# Original Employee Views (from original implementation)
class EmployeeProfileListView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        profile_type = request.query_params.get("profile_type", "staff")
        if profile_type not in ("staff", "teacher"):
            raise serializers.ValidationError({"profile_type": "Choose staff or teacher."})
        if getattr(request, "institution", None) is None:
            return Response([])
        queryset = available_employee_profiles(request, profile_type)
        search = request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(first_name__icontains=search)
                | Q(last_name__icontains=search)
                | Q(employee_number__icontains=search)
            )
        return Response([
            {"id": profile.pk, "full_name": profile.full_name,
             "employee_number": profile.employee_number, "primary_campus": profile.primary_campus_id}
            for profile in queryset.order_by("first_name", "last_name", "pk")[:100]
        ])


class EmployeeListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = EmployeeSerializer

    def get_queryset(self):
        queryset = employee_queryset(self.request)
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                employee_number__icontains=search
            ) | queryset.filter(
                teacher__first_name__icontains=search
            ) | queryset.filter(
                staff_profile__first_name__icontains=search
            )
        status_value = self.request.query_params.get("status")
        if status_value:
            queryset = queryset.filter(status=status_value)
        return queryset.distinct()

    def perform_create(self, serializer):
        institution = getattr(self.request, "institution", None)
        if institution is None:
            raise serializers.ValidationError(
                {"institution": "Select a school before adding an employee."}
            )

        teacher = serializer.validated_data.get("teacher")
        staff_profile = serializer.validated_data.get("staff_profile")
        profile = teacher or staff_profile
        field = "teacher" if teacher else "staff_profile"
        if Employee.objects.filter(**{field: profile}).exists():
            raise serializers.ValidationError({field: "This profile already has an employee record."})
        if not available_employee_profiles(self.request, "teacher" if teacher else "staff").filter(pk=profile.pk).exists():
            raise serializers.ValidationError({field: "Choose a profile from the active school."})
        campus = serializer.validated_data.get("primary_campus") or profile.primary_campus
        if campus is not None:
            assert_campus_allowed(self.request.user, campus.pk, request=self.request)
            if campus.school_id != institution.pk:
                raise serializers.ValidationError({"primary_campus": "Campus must belong to the selected school."})

        # Generate employee number if the client left it blank.
        emp_number = serializer.validated_data.get("employee_number")
        if not emp_number:
            prefix = (
                f"T-{institution.id:03d}"
                if teacher
                else f"S-{institution.id:03d}"
            )
            last = (
                Employee.objects
                .filter(
                    institution=institution,
                    employee_number__startswith=prefix,
                )
                .order_by("-employee_number")
                .values_list("employee_number", flat=True)
                .first()
            )
            seq = 1
            if last:
                try:
                    seq = int(last.split("-")[-1]) + 1
                except (ValueError, IndexError):
                    pass
            emp_number = f"{prefix}-{seq:04d}"

        serializer.save(
            institution=institution,
            primary_campus=campus,
            employee_number=emp_number,
            status=serializer.validated_data.get("status", "active"),
        )


class EmployeeDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = EmployeeSerializer

    def get_queryset(self):
        return employee_queryset(self.request)


class EmployeeContractListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = EmploymentContractSerializer

    def get_queryset(self):
        return owned_queryset(EmploymentContract, self.request).order_by("-start_date")

    def perform_create(self, serializer):
        employee = get_object_or_404(employee_queryset(self.request), pk=self.kwargs["employee_id"])
        serializer.save(employee=employee)


class EmployeeDocumentListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = EmployeeDocumentSerializer

    def get_queryset(self):
        return owned_queryset(EmployeeDocument, self.request).order_by("-created_at")

    def perform_create(self, serializer):
        employee = get_object_or_404(employee_queryset(self.request), pk=self.kwargs["employee_id"])
        campus = serializer.validated_data.get("campus") or employee.primary_campus
        serializer.save(employee=employee, uploaded_by=self.request.user, campus=campus)


class EmployeeDocumentDetailView(generics.RetrieveDestroyAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = EmployeeDocumentSerializer

    def get_queryset(self):
        return owned_queryset(EmployeeDocument, self.request)


class EmployeeWorkloadListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = WorkloadAssignmentSerializer

    def get_queryset(self):
        return owned_queryset(WorkloadAssignment, self.request).order_by("-created_at")

    def perform_create(self, serializer):
        employee = get_object_or_404(employee_queryset(self.request), pk=self.kwargs["employee_id"])
        serializer.save(employee=employee)


class EmployeeReviewListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = PerformanceReviewSerializer

    def get_queryset(self):
        return owned_queryset(PerformanceReview, self.request).order_by("-review_date")

    def perform_create(self, serializer):
        employee = get_object_or_404(employee_queryset(self.request), pk=self.kwargs["employee_id"])
        serializer.save(employee=employee, reviewer=self.request.user)


class EmploymentEventListView(generics.ListAPIView):
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = EmploymentEventSerializer

    def get_queryset(self):
        return owned_queryset(EmploymentEvent, self.request).order_by("-effective_date")


class EmploymentEventCreateView(APIView):
    permission_classes = [IsAccountantRole]

    def post(self, request):
        employee = get_object_or_404(employee_queryset(request), pk=request.data.get("employee"))
        event_data = request.data.copy()
        event_data.pop("employee", None)
        serializer = EmploymentEventSerializer(data=event_data)
        serializer.is_valid(raise_exception=True)
        event_type = serializer.validated_data["event_type"]
        to_campus = serializer.validated_data.get("to_campus")
        if to_campus:
            assert_campus_allowed(request.user, to_campus.pk)
        old_status = employee.status
        old_campus = employee.primary_campus
        old_designation = employee.designation
        event = serializer.save(employee=employee, recorded_by=request.user, from_campus=old_campus, previous_designation=old_designation)
        updates = {"updated_at"}
        if to_campus:
            employee.primary_campus = to_campus
            updates.add("primary_campus")
        if event.new_designation:
            employee.designation = event.new_designation
            updates.add("designation")
        if event_type in ("resigned", "terminated"):
            employee.status = event_type
            updates.add("status")
        employee.save(update_fields=list(updates))
        return Response(EmploymentEventSerializer(event).data, status=201)


# Department Views
class DepartmentListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = DepartmentSerializer

    def get_queryset(self):
        queryset = Department.objects.filter(institution=self.request.institution)
        if not is_manager(self.request.user):
            queryset = apply_campus_scope(queryset, self.request, "campus_id")
        return queryset

    def perform_create(self, serializer):
        serializer.save(institution=self.request.institution)


class DepartmentDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = DepartmentSerializer

    def get_queryset(self):
        queryset = Department.objects.filter(institution=self.request.institution)
        if not is_manager(self.request.user):
            queryset = apply_campus_scope(queryset, self.request, "campus_id")
        return queryset


# Designation Views
class DesignationListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = DesignationSerializer

    def get_queryset(self):
        queryset = Designation.objects.filter(institution=self.request.institution)
        department = self.request.query_params.get("department")
        if department:
            queryset = queryset.filter(department_id=department)
        return queryset

    def perform_create(self, serializer):
        serializer.save(institution=self.request.institution)


class DesignationDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = DesignationSerializer

    def get_queryset(self):
        return Designation.objects.filter(institution=self.request.institution)


# Leave Type Views
class LeaveTypeListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = LeaveTypeSerializer

    def get_queryset(self):
        queryset = LeaveType.objects.filter(institution=self.request.institution)
        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category=category)
        status = self.request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)
        return queryset

    def perform_create(self, serializer):
        serializer.save(institution=self.request.institution)


class LeaveTypeDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = LeaveTypeSerializer

    def get_queryset(self):
        return LeaveType.objects.filter(institution=self.request.institution)


# Leave Policy Views
class LeavePolicyListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = LeavePolicySerializer

    def get_queryset(self):
        queryset = LeavePolicy.objects.filter(institution=self.request.institution)
        department = self.request.query_params.get("department")
        if department:
            queryset = queryset.filter(department_id=department)
        leave_type = self.request.query_params.get("leave_type")
        if leave_type:
            queryset = queryset.filter(leave_type_id=leave_type)
        status = self.request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)
        return queryset

    def perform_create(self, serializer):
        serializer.save(institution=self.request.institution)


class LeavePolicyDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = LeavePolicySerializer

    def get_queryset(self):
        return LeavePolicy.objects.filter(institution=self.request.institution)


# Leave Balance Views
class LeaveBalanceListView(generics.ListAPIView):
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = LeaveBalanceSerializer

    def get_queryset(self):
        queryset = LeaveBalance.objects.select_related("employee", "leave_type", "academic_year").filter(
            employee__institution=self.request.institution
        )
        queryset = apply_campus_scope(queryset, self.request, "employee__primary_campus_id")

        employee = self.request.query_params.get("employee")
        if employee:
            queryset = queryset.filter(employee_id=employee)

        leave_type = self.request.query_params.get("leave_type")
        if leave_type:
            queryset = queryset.filter(leave_type_id=leave_type)

        academic_year = self.request.query_params.get("academic_year")
        if academic_year:
            queryset = queryset.filter(academic_year_id=academic_year)

        return queryset


class LeaveBalanceDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = LeaveBalanceSerializer

    def get_queryset(self):
        queryset = LeaveBalance.objects.select_related("employee", "leave_type", "academic_year").filter(
            employee__institution=self.request.institution
        )
        queryset = apply_campus_scope(queryset, self.request, "employee__primary_campus_id")
        return queryset


# Leave Request Views
class LeaveRequestListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = LeaveRequestSerializer

    def get_queryset(self):
        queryset = LeaveRequest.objects.select_related(
            "employee", "leave_type", "leave_policy"
        ).filter(employee__institution=self.request.institution)
        queryset = apply_campus_scope(queryset, self.request, "employee__primary_campus_id")

        employee = self.request.query_params.get("employee")
        if employee:
            queryset = queryset.filter(employee_id=employee)

        status = self.request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)

        leave_type = self.request.query_params.get("leave_type")
        if leave_type:
            queryset = queryset.filter(leave_type_id=leave_type)

        start_date = self.request.query_params.get("start_date")
        if start_date:
            queryset = queryset.filter(start_date__gte=start_date)

        end_date = self.request.query_params.get("end_date")
        if end_date:
            queryset = queryset.filter(end_date__lte=end_date)

        return queryset.order_by("-applied_on")

    def perform_create(self, serializer):
        employee = get_object_or_404(
            Employee.objects.filter(institution=self.request.institution),
            pk=self.request.data.get("employee")
        )
        # Auto-assign leave policy based on employee's department and leave type
        leave_type_id = self.request.data.get("leave_type")
        leave_policy = None
        if leave_type_id and employee.department_id:
            from .models import LeavePolicy
            leave_policy = LeavePolicy.objects.filter(
                institution=self.request.institution,
                department=employee.department,
                leave_type_id=leave_type_id,
                effective_from__lte=serializer.validated_data.get("start_date"),
                status="active"
            ).first()
        serializer.save(employee=employee, leave_policy=leave_policy)


class LeaveRequestDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = LeaveRequestSerializer

    def get_queryset(self):
        queryset = LeaveRequest.objects.select_related(
            "employee", "leave_type", "leave_policy"
        ).filter(employee__institution=self.request.institution)
        queryset = apply_campus_scope(queryset, self.request, "employee__primary_campus_id")
        return queryset


class LeaveRequestActionView(APIView):
    permission_classes = [IsAccountantRole]

    def post(self, request, pk, action):
        leave_request = get_object_or_404(
            LeaveRequest.objects.select_related("employee", "leave_type"),
            pk=pk,
            employee__institution=request.institution
        )
        queryset = apply_campus_scope(
            LeaveRequest.objects.filter(pk=pk),
            request,
            "employee__primary_campus_id"
        )
        if not queryset.exists():
            raise PermissionDenied("Access denied")

        if action == "approve":
            comments = request.data.get("comments", "")
            leave_request.approve(request.user, comments)
            return Response({"detail": "Leave request approved"})
        elif action == "reject":
            reason = request.data.get("reason", "")
            if not reason:
                return Response({"detail": "Rejection reason is required"}, status=status.HTTP_400_BAD_REQUEST)
            leave_request.reject(request.user, reason)
            return Response({"detail": "Leave request rejected"})
        elif action == "cancel":
            reason = request.data.get("reason", "")
            leave_request.cancel(request.user, reason)
            return Response({"detail": "Leave request cancelled"})
        else:
            return Response({"detail": "Invalid action"}, status=status.HTTP_400_BAD_REQUEST)


# Allowance Views
class AllowanceListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = AllowanceSerializer

    def get_queryset(self):
        queryset = Allowance.objects.filter(institution=self.request.institution)
        status = self.request.query_params.get("status")
        if status == "active":
            queryset = queryset.filter(is_active=True)
        elif status == "inactive":
            queryset = queryset.filter(is_active=False)
        return queryset

    def perform_create(self, serializer):
        serializer.save(institution=self.request.institution)


class AllowanceDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = AllowanceSerializer

    def get_queryset(self):
        return Allowance.objects.filter(institution=self.request.institution)


# Deduction Views
class DeductionListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = DeductionSerializer

    def get_queryset(self):
        queryset = Deduction.objects.filter(institution=self.request.institution)
        status = self.request.query_params.get("status")
        if status == "active":
            queryset = queryset.filter(is_active=True)
        elif status == "inactive":
            queryset = queryset.filter(is_active=False)
        return queryset

    def perform_create(self, serializer):
        serializer.save(institution=self.request.institution)


class DeductionDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = DeductionSerializer

    def get_queryset(self):
        return Deduction.objects.filter(institution=self.request.institution)


# Bonus Views
class BonusListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = BonusSerializer

    def get_queryset(self):
        queryset = Bonus.objects.filter(institution=self.request.institution)
        status = self.request.query_params.get("status")
        if status == "active":
            queryset = queryset.filter(is_active=True)
        elif status == "inactive":
            queryset = queryset.filter(is_active=False)
        bonus_type = self.request.query_params.get("bonus_type")
        if bonus_type:
            queryset = queryset.filter(bonus_type=bonus_type)
        return queryset

    def perform_create(self, serializer):
        serializer.save(institution=self.request.institution)


class BonusDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = BonusSerializer

    def get_queryset(self):
        return Bonus.objects.filter(institution=self.request.institution)


# Overtime Views
class OvertimeListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = OvertimeSerializer

    def get_queryset(self):
        queryset = Overtime.objects.select_related("employee", "payroll_period").filter(
            employee__institution=self.request.institution
        )
        queryset = apply_campus_scope(queryset, self.request, "employee__primary_campus_id")

        employee = self.request.query_params.get("employee")
        if employee:
            queryset = queryset.filter(employee_id=employee)

        status = self.request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)

        date_from = self.request.query_params.get("date_from")
        if date_from:
            queryset = queryset.filter(date__gte=date_from)

        date_to = self.request.query_params.get("date_to")
        if date_to:
            queryset = queryset.filter(date__lte=date_to)

        return queryset.order_by("-date")

    def perform_create(self, serializer):
        employee = get_object_or_404(
            Employee.objects.filter(institution=self.request.institution),
            pk=self.request.data.get("employee")
        )
        serializer.save(employee=employee)


class OvertimeDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = OvertimeSerializer

    def get_queryset(self):
        queryset = Overtime.objects.select_related("employee", "payroll_period").filter(
            employee__institution=self.request.institution
        )
        return apply_campus_scope(queryset, self.request, "employee__primary_campus_id")


class OvertimeActionView(APIView):
    permission_classes = [IsAccountantRole]

    def post(self, request, pk, action):
        overtime = get_object_or_404(
            Overtime.objects.select_related("employee"),
            pk=pk,
            employee__institution=request.institution
        )
        queryset = apply_campus_scope(
            Overtime.objects.filter(pk=pk),
            request,
            "employee__primary_campus_id"
        )
        if not queryset.exists():
            raise PermissionDenied("Access denied")

        if action == "approve":
            overtime.status = "approved"
            overtime.approved_by = request.user
            overtime.approved_on = timezone.now()
            overtime.save(update_fields=["status", "approved_by", "approved_on"])
            return Response({"detail": "Overtime approved"})
        elif action == "reject":
            overtime.status = "rejected"
            overtime.save(update_fields=["status"])
            return Response({"detail": "Overtime rejected"})
        else:
            return Response({"detail": "Invalid action"}, status=status.HTTP_400_BAD_REQUEST)


# Loan Views
class LoanListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = LoanSerializer

    def get_queryset(self):
        queryset = Loan.objects.select_related("employee").filter(
            employee__institution=self.request.institution
        )
        queryset = apply_campus_scope(queryset, self.request, "employee__primary_campus_id")

        employee = self.request.query_params.get("employee")
        if employee:
            queryset = queryset.filter(employee_id=employee)

        status = self.request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)

        return queryset.order_by("-applied_on")

    def perform_create(self, serializer):
        employee = get_object_or_404(
            Employee.objects.filter(institution=self.request.institution),
            pk=self.request.data.get("employee")
        )
        serializer.save(employee=employee)


class LoanDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = LoanSerializer

    def get_queryset(self):
        queryset = Loan.objects.select_related("employee").filter(
            employee__institution=self.request.institution
        )
        return apply_campus_scope(queryset, self.request, "employee__primary_campus_id")


class LoanActionView(APIView):
    permission_classes = [IsAccountantRole]

    def post(self, request, pk, action):
        loan = get_object_or_404(
            Loan.objects.select_related("employee"),
            pk=pk,
            employee__institution=request.institution
        )
        queryset = apply_campus_scope(
            Loan.objects.filter(pk=pk),
            request,
            "employee__primary_campus_id"
        )
        if not queryset.exists():
            raise PermissionDenied("Access denied")

        if action == "approve":
            loan.status = "approved"
            loan.approved_by = request.user
            loan.approved_on = date.today()
            loan.status = "active"
            loan.remaining_balance = loan.principal_amount
            loan.save(update_fields=["status", "approved_by", "approved_on", "remaining_balance"])
            return Response({"detail": "Loan approved"})
        elif action == "reject":
            reason = request.data.get("reason", "")
            if not reason:
                return Response({"detail": "Rejection reason is required"}, status=status.HTTP_400_BAD_REQUEST)
            loan.status = "rejected"
            loan.rejection_reason = reason
            loan.save(update_fields=["status", "rejection_reason"])
            return Response({"detail": "Loan rejected"})
        elif action == "payment":
            amount = request.data.get("amount")
            if not amount:
                return Response({"detail": "Amount is required"}, status=status.HTTP_400_BAD_REQUEST)
            loan.record_payment(Decimal(amount), request.user)
            return Response({"detail": "Payment recorded"})
        else:
            return Response({"detail": "Invalid action"}, status=status.HTTP_400_BAD_REQUEST)


# Advance Views
class AdvanceListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = AdvanceSerializer

    def get_queryset(self):
        queryset = Advance.objects.select_related("employee").filter(
            employee__institution=self.request.institution
        )
        queryset = apply_campus_scope(queryset, self.request, "employee__primary_campus_id")

        employee = self.request.query_params.get("employee")
        if employee:
            queryset = queryset.filter(employee_id=employee)

        status = self.request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)

        return queryset.order_by("-requested_on")

    def perform_create(self, serializer):
        employee = get_object_or_404(
            Employee.objects.filter(institution=self.request.institution),
            pk=self.request.data.get("employee")
        )
        serializer.save(employee=employee)


class AdvanceDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = AdvanceSerializer

    def get_queryset(self):
        queryset = Advance.objects.select_related("employee").filter(
            employee__institution=self.request.institution
        )
        return apply_campus_scope(queryset, self.request, "employee__primary_campus_id")


class AdvanceActionView(APIView):
    permission_classes = [IsAccountantRole]

    def post(self, request, pk, action):
        advance = get_object_or_404(
            Advance.objects.select_related("employee"),
            pk=pk,
            employee__institution=request.institution
        )
        queryset = apply_campus_scope(
            Advance.objects.filter(pk=pk),
            request,
            "employee__primary_campus_id"
        )
        if not queryset.exists():
            raise PermissionDenied("Access denied")

        if action == "approve":
            advance.status = "approved"
            advance.approved_by = request.user
            advance.approved_on = date.today()
            advance.remaining_balance = advance.amount
            advance.status = "active"
            advance.save(update_fields=["status", "approved_by", "approved_on", "remaining_balance"])
            return Response({"detail": "Advance approved"})
        elif action == "reject":
            reason = request.data.get("reason", "")
            if not reason:
                return Response({"detail": "Rejection reason is required"}, status=status.HTTP_400_BAD_REQUEST)
            advance.status = "rejected"
            advance.rejection_reason = reason
            advance.save(update_fields=["status", "rejection_reason"])
            return Response({"detail": "Advance rejected"})
        else:
            return Response({"detail": "Invalid action"}, status=status.HTTP_400_BAD_REQUEST)


# Salary Revision Views
class SalaryRevisionListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = SalaryRevisionSerializer

    def get_queryset(self):
        queryset = SalaryRevision.objects.select_related("employee").filter(
            employee__institution=self.request.institution
        )
        queryset = apply_campus_scope(queryset, self.request, "employee__primary_campus_id")

        employee = self.request.query_params.get("employee")
        if employee:
            queryset = queryset.filter(employee_id=employee)

        return queryset.order_by("-effective_date")

    def perform_create(self, serializer):
        employee = get_object_or_404(
            Employee.objects.filter(institution=self.request.institution),
            pk=self.request.data.get("employee")
        )
        serializer.save(employee=employee, approved_by=self.request.user, approved_on=date.today())


class SalaryRevisionDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = SalaryRevisionSerializer

    def get_queryset(self):
        queryset = SalaryRevision.objects.select_related("employee").filter(
            employee__institution=self.request.institution
        )
        return apply_campus_scope(queryset, self.request, "employee__primary_campus_id")


# Payroll Period Views
class PayrollPeriodListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = PayrollPeriodSerializer

    def get_queryset(self):
        queryset = PayrollPeriod.objects.filter(institution=self.request.institution)
        if not is_manager(self.request.user):
            queryset = apply_campus_scope(queryset, self.request, "campus_id")

        status = self.request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)

        return queryset.order_by("-start_date")

    def perform_create(self, serializer):
        serializer.save(institution=self.request.institution)


class PayrollPeriodDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = PayrollPeriodSerializer

    def get_queryset(self):
        queryset = PayrollPeriod.objects.filter(institution=self.request.institution)
        if not is_manager(self.request.user):
            queryset = apply_campus_scope(queryset, self.request, "campus_id")
        return queryset


class PayrollPeriodActionView(APIView):
    permission_classes = [IsAccountantRole]

    def post(self, request, pk, action):
        period = get_object_or_404(
            PayrollPeriod,
            pk=pk,
            institution=request.institution
        )
        if not is_manager(request.user):
            queryset = apply_campus_scope(
                PayrollPeriod.objects.filter(pk=pk),
                request,
                "campus_id"
            )
            if not queryset.exists():
                raise PermissionDenied("Access denied")

        if action == "open":
            period.open_for_processing(request.user)
            return Response({"detail": "Payroll period opened for processing"})
        elif action == "approve":
            period.approve(request.user)
            return Response({"detail": "Payroll period approved"})
        elif action == "close":
            period.close(request.user)
            return Response({"detail": "Payroll period closed"})
        else:
            return Response({"detail": "Invalid action"}, status=status.HTTP_400_BAD_REQUEST)


# Exit Clearance Views
class ExitClearanceListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = ExitClearanceSerializer

    def get_queryset(self):
        queryset = ExitClearance.objects.select_related("employee").filter(
            employee__institution=self.request.institution
        )
        queryset = apply_campus_scope(queryset, self.request, "employee__primary_campus_id")

        employee = self.request.query_params.get("employee")
        if employee:
            queryset = queryset.filter(employee_id=employee)

        status = self.request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)

        return queryset.order_by("-initiated_on")

    def perform_create(self, serializer):
        employee = get_object_or_404(
            Employee.objects.filter(institution=self.request.institution),
            pk=self.request.data.get("employee")
        )
        clearance = serializer.save(employee=employee, initiated_by=self.request.user)
        self.create_standard_items(clearance)

    def create_standard_items(self, clearance):
        standard_departments = [
            ("hr", "HR"),
            ("finance", "Finance"),
            ("library", "Library"),
            ("it", "IT"),
            ("administration", "Administration"),
            ("transport", "Transport"),
            ("inventory", "Inventory"),
        ]
        from .models import ClearanceItem
        for dept_code, dept_name in standard_departments:
            ClearanceItem.objects.create(
                clearance=clearance,
                department=dept_code,
                department_name=dept_name,
            )


class ExitClearanceDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = ExitClearanceSerializer

    def get_queryset(self):
        queryset = ExitClearance.objects.select_related("employee").prefetch_related("items").filter(
            employee__institution=self.request.institution
        )
        return apply_campus_scope(queryset, self.request, "employee__primary_campus_id")


class ClearanceItemActionView(APIView):
    permission_classes = [IsAccountantRole]

    def post(self, request, pk, action):
        item = get_object_or_404(
            ClearanceItem,
            pk=pk,
            clearance__employee__institution=request.institution
        )
        queryset = apply_campus_scope(
            ClearanceItem.objects.filter(pk=pk),
            request,
            "clearance__employee__primary_campus_id"
        )
        if not queryset.exists():
            raise PermissionDenied("Access denied")

        if action == "clear":
            remarks = request.data.get("remarks", "")
            item.clear(request.user, remarks)
            return Response({"detail": "Clearance item cleared"})
        elif action == "block":
            item.status = "blocked"
            item.remarks = request.data.get("remarks", "")
            item.save(update_fields=["status", "remarks"])
            return Response({"detail": "Clearance item blocked"})
        else:
            return Response({"detail": "Invalid action"}, status=status.HTTP_400_BAD_REQUEST)


# Recruitment Views
class JobPositionListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = JobPositionSerializer

    def get_queryset(self):
        queryset = JobPosition.objects.filter(institution=self.request.institution)
        department = self.request.query_params.get("department")
        if department:
            queryset = queryset.filter(department_id=department)
        status = self.request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)
        return queryset.order_by("-posted_on")

    def perform_create(self, serializer):
        serializer.save(institution=self.request.institution, created_by=self.request.user)


class JobPositionDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = JobPositionSerializer

    def get_queryset(self):
        return JobPosition.objects.filter(institution=self.request.institution)


class CandidateListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = CandidateSerializer

    def get_queryset(self):
        queryset = Candidate.objects.filter(institution=self.request.institution)
        status = self.request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)
        position = self.request.query_params.get("position")
        if position:
            queryset = queryset.filter(applied_position_id=position)
        return queryset.order_by("-applied_on")

    def perform_create(self, serializer):
        serializer.save(institution=self.request.institution)


class CandidateDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = CandidateSerializer

    def get_queryset(self):
        return Candidate.objects.filter(institution=self.request.institution)


class ApplicationListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = ApplicationSerializer

    def get_queryset(self):
        queryset = Application.objects.select_related("candidate", "position").filter(
            candidate__institution=self.request.institution
        )
        status = self.request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)
        position = self.request.query_params.get("position")
        if position:
            queryset = queryset.filter(position_id=position)
        return queryset.order_by("-applied_on")

    def perform_create(self, serializer):
        candidate = serializer.validated_data.get("candidate")
        position = serializer.validated_data.get("position")
        institution = self.request.institution

        if candidate is not None and candidate.institution_id != institution.id:
            raise PermissionDenied(
                "Candidate does not belong to the active institution."
            )
        if position is not None and position.institution_id != institution.id:
            raise PermissionDenied(
                "Position does not belong to the active institution."
            )

        serializer.save()


class ApplicationDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = ApplicationSerializer

    def get_queryset(self):
        return Application.objects.select_related("candidate", "position").filter(
            candidate__institution=self.request.institution
        )


class InterviewListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = InterviewSerializer

    def get_queryset(self):
        queryset = Interview.objects.select_related(
            "application__candidate", "application__position", "interviewer"
        ).filter(application__candidate__institution=self.request.institution)

        status = self.request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)

        interviewer = self.request.query_params.get("interviewer")
        if interviewer:
            queryset = queryset.filter(interviewer_id=interviewer)

        return queryset.order_by("scheduled_on")

    def perform_create(self, serializer):
        application = serializer.validated_data.get("application")
        interviewer = serializer.validated_data.get("interviewer")
        institution = self.request.institution

        # The application cannot have an institution field; its candidate does.
        if application is not None and (
            application.candidate_id is None
            or Application.objects.filter(
                pk=application.pk,
                candidate__institution=institution,
            ).exists() is False
        ):
            raise PermissionDenied(
                "Application does not belong to the active institution."
            )

        if interviewer is not None and interviewer.institution_id != institution.id:
            raise PermissionDenied(
                "Interviewer does not belong to the active institution."
            )

        serializer.save(scheduled_by=self.request.user)


class InterviewDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = InterviewSerializer

    def get_queryset(self):
        return Interview.objects.select_related(
            "application__candidate", "application__position", "interviewer"
        ).filter(application__candidate__institution=self.request.institution)


class InterviewActionView(APIView):
    permission_classes = [IsAccountantRole]

    def post(self, request, pk, action):
        interview = get_object_or_404(
            Interview.objects.select_related("application__candidate", "application__position"),
            pk=pk,
            application__candidate__institution=request.institution
        )

        if action == "complete":
            interview.status = "completed"
            interview.conducted_on = date.today()
            interview.feedback = request.data.get("feedback", "")
            interview.rating = request.data.get("rating")
            interview.recommendation = request.data.get("recommendation")
            interview.save(update_fields=["status", "conducted_on", "feedback", "rating", "recommendation"])
            return Response({"detail": "Interview completed"})
        elif action == "cancel":
            interview.status = "cancelled"
            interview.save(update_fields=["status"])
            return Response({"detail": "Interview cancelled"})
        elif action == "reschedule":
            new_date = request.data.get("scheduled_on")
            if not new_date:
                return Response({"detail": "New date is required"}, status=status.HTTP_400_BAD_REQUEST)
            interview.scheduled_on = new_date
            interview.status = "rescheduled"
            interview.save(update_fields=["scheduled_on", "status"])
            return Response({"detail": "Interview rescheduled"})
        else:
            return Response({"detail": "Invalid action"}, status=status.HTTP_400_BAD_REQUEST)


# Updated Employee Views with Detail Serializer
class EmployeeDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAdminOrReadOnly]
    serializer_class = EmployeeDetailSerializer

    def get_queryset(self):
        return employee_queryset(self.request)

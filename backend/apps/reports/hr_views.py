"""HR and Payroll Reports."""

from decimal import Decimal
from django.db.models import Count, Q, Case, When, Value, IntegerField, Sum, Avg, Max, Min, Prefetch
from django.utils import timezone
from rest_framework.response import Response

from apps.accounts.access import apply_campus_scope
from apps.accounts.permissions import IsAccountantRole
from apps.reports.base_views import AggregateReportView, BaseReportView
from apps.reports.utils import quantize, to_csv


class EmployeeMasterReportView(AggregateReportView):
    """HR Employee master report."""

    permission_classes = [IsAccountantRole]
    report_definition_key = "hr_employee"
    model = "apps.hr.models.Employee"

    def get_base_queryset(self, request):
        from apps.hr.models import Employee
        from apps.payroll.models import SalaryStructure

        return Employee.objects.select_related(
            "teacher",
            "staff_profile",
            "department",
            "designation",
            "primary_campus",
        ).prefetch_related(
            Prefetch(
                "salary_structures",
                queryset=SalaryStructure.objects.filter(status="active").order_by("-effective_date"),
                to_attr="active_salary_structures",
            )
        )

    def get_queryset(self, request):
        queryset = self.get_base_queryset(request)
        queryset = apply_campus_scope(queryset, request, "primary_campus_id")

        status = request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)

        department = request.query_params.get("department")
        if department:
            queryset = queryset.filter(department_id=department)

        return queryset

    def get_summary(self, queryset, request):
        total = queryset.count()
        by_status = queryset.values("status").annotate(count=Count("id"))
        by_department = queryset.values("department__name").annotate(count=Count("id"))
        by_campus = queryset.values("primary_campus__name").annotate(count=Count("id"))

        return {
            "total_employees": total,
            "by_status": list(by_status),
            "by_department": list(by_department),
            "by_campus": list(by_campus),
        }

    def get_detail_rows(self, queryset, request):
        rows = []
        for emp in queryset:
            profile = emp.staff_profile or emp.teacher
            salary_structure = emp.active_salary_structures[0] if emp.active_salary_structures else None
            rows.append({
                "employee_id": emp.employee_number,
                "full_name": emp.full_name,
                "email": profile.email if profile and profile.email else "-",
                "phone": profile.phone if profile and profile.phone else "-",
                "department": emp.department.name if emp.department else "-",
                "designation": emp.designation.name if emp.designation else "-",
                "campus": emp.primary_campus.name if emp.primary_campus else "-",
                "employment_type": emp.get_employment_type_display(),
                "joining_date": emp.joining_date,
                "status": emp.get_status_display(),
                "basic_salary": str(salary_structure.basic_salary) if salary_structure else "0",
            })
        return rows


class HRAttendanceReportView(AggregateReportView):
    """HR Attendance report."""

    permission_classes = [IsAccountantRole]
    report_definition_key = "hr_attendance"
    model = "apps.hr.models.Attendance"

    def get_base_queryset(self, request):
        from apps.hr.models import Attendance
        return Attendance.objects.select_related("employee", "employee__user", "employee__campus")

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = apply_campus_scope(queryset, request, "employee__campus_id")

        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")

        if date_from:
            queryset = queryset.filter(date__gte=date_from)
        if date_to:
            queryset = queryset.filter(date__lte=date_to)

        employee = request.query_params.get("employee")
        if employee:
            queryset = queryset.filter(employee_id=employee)

        return queryset

    def get_summary(self, queryset, request):
        total = queryset.count()
        present = queryset.filter(status="present").count()
        absent = queryset.filter(status="absent").count()
        late = queryset.filter(status="late").count()
        leave = queryset.filter(status="leave").count()

        return {
            "total_records": total,
            "present": present,
            "absent": absent,
            "late": late,
            "leave": leave,
            "attendance_rate": round((present + late) / total * 100, 2) if total else 0,
        }

    def get_detail_rows(self, queryset, request):
        rows = []
        for record in queryset:
            rows.append({
                "date": record.date,
                "employee_id": record.employee.employee_id,
                "employee": record.employee.full_name,
                "department": record.employee.department.name if record.employee.department else "-",
                "campus": record.employee.campus.name if record.employee.campus else "-",
                "status": record.get_status_display(),
                "check_in": record.check_in,
                "check_out": record.check_out,
            })
        return rows


class HRLeaveReportView(AggregateReportView):
    """HR Leave report."""

    permission_classes = [IsAccountantRole]
    report_definition_key = "hr_leave"
    model = "apps.hr.models.LeaveRequest"

    def get_base_queryset(self, request):
        from apps.hr.models import LeaveRequest
        return LeaveRequest.objects.select_related(
            "employee",
            "employee__teacher",
            "employee__staff_profile",
            "employee__primary_campus",
            "leave_type",
            "reviewed_by",
        )

    def get_queryset(self, request):
        queryset = self.get_base_queryset(request)
        queryset = apply_campus_scope(
            queryset,
            request,
            "employee__primary_campus_id",
            "employee__institution_id",
        )

        status = request.query_params.get("status")
        if status:
            queryset = queryset.filter(status=status)

        leave_type = request.query_params.get("leave_type")
        if leave_type:
            queryset = queryset.filter(leave_type_id=leave_type)

        date_from = request.query_params.get("date_from")
        if date_from:
            queryset = queryset.filter(start_date__gte=date_from)

        date_to = request.query_params.get("date_to")
        if date_to:
            queryset = queryset.filter(end_date__lte=date_to)

        return queryset

    def get_summary(self, queryset, request):
        total = queryset.count()
        by_status = queryset.values("status").annotate(count=Count("id"))
        by_type = queryset.values("leave_type__name").annotate(count=Count("id"))

        total_days = sum(l.total_days for l in queryset)
        approved_days = sum(l.total_days for l in queryset.filter(status="approved"))

        return {
            "total_requests": total,
            "total_days": total_days,
            "approved_days": approved_days,
            "by_status": list(by_status),
            "by_type": list(by_type),
        }

    def get_detail_rows(self, queryset, request):
        rows = []
        for leave in queryset:
            rows.append({
                "employee_id": leave.employee.employee_number,
                "employee": leave.employee.full_name,
                "leave_type": leave.leave_type.name if leave.leave_type else "-",
                "start_date": leave.start_date,
                "end_date": leave.end_date,
                "days": leave.total_days,
                "reason": leave.reason,
                "status": leave.get_status_display(),
                "reviewed_by": leave.reviewed_by.get_full_name() if leave.reviewed_by else "-",
            })
        return rows


class PayrollMonthlyReportView(AggregateReportView):
    """Monthly payroll report."""

    permission_classes = [IsAccountantRole]
    report_definition_key = "payroll_monthly"
    model = "apps.payroll.models.PayrollRecord"

    def get_base_queryset(self, request):
        from apps.payroll.models import PayrollRecord
        return PayrollRecord.objects.select_related(
            "employee", "employee__primary_campus", "salary_structure"
        ).prefetch_related("employee__staff_profile", "employee__teacher")

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = apply_campus_scope(queryset, request, "employee__primary_campus_id", institution_field=None)

        year = request.query_params.get("year")
        if year:
            queryset = queryset.filter(year=year)

        month = request.query_params.get("month")
        if month:
            queryset = queryset.filter(month=month)

        return queryset

    def get_summary(self, queryset, request):
        total_gross = sum(r.gross_salary for r in queryset)
        total_deductions = sum(r.total_deductions for r in queryset)
        total_net = sum(r.net_salary for r in queryset)

        by_campus = {}
        for record in queryset:
            campus = record.employee.primary_campus.name if record.employee.primary_campus_id else "-"
            if campus not in by_campus:
                by_campus[campus] = {"gross": Decimal("0"), "deductions": Decimal("0"), "net": Decimal("0"), "count": 0}
            by_campus[campus]["gross"] += record.gross_salary
            by_campus[campus]["deductions"] += record.total_deductions
            by_campus[campus]["net"] += record.net_salary
            by_campus[campus]["count"] += 1

        return {
            "records": queryset.count(),
            "total_gross": quantize(total_gross),
            "total_deductions": quantize(total_deductions),
            "total_net": quantize(total_net),
            "by_campus": [
                {
                    "campus": k,
                    "employees": v["count"],
                    "gross": quantize(v["gross"]),
                    "deductions": quantize(v["deductions"]),
                    "net": quantize(v["net"]),
                }
                for k, v in sorted(by_campus.items())
            ],
        }

    def get_detail_rows(self, queryset, request):
        rows = []
        for record in queryset:
            rows.append({
                "employee_id": record.employee.employee_number,
                "employee": record.employee.full_name,
                "campus": record.employee.primary_campus.name if record.employee.primary_campus_id else "-",
                "year": record.year,
                "month": record.month,
                "gross_salary": quantize(record.gross_salary),
                "total_deductions": quantize(record.total_deductions),
                "net_salary": quantize(record.net_salary),
                "status": record.status,
            })
        return rows


class EmployeeSalaryReportView(BaseReportView):
    """Individual employee salary report."""

    permission_classes = [IsAccountantRole]
    report_definition_key = "payroll_salary_slip"
    model = "apps.payroll.models.PayrollRecord"

    def get_base_queryset(self, request):
        from apps.payroll.models import PayrollRecord
        return PayrollRecord.objects.select_related(
            "employee", "employee__primary_campus", "salary_structure"
        ).prefetch_related("employee__staff_profile", "employee__teacher")

    def get_queryset(self, request):
        queryset = super().get_queryset(request)

        employee = request.query_params.get("employee")
        if not employee:
            return queryset.none()
        queryset = queryset.filter(employee_id=employee)

        year = request.query_params.get("year")
        if year:
            queryset = queryset.filter(year=year)

        month = request.query_params.get("month")
        if month:
            queryset = queryset.filter(month=month)

        return queryset

    def get(self, request):
        queryset = self.get_queryset(request)
        records = list(queryset)

        if not records:
            return Response({"detail": "No payroll records found"}, status=404)

        if len(records) == 1:
            return Response(self.build_salary_slip(records[0]))

        rows = []
        for r in records:
            rows.append({
                "id": r.id,
                "employee": r.employee.full_name,
                "year": r.year,
                "month": r.month,
                "gross": quantize(r.gross_salary),
                "deductions": quantize(r.total_deductions),
                "net": quantize(r.net_salary),
                "status": r.status,
            })
        return Response({"records": rows})

    def build_salary_slip(self, record):
        details = record.component_details or {}
        raw_allowances = details.get("allowances") or {}
        raw_deductions = details.get("deductions") or {}

        allowances = []
        for code, entry in raw_allowances.items():
            if isinstance(entry, dict):
                allowances.append({
                    "name": entry.get("name", code),
                    "amount": quantize(Decimal(str(entry.get("amount", 0)))),
                    "is_taxable": entry.get("is_taxable", True),
                })
            else:
                allowances.append({
                    "name": code,
                    "amount": quantize(Decimal(str(entry))),
                    "is_taxable": True,
                })

        deductions = []
        for code, entry in raw_deductions.items():
            if isinstance(entry, dict):
                deductions.append({
                    "name": entry.get("name", code),
                    "amount": quantize(Decimal(str(entry.get("amount", 0)))),
                })
            else:
                deductions.append({
                    "name": code,
                    "amount": quantize(Decimal(str(entry))),
                })

        return {
            "employee": {
                "employee_number": record.employee.employee_number,
                "full_name": record.employee.full_name,
                "campus": record.employee.primary_campus.name if record.employee.primary_campus_id else "-",
                "designation": str(record.employee.designation) if record.employee.designation_id else "-",
            },
            "period": {
                "year": record.year,
                "month": record.month,
            },
            "earnings": {
                "basic": quantize(record.basic_salary),
                "allowances": allowances,
                "total_allowances": quantize(record.total_allowances),
                "gross": quantize(record.gross_salary),
            },
            "deductions": {
                "items": deductions,
                "total_deductions": quantize(record.total_deductions),
            },
            "net_salary": quantize(record.net_salary),
            "status": record.status,
            "generated_at": record.created_at,
        }


class PayrollSummaryReportView(AggregateReportView):
    """Payroll summary by period and campus."""

    permission_classes = [IsAccountantRole]
    report_definition_key = "payroll_summary_report"
    model = "apps.payroll.models.PayrollRecord"

    def get_base_queryset(self, request):
        from apps.payroll.models import PayrollRecord
        return PayrollRecord.objects.select_related(
            "employee", "employee__primary_campus", "salary_structure"
        )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = apply_campus_scope(queryset, request, "employee__primary_campus_id", institution_field=None)

        year = request.query_params.get("year")
        if year:
            queryset = queryset.filter(year=year)

        month = request.query_params.get("month")
        if month:
            queryset = queryset.filter(month=month)

        return queryset

    def get_summary(self, queryset, request):
        total_gross = sum(r.gross_salary for r in queryset)
        total_deductions = sum(r.total_deductions for r in queryset)
        total_net = sum(r.net_salary for r in queryset)

        periods = {}
        for record in queryset:
            period = f"{record.year}-{record.month:02d}"
            if period not in periods:
                periods[period] = {"gross": Decimal("0"), "deductions": Decimal("0"), "net": Decimal("0"), "count": 0}
            periods[period]["gross"] += record.gross_salary
            periods[period]["deductions"] += record.total_deductions
            periods[period]["net"] += record.net_salary
            periods[period]["count"] += 1

        return {
            "summary": {
                "total_gross": quantize(total_gross),
                "total_deductions": quantize(total_deductions),
                "total_net": quantize(total_net),
            },
            "by_period": [
                {
                    "period": k,
                    "employees": v["count"],
                    "gross": quantize(v["gross"]),
                    "deductions": quantize(v["deductions"]),
                    "net": quantize(v["net"]),
                }
                for k, v in sorted(periods.items(), reverse=True)
            ],
        }

    def get_detail_rows(self, queryset, request):
        return []


class AllowanceReportView(AggregateReportView):
    """Allowance breakdown report."""

    permission_classes = [IsAccountantRole]
    report_definition_key = "payroll_allowance"
    model = "apps.payroll.models.PayrollRecord"

    def get_base_queryset(self, request):
        from apps.payroll.models import PayrollRecord
        return PayrollRecord.objects.select_related(
            "employee", "employee__primary_campus", "salary_structure"
        )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = apply_campus_scope(queryset, request, "employee__primary_campus_id", institution_field=None)

        year = request.query_params.get("year")
        if year:
            queryset = queryset.filter(year=year)

        month = request.query_params.get("month")
        if month:
            queryset = queryset.filter(month=month)

        return queryset

    @staticmethod
    def _iter_allowances(records):
        aggregated = {}
        for record in records:
            details = record.component_details or {}
            for code, entry in (details.get("allowances") or {}).items():
                if isinstance(entry, dict):
                    name = entry.get("name", code)
                    amount = Decimal(str(entry.get("amount", 0)))
                else:
                    name = str(code)
                    amount = Decimal(str(entry))
                item = aggregated.setdefault(name, {"count": 0, "total": Decimal("0")})
                item["count"] += 1
                item["total"] += amount
        return aggregated

    def get_summary(self, queryset, request):
        allowances = self._iter_allowances(queryset)
        total = sum(v["total"] for v in allowances.values())
        return {
            "total_allowances": quantize(total),
            "allowance_types": len(allowances),
        }

    def get_detail_rows(self, queryset, request):
        allowances = self._iter_allowances(queryset)
        rows = [
            {"allowance": name, "count": v["count"], "total": quantize(v["total"])}
            for name, v in sorted(allowances.items(), key=lambda kv: kv[1]["total"], reverse=True)
        ]
        return rows


class DeductionReportView(AggregateReportView):
    """Deduction breakdown report."""

    permission_classes = [IsAccountantRole]
    report_definition_key = "payroll_deduction"
    model = "apps.payroll.models.PayrollRecord"

    def get_base_queryset(self, request):
        from apps.payroll.models import PayrollRecord
        return PayrollRecord.objects.select_related(
            "employee", "employee__primary_campus", "salary_structure"
        )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = apply_campus_scope(queryset, request, "employee__primary_campus_id", institution_field=None)

        year = request.query_params.get("year")
        if year:
            queryset = queryset.filter(year=year)

        month = request.query_params.get("month")
        if month:
            queryset = queryset.filter(month=month)

        return queryset

    @staticmethod
    def _iter_deductions(records):
        aggregated = {}
        for record in records:
            details = record.component_details or {}
            for code, entry in (details.get("deductions") or {}).items():
                if isinstance(entry, dict):
                    name = entry.get("name", code)
                    amount = Decimal(str(entry.get("amount", 0)))
                else:
                    name = str(code)
                    amount = Decimal(str(entry))
                item = aggregated.setdefault(name, {"count": 0, "total": Decimal("0")})
                item["count"] += 1
                item["total"] += amount
        return aggregated

    def get_summary(self, queryset, request):
        deductions = self._iter_deductions(queryset)
        total = sum(v["total"] for v in deductions.values())
        return {
            "total_deductions": quantize(total),
            "deduction_types": len(deductions),
        }

    def get_detail_rows(self, queryset, request):
        deductions = self._iter_deductions(queryset)
        rows = [
            {"deduction": name, "count": v["count"], "total": quantize(v["total"])}
            for name, v in sorted(deductions.items(), key=lambda kv: kv[1]["total"], reverse=True)
        ]
        return rows


class NetSalaryReportView(AggregateReportView):
    """Net salary report by campus/department."""

    permission_classes = [IsAccountantRole]
    report_definition_key = "payroll_net_salary"
    model = "apps.payroll.models.PayrollRecord"

    def get_base_queryset(self, request):
        from apps.payroll.models import PayrollRecord
        return PayrollRecord.objects.select_related(
            "employee", "employee__primary_campus"
        ).prefetch_related("employee__staff_profile", "employee__teacher")

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = apply_campus_scope(queryset, request, "employee__primary_campus_id", institution_field=None)

        year = request.query_params.get("year")
        if year:
            queryset = queryset.filter(year=year)

        month = request.query_params.get("month")
        if month:
            queryset = queryset.filter(month=month)

        return queryset

    def get_summary(self, queryset, request):
        total_net = sum(r.net_salary for r in queryset)

        by_campus = {}
        for record in queryset:
            campus = record.employee.primary_campus.name if record.employee.primary_campus_id else "-"
            if campus not in by_campus:
                by_campus[campus] = {"net": Decimal("0"), "count": 0}
            by_campus[campus]["net"] += record.net_salary
            by_campus[campus]["count"] += 1

        return {
            "total_net": quantize(total_net),
            "total_employees": queryset.count(),
            "by_campus": [
                {"campus": k, "employees": v["count"], "net": quantize(v["net"])}
                for k, v in sorted(by_campus.items())
            ],
        }

    def get_detail_rows(self, queryset, request):
        rows = []
        for record in queryset:
            rows.append({
                "employee_id": record.employee.employee_number,
                "employee": record.employee.full_name,
                "campus": record.employee.primary_campus.name if record.employee.primary_campus_id else "-",
                "year": record.year,
                "month": record.month,
                "net_salary": quantize(record.net_salary),
            })
        return rows


class PaidSalaryReportView(AggregateReportView):
    """Paid salary report."""

    permission_classes = [IsAccountantRole]
    report_definition_key = "payroll_paid"
    model = "apps.payroll.models.PayrollRecord"

    def get_base_queryset(self, request):
        from apps.payroll.models import PayrollRecord
        return PayrollRecord.objects.filter(status="paid").select_related(
            "employee", "employee__primary_campus"
        ).prefetch_related("employee__staff_profile", "employee__teacher")

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = apply_campus_scope(queryset, request, "employee__primary_campus_id", institution_field=None)

        year = request.query_params.get("year")
        if year:
            queryset = queryset.filter(year=year)

        month = request.query_params.get("month")
        if month:
            queryset = queryset.filter(month=month)

        return queryset

    def get_summary(self, queryset, request):
        total_net = sum(r.net_salary for r in queryset)

        return {
            "total_paid": quantize(total_net),
            "employees_paid": queryset.count(),
        }

    def get_detail_rows(self, queryset, request):
        rows = []
        for record in queryset:
            rows.append({
                "employee_id": record.employee.employee_number,
                "employee": record.employee.full_name,
                "campus": record.employee.primary_campus.name if record.employee.primary_campus_id else "-",
                "year": record.year,
                "month": record.month,
                "net_salary": quantize(record.net_salary),
                "paid_date": record.updated_at.date() if record.updated_at else "-",
            })
        return rows


class PendingSalaryReportView(PaidSalaryReportView):
    """Pending salary report."""
    report_definition_key = "payroll_pending"

    def get_base_queryset(self, request):
        from apps.payroll.models import PayrollRecord
        return PayrollRecord.objects.filter(status__in=["draft", "approved"]).select_related(
            "employee", "employee__primary_campus"
        ).prefetch_related("employee__staff_profile", "employee__teacher")

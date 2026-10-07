"""Fee and Finance Reports."""

from datetime import date
from decimal import Decimal
from django.db.models import Count, Q, Case, When, Value, IntegerField, Sum, Avg, Max, Min
from django.db.models.functions import TruncMonth, TruncWeek, TruncDay
from django.utils import timezone
from rest_framework.response import Response

from apps.accounts.access import apply_campus_scope
from apps.accounts.permissions import IsAccountantRole
from apps.reports.base_views import AggregateReportView, BaseReportView
from apps.reports.utils import quantize, to_csv


class FeeCollectionReportView(AggregateReportView):
    """Fee collection reports - daily, weekly, monthly."""

    permission_classes = [IsAccountantRole]
    report_definition_key = "fee_collection"
    model = "apps.finance.models.Payment"

    PERIOD_CHOICES = ["daily", "weekly", "monthly", "range"]

    def get_base_queryset(self, request):
        from apps.finance.models import Payment
        return Payment.objects.filter(status="completed").select_related(
            "invoice__enrollment__campus",
            "invoice__enrollment__class_obj",
            "invoice__enrollment__section",
            "invoice__student",
            "invoice__academic_year",
        )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = apply_campus_scope(queryset, request, "invoice__enrollment__campus_id")

        period = request.query_params.get("period", "monthly")
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")

        if period == "range" and date_from and date_to:
            queryset = queryset.filter(payment_date__gte=date_from, payment_date__lte=date_to)
        elif period == "monthly":
            month = request.query_params.get("month", str(timezone.now().month))
            year = request.query_params.get("year", str(timezone.now().year))
            queryset = queryset.filter(payment_date__year=year, payment_date__month=month)
        elif period == "weekly":
            week = request.query_params.get("week")
            year = request.query_params.get("year", str(timezone.now().year))
            if week:
                queryset = queryset.filter(payment_date__year=year, payment_date__week=week)
        elif period == "daily":
            day = request.query_params.get("date", str(timezone.now().date()))
            queryset = queryset.filter(payment_date=day)

        payment_method = request.query_params.get("payment_method")
        if payment_method:
            queryset = queryset.filter(payment_method=payment_method)

        class_obj = request.query_params.get("class")
        if class_obj:
            queryset = queryset.filter(invoice__enrollment__class_obj_id=class_obj)

        return queryset

    def get_summary(self, queryset, request):
        period = request.query_params.get("period", "monthly")

        total_collected = sum(p.net_amount for p in queryset)
        total_payments = queryset.count()

        by_method = queryset.values("payment_method").annotate(
            count=Count("id"),
            collected=Sum("net_amount"),
        )

        by_campus = queryset.values("invoice__enrollment__campus__name").annotate(
            count=Count("id"),
            collected=Sum("net_amount"),
        )

        by_class = queryset.values("invoice__enrollment__class_obj__name").annotate(
            count=Count("id"),
            collected=Sum("net_amount"),
        )

        return {
            "period": period,
            "total_collected": quantize(total_collected),
            "total_payments": total_payments,
            "by_method": [
                {"method": m["payment_method"], "count": m["count"], "collected": quantize(m["collected"])}
                for m in by_method
            ],
            "by_campus": [
                {"campus": c["invoice__enrollment__campus__name"], "count": c["count"], "collected": quantize(c["collected"])}
                for c in by_campus
            ],
            "by_class": [
                {"class": c["invoice__enrollment__class_obj__name"], "count": c["count"], "collected": quantize(c["collected"])}
                for c in by_class
            ],
        }

    def get_detail_rows(self, queryset, request):
        rows = []
        for payment in queryset:
            rows.append({
                "receipt_number": payment.receipt_number,
                "date": payment.payment_date,
                "student": payment.invoice.student.full_name,
                "admission_number": payment.invoice.student.admission_number,
                "campus": payment.invoice.enrollment.campus.name,
                "class": payment.invoice.enrollment.class_obj.name,
                "section": payment.invoice.enrollment.section.name if payment.invoice.enrollment.section else "-",
                "payment_method": payment.get_payment_method_display(),
                "amount": quantize(payment.amount),
                "discount": quantize(payment.discount),
                "net_amount": quantize(payment.net_amount),
                "reference": payment.reference,
            })
        return rows


class FeeStatusReportView(AggregateReportView):
    """Fee status reports - paid, unpaid, partial, overdue."""

    permission_classes = [IsAccountantRole]
    report_definition_key = "fee_status"
    model = "apps.finance.models.Invoice"

    STATUS_TYPES = ["paid", "unpaid", "partial", "overdue", "outstanding", "upcoming", "waived", "discounted", "refunded", "cancelled"]

    def get_base_queryset(self, request):
        from apps.finance.models import Invoice
        return Invoice.objects.select_related(
            "student", "enrollment__campus", "enrollment__class_obj", "enrollment__section", "academic_year"
        ).prefetch_related("items", "payments", "concessions")

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = apply_campus_scope(queryset, request, "enrollment__campus_id")

        status_type = request.query_params.get("status_type", "outstanding")

        if status_type == "paid":
            queryset = queryset.filter(status="paid")
        elif status_type == "unpaid":
            queryset = queryset.filter(status__in=["issued", "overdue"]).exclude(
                payments__status="completed"
            )
        elif status_type == "partial":
            queryset = queryset.filter(status="partial")
        elif status_type == "overdue":
            queryset = queryset.filter(status="overdue")
        elif status_type == "outstanding":
            queryset = queryset.filter(status__in=["issued", "partial", "overdue"])
        elif status_type == "upcoming":
            queryset = queryset.filter(status__in=["issued", "partial"], due_date__gte=timezone.now().date())
        elif status_type == "waived":
            queryset = queryset.filter(concessions__status="approved")
        elif status_type == "discounted":
            queryset = queryset.filter(discount__gt=0)
        elif status_type == "refunded":
            queryset = queryset.filter(payments__refunds__status="completed")
        elif status_type == "cancelled":
            queryset = queryset.filter(status="cancelled")

        student = request.query_params.get("student")
        if student:
            queryset = queryset.filter(student_id=student)

        class_obj = request.query_params.get("class")
        if class_obj:
            queryset = queryset.filter(enrollment__class_obj_id=class_obj)

        fee_type = request.query_params.get("fee_type")
        if fee_type:
            queryset = queryset.filter(items__category_id=fee_type)

        amount_min = request.query_params.get("amount_min")
        if amount_min:
            queryset = queryset.filter(total_amount__gte=amount_min)

        amount_max = request.query_params.get("amount_max")
        if amount_max:
            queryset = queryset.filter(total_amount__lte=amount_max)

        return queryset.distinct()

    def get_summary(self, queryset, request):
        total_invoiced = Decimal("0")
        total_collected = Decimal("0")
        total_outstanding = Decimal("0")
        total_discount = Decimal("0")

        for invoice in queryset:
            total_invoiced += invoice.total_amount
            total_collected += invoice.paid_amount
            total_outstanding += invoice.balance
            total_discount += invoice.discount

        return {
            "total_invoices": queryset.count(),
            "total_invoiced": quantize(total_invoiced),
            "total_collected": quantize(total_collected),
            "total_outstanding": quantize(total_outstanding),
            "total_discount": quantize(total_discount),
            "collection_rate": round(float(total_collected) / float(total_invoiced) * 100, 2) if total_invoiced else 0,
        }

    def get_detail_rows(self, queryset, request):
        rows = []
        for invoice in queryset:
            rows.append({
                "invoice_number": invoice.invoice_number,
                "date": invoice.issue_date,
                "due_date": invoice.due_date,
                "student": invoice.student.full_name,
                "admission_number": invoice.student.admission_number,
                "campus": invoice.enrollment.campus.name,
                "class": invoice.enrollment.class_obj.name,
                "section": invoice.enrollment.section.name if invoice.enrollment.section else "-",
                "status": invoice.get_status_display(),
                "total_amount": quantize(invoice.total_amount),
                "paid_amount": quantize(invoice.paid_amount),
                "balance": quantize(invoice.balance),
                "discount": quantize(invoice.discount),
            })
        return rows


class FeeAnalyticsReportView(AggregateReportView):
    """Fee analytics with trends and comparisons."""

    permission_classes = [IsAccountantRole]
    report_definition_key = "fee_analytics"
    model = "apps.finance.models.Invoice"

    def get_base_queryset(self, request):
        from apps.finance.models import Invoice
        return Invoice.objects.select_related(
            "enrollment__campus", "enrollment__class_obj", "academic_year"
        ).prefetch_related("items", "payments", "concessions")

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = apply_campus_scope(queryset, request, "enrollment__campus_id")

        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")

        if date_from:
            queryset = queryset.filter(issue_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(issue_date__lte=date_to)

        return queryset

    def get_summary(self, queryset, request):
        from apps.finance.models import Payment

        # Overall totals
        total_invoiced = sum(inv.total_amount for inv in queryset)
        total_collected = sum(inv.paid_amount for inv in queryset)
        total_outstanding = sum(inv.balance for inv in queryset)
        total_discount = sum(inv.discount for inv in queryset)

        # Monthly trend
        monthly = {}
        for inv in queryset:
            key = inv.issue_date.strftime("%Y-%m")
            if key not in monthly:
                monthly[key] = {"invoiced": Decimal("0"), "collected": Decimal("0"), "outstanding": Decimal("0")}
            monthly[key]["invoiced"] += inv.total_amount
            monthly[key]["collected"] += inv.paid_amount
            monthly[key]["outstanding"] += inv.balance

        monthly_trend = [
            {
                "month": k,
                "invoiced": quantize(v["invoiced"]),
                "collected": quantize(v["collected"]),
                "outstanding": quantize(v["outstanding"]),
            }
            for k, v in sorted(monthly.items())
        ]

        # Campus comparison
        campuses = {}
        for inv in queryset:
            campus = inv.enrollment.campus.name
            if campus not in campuses:
                campuses[campus] = {"invoiced": Decimal("0"), "collected": Decimal("0"), "outstanding": Decimal("0")}
            campuses[campus]["invoiced"] += inv.total_amount
            campuses[campus]["collected"] += inv.paid_amount
            campuses[campus]["outstanding"] += inv.balance

        campus_comparison = [
            {
                "campus": k,
                "invoiced": quantize(v["invoiced"]),
                "collected": quantize(v["collected"]),
                "outstanding": quantize(v["outstanding"]),
                "rate": round(float(v["collected"]) / float(v["invoiced"]) * 100, 2) if v["invoiced"] else 0,
            }
            for k, v in sorted(campuses.items())
        ]

        # Class comparison
        classes = {}
        for inv in queryset:
            cls = inv.enrollment.class_obj.name
            if cls not in classes:
                classes[cls] = {"invoiced": Decimal("0"), "collected": Decimal("0"), "outstanding": Decimal("0")}
            classes[cls]["invoiced"] += inv.total_amount
            classes[cls]["collected"] += inv.paid_amount
            classes[cls]["outstanding"] += inv.balance

        class_comparison = [
            {
                "class": k,
                "invoiced": quantize(v["invoiced"]),
                "collected": quantize(v["collected"]),
                "outstanding": quantize(v["outstanding"]),
                "rate": round(float(v["collected"]) / float(v["invoiced"]) * 100, 2) if v["invoiced"] else 0,
            }
            for k, v in sorted(classes.items())
        ]

        # Fee type comparison
        fee_types = {}
        for inv in queryset:
            for item in inv.items.all():
                cat = item.category.name
                if cat not in fee_types:
                    fee_types[cat] = {"invoiced": Decimal("0"), "collected": Decimal("0")}
                fee_types[cat]["invoiced"] += item.amount

        # Fee type collected (approximate - proportional)
        for inv in queryset:
            if inv.total_amount > 0:
                for item in inv.items.all():
                    cat = item.category.name
                    proportion = item.amount / inv.total_amount
                    fee_types[cat]["collected"] += inv.paid_amount * proportion

        fee_type_comparison = [
            {
                "category": k,
                "invoiced": quantize(v["invoiced"]),
                "collected": quantize(v["collected"]),
                "rate": round(float(v["collected"]) / float(v["invoiced"]) * 100, 2) if v["invoiced"] else 0,
            }
            for k, v in sorted(fee_types.items())
        ]

        # Payment method comparison
        payments = Payment.objects.filter(
            invoice__in=queryset, status="completed"
        ).select_related("invoice__enrollment__campus")

        methods = {}
        for p in payments:
            method = p.get_payment_method_display()
            if method not in methods:
                methods[method] = Decimal("0")
            methods[method] += p.net_amount

        method_comparison = [
            {"method": k, "collected": quantize(v)}
            for k, v in sorted(methods.items(), key=lambda x: x[1], reverse=True)
        ]

        return {
            "summary": {
                "total_invoiced": quantize(total_invoiced),
                "total_collected": quantize(total_collected),
                "total_outstanding": quantize(total_outstanding),
                "total_discount": quantize(total_discount),
                "collection_rate": round(float(total_collected) / float(total_invoiced) * 100, 2) if total_invoiced else 0,
            },
            "monthly_trend": monthly_trend,
            "campus_comparison": campus_comparison,
            "class_comparison": class_comparison,
            "fee_type_comparison": fee_type_comparison,
            "payment_method_comparison": method_comparison,
        }

    def get_detail_rows(self, queryset, request):
        return []


class FinanceReportView(AggregateReportView):
    """Finance/Accounting reports - income, expense, P&L, cash flow."""

    permission_classes = [IsAccountantRole]
    report_definition_key = "finance_income"
    model = "apps.finance.models.JournalEntry"

    REPORT_TYPES = ["income", "expense", "pl", "cashflow", "ledger"]

    def get_base_queryset(self, request):
        from apps.finance.models import JournalEntry
        return JournalEntry.objects.filter(status="posted").select_related(
            "campus", "created_by"
        ).prefetch_related("lines__account")

    def get_queryset(self, request):
        queryset = apply_campus_scope(self.get_base_queryset(request), request, "campus_id")

        report_type = request.query_params.get("report_type", "income")
        self.report_type = report_type

        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")

        if date_from:
            queryset = queryset.filter(posting_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(posting_date__lte=date_to)

        campus = request.query_params.get("campus")
        if campus:
            queryset = queryset.filter(campus_id=campus)

        return queryset

    def get_summary(self, queryset, request):
        report_type = getattr(self, "report_type", "income")

        if report_type == "income":
            return self.get_income_summary(queryset)
        elif report_type == "expense":
            return self.get_expense_summary(queryset)
        elif report_type == "pl":
            return self.get_pl_summary(queryset)
        elif report_type == "cashflow":
            return self.get_cashflow_summary(queryset)
        elif report_type == "ledger":
            return self.get_ledger_summary(queryset)

        return {}

    def get_income_summary(self, queryset):
        from apps.finance.models import Account
        income_accounts = Account.objects.filter(account_type="income")

        totals = {}
        for entry in queryset:
            for line in entry.lines.filter(account__account_type="income"):
                acc = line.account.name
                if acc not in totals:
                    totals[acc] = Decimal("0")
                totals[acc] += line.credit - line.debit

        return {
            "total_income": quantize(sum(totals.values())),
            "by_account": [{"account": k, "amount": quantize(v)} for k, v in totals.items()],
        }

    def get_expense_summary(self, queryset):
        from apps.finance.models import Account
        expense_accounts = Account.objects.filter(account_type="expense")

        totals = {}
        for entry in queryset:
            for line in entry.lines.filter(account__account_type="expense"):
                acc = line.account.name
                if acc not in totals:
                    totals[acc] = Decimal("0")
                totals[acc] += line.debit - line.credit

        return {
            "total_expense": quantize(sum(totals.values())),
            "by_account": [{"account": k, "amount": quantize(v)} for k, v in totals.items()],
        }

    def get_pl_summary(self, queryset):
        income = Decimal("0")
        expense = Decimal("0")

        for entry in queryset:
            for line in entry.lines.all():
                if line.account.account_type == "income":
                    income += line.credit - line.debit
                elif line.account.account_type == "expense":
                    expense += line.debit - line.credit

        return {
            "total_income": quantize(income),
            "total_expense": quantize(expense),
            "net_profit": quantize(income - expense),
        }

    def get_cashflow_summary(self, queryset):
        # Simplified cash flow from journal entries
        operating = Decimal("0")
        investing = Decimal("0")
        financing = Decimal("0")

        for entry in queryset:
            for line in entry.lines.all():
                if line.account.account_type == "asset":
                    if line.debit > 0:
                        investing += line.debit
                    else:
                        investing -= line.credit
                elif line.account.account_type == "liability":
                    if line.credit > 0:
                        financing += line.credit
                    else:
                        financing -= line.debit
                elif line.account.account_type == "equity":
                    financing += line.credit - line.debit
                else:
                    operating += line.credit - line.debit

        return {
            "operating_cashflow": quantize(operating),
            "investing_cashflow": quantize(investing),
            "financing_cashflow": quantize(financing),
            "net_cashflow": quantize(operating + investing + financing),
        }

    def get_ledger_summary(self, queryset):
        from apps.finance.models import Account

        accounts = Account.objects.filter(is_active=True)
        ledger = []

        for account in accounts:
            debit_total = Decimal("0")
            credit_total = Decimal("0")

            for entry in queryset:
                for line in entry.lines.filter(account=account):
                    debit_total += line.debit
                    credit_total += line.credit

            if debit_total > 0 or credit_total > 0:
                balance = debit_total - credit_total
                ledger.append({
                    "code": account.code,
                    "name": account.name,
                    "type": account.account_type,
                    "debit": quantize(debit_total),
                    "credit": quantize(credit_total),
                    "balance": quantize(balance),
                })

        return {
            "accounts": ledger,
            "total_accounts": len(ledger),
        }

    def get_detail_rows(self, queryset, request):
        return []


class FeeDefaultersReportView(AggregateReportView):
    """Students with outstanding balances."""

    permission_classes = [IsAccountantRole]
    report_definition_key = "fee_defaulters"
    model = "apps.finance.models.Invoice"

    def get_base_queryset(self, request):
        from apps.finance.models import Invoice
        return Invoice.objects.filter(
            status__in=["issued", "partial", "overdue"]
        ).prefetch_related(
            "items", "payments", "concessions"
        ).select_related(
            "student", "enrollment__campus", "academic_year"
        )

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        queryset = apply_campus_scope(queryset, request, "enrollment__campus_id", "institution")

        academic_year = request.query_params.get("academic_year")
        if academic_year:
            queryset = queryset.filter(academic_year_id=academic_year)

        return queryset

    def get_summary(self, queryset, request):
        students = {}

        for invoice in queryset:
            balance = invoice.balance
            if balance <= 0:
                continue

            student_id = invoice.student_id
            if student_id not in students:
                students[student_id] = {
                    "student": invoice.student,
                    "campus": invoice.enrollment.campus.name if invoice.enrollment.campus else "-",
                    "total_invoiced": Decimal("0"),
                    "total_paid": Decimal("0"),
                    "total_outstanding": Decimal("0"),
                    "invoice_count": 0,
                }

            students[student_id]["total_invoiced"] += invoice.total_amount
            students[student_id]["total_paid"] += invoice.paid_amount
            students[student_id]["total_outstanding"] += balance
            students[student_id]["invoice_count"] += 1

        rows = sorted(
            students.values(),
            key=lambda x: x["total_outstanding"],
            reverse=True
        )

        total_outstanding = sum(r["total_outstanding"] for r in rows)

        row_limit = int(request.query_params.get("limit", 500))
        shown = rows[:row_limit] if row_limit else rows

        return {
            "total_defaulters": len(rows),
            "total_outstanding": quantize(total_outstanding),
            "row_limit": row_limit,
            "rows_truncated": bool(row_limit) and len(rows) > row_limit,
        }

    def get_detail_rows(self, queryset, request):
        students = {}

        for invoice in queryset:
            balance = invoice.balance
            if balance <= 0:
                continue

            student_id = invoice.student_id
            if student_id not in students:
                students[student_id] = {
                    "student": invoice.student,
                    "campus": invoice.enrollment.campus.name if invoice.enrollment.campus else "-",
                    "total_invoiced": Decimal("0"),
                    "total_paid": Decimal("0"),
                    "total_outstanding": Decimal("0"),
                    "invoice_count": 0,
                }

            students[student_id]["total_invoiced"] += invoice.total_amount
            students[student_id]["total_paid"] += invoice.paid_amount
            students[student_id]["total_outstanding"] += balance
            students[student_id]["invoice_count"] += 1

        rows = sorted(
            students.values(),
            key=lambda x: x["total_outstanding"],
            reverse=True
        )

        row_limit = int(request.query_params.get("limit", 500))
        shown = rows[:row_limit] if row_limit else rows

        result = []
        for row in shown:
            result.append({
                "admission_number": row["student"].admission_number,
                "student": row["student"].full_name,
                "campus": row["campus"],
                "invoices": row["invoice_count"],
                "total_invoiced": quantize(row["total_invoiced"]),
                "total_paid": quantize(row["total_paid"]),
                "total_outstanding": quantize(row["total_outstanding"]),
            })
        return result

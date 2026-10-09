from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics, serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.access import apply_campus_scope
from apps.accounts.permissions import (
    IsAccountantRole,
    IsFinanceReaderRole,
)
from apps.accounts.scopes import (
    get_student_profile,
    is_manager,
    is_parent,
    is_student,
    parent_student_ids,
)
from apps.audit.models import record_audit

from .models import (
    FeeCategory,
    FeeStructure,
    Invoice,
    InvoiceItem,
    Payment,
    PaymentReversal,
    Account,
    JournalEntry,
    JournalLine,
    Expense,
    Concession,
    PaymentRefund,
    StudentFeeOverride,
    Fine,
    Adjustment,
    BankAccount,
    BankReconciliation,
    Budget,
    BudgetLine,
)
from .pdf import payment_receipt_pdf
from .serializers import (
    FeeCategorySerializer,
    FeeStructureSerializer,
    InvoiceCreateSerializer,
    InvoiceSerializer,
    PaymentCreateSerializer,
    PaymentReversalSerializer,
    PaymentSerializer,
    AccountSerializer,
    JournalEntrySerializer,
    JournalEntryCreateSerializer,
    JournalEntryPostSerializer,
    JournalEntryVoidSerializer,
    ExpenseSerializer,
    ConcessionSerializer,
    PaymentRefundSerializer,
    StudentFeeOverrideSerializer,
    LateFeeApplySerializer,
    LateFeeResultSerializer,
    FineSerializer,
    FineApproveSerializer,
    FineWaiveSerializer,
    AdjustmentSerializer,
    AdjustmentApplySerializer,
    BankAccountSerializer,
    BankReconciliationSerializer,
    BankReconciliationCreateSerializer,
    BudgetSerializer,
    BudgetLineSerializer,
    BudgetApproveSerializer,
    BudgetCloseSerializer,
)
from .services import FeeInvoiceService, PaymentService, JournalService


def institution_filter(queryset, request):
    return queryset.filter(institution=getattr(request, "institution", None))


def scoped_invoice_queryset(request):
    queryset = Invoice.objects.filter(
        academic_year__school=getattr(request, "institution", None),
    )
    return apply_campus_scope(queryset, request, "enrollment__campus_id")


class AccountListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = AccountSerializer

    def get_queryset(self):
        queryset = institution_filter(Account.objects.select_related("parent"), self.request)
        active = self.request.query_params.get("active")
        if active is not None:
            queryset = queryset.filter(is_active=active.lower() == "true")
        return queryset

    def perform_create(self, serializer):
        serializer.save(institution=self.request.institution)


class JournalEntryListView(generics.ListAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = JournalEntrySerializer

    def get_queryset(self):
        queryset = institution_filter(
            JournalEntry.objects.prefetch_related("lines__account").order_by("-posting_date", "-id"),
            self.request,
        )
        return apply_campus_scope(queryset, self.request, "campus_id")


class ExpenseListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = ExpenseSerializer

    def get_queryset(self):
        queryset = institution_filter(
            Expense.objects.select_related("campus", "expense_account", "payment_account"),
            self.request,
        )
        return apply_campus_scope(queryset, self.request, "campus_id")

    def perform_create(self, serializer):
        campus = serializer.validated_data.get("campus")
        if campus:
            from apps.accounts.access import assert_campus_allowed
            assert_campus_allowed(self.request.user, campus.pk, request=self.request)
        for field in ("expense_account", "payment_account"):
            account = serializer.validated_data.get(field)
            if account is not None and account.institution_id != self.request.institution.id:
                raise PermissionDenied(
                    f"{field} does not belong to the active institution."
                )
        serializer.save(institution=self.request.institution, created_by=self.request.user)


class ExpensePostView(APIView):
    permission_classes = [IsAccountantRole]

    @transaction.atomic
    def post(self, request, pk):
        expense = get_object_or_404(
            institution_filter(Expense.objects.select_related("campus", "expense_account", "payment_account"), request),
            pk=pk,
        )
        if expense.campus_id:
            from apps.accounts.access import assert_campus_allowed
            assert_campus_allowed(request.user, expense.campus_id, request=request)
        if expense.status == "cancelled":
            return Response({"detail": "Cancelled expenses cannot be posted."}, status=400)
        if expense.journal_entry_id:
            return Response(ExpenseSerializer(expense).data)
        entry = JournalEntry.objects.create(
            institution=expense.institution,
            campus=expense.campus,
            posting_date=expense.expense_date,
            description=f"Expense: {expense.vendor or expense.reference or expense.id}",
            source_type="expense",
            source_id=str(expense.pk),
            created_by=request.user,
        )
        JournalLine.objects.create(entry=entry, account=expense.expense_account, debit=expense.amount, memo=expense.notes)
        JournalLine.objects.create(entry=entry, account=expense.payment_account, credit=expense.amount, memo=expense.reference)
        expense.journal_entry = entry
        expense.status = "paid"
        expense.save(update_fields=["journal_entry", "status", "updated_at"])
        record_audit(request=request, action="expense_posted", model_name="Expense", object_id=str(expense.pk), object_repr=str(expense), details={"amount": str(expense.amount)})
        return Response(ExpenseSerializer(expense).data)


class ConcessionListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = ConcessionSerializer

    def get_queryset(self):
        return Concession.objects.filter(
            invoice__in=scoped_invoice_queryset(self.request),
        ).select_related("invoice")

    def perform_create(self, serializer):
        invoice = serializer.validated_data["invoice"]
        if not scoped_invoice_queryset(self.request).filter(pk=invoice.pk).exists():
            raise PermissionDenied(
                "You cannot create a concession outside your institution or campus."
            )
        serializer.save()


class ConcessionApproveView(APIView):
    permission_classes = [IsAccountantRole]

    @transaction.atomic
    def post(self, request, pk):
        concession = get_object_or_404(
            Concession.objects.select_related("invoice__enrollment"),
            pk=pk,
            invoice__in=scoped_invoice_queryset(request),
        )
        if concession.status != "pending":
            return Response({"detail": "Only pending concessions can be approved."}, status=400)
        from django.utils import timezone
        concession.status = "approved"
        concession.approved_by = request.user
        concession.approved_at = timezone.now()
        concession.save(update_fields=["status", "approved_by", "approved_at"])
        concession.invoice.refresh_status()
        record_audit(request=request, action="concession_approved", model_name="Concession", object_id=str(pk), object_repr=str(concession), details={"amount": str(concession.amount)})
        return Response(ConcessionSerializer(concession).data)


class PaymentRefundCreateView(generics.CreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = PaymentRefundSerializer

    def perform_create(self, serializer):
        payment = serializer.validated_data["payment"]
        invoice = payment.invoice
        if not scoped_invoice_queryset(self.request).filter(pk=invoice.pk).exists():
            raise PermissionDenied("You cannot refund a payment outside your institution or campus.")
        refund = serializer.save(created_by=self.request.user)
        record_audit(request=self.request, action="payment_refund", model_name="PaymentRefund", object_id=str(refund.pk), object_repr=str(refund), details={"amount": str(refund.amount), "payment": payment.receipt_number})


class TrialBalanceReportView(APIView):
    permission_classes = [IsAccountantRole]

    def get(self, request):
        rows = []
        entries = JournalEntry.objects.filter(institution=request.institution, status="posted")
        entries = apply_campus_scope(entries, request, "campus_id")
        lines = JournalLine.objects.filter(entry__in=entries).values("account_id", "account__code", "account__name").annotate(debit=Sum("debit"), credit=Sum("credit")).order_by("account__code")
        for line in lines:
            rows.append({"account": line["account__name"], "code": line["account__code"], "debit": str(line["debit"] or Decimal("0.00")), "credit": str(line["credit"] or Decimal("0.00"))})
        return Response({"rows": rows})


class IncomeExpenseReportView(APIView):
    permission_classes = [IsAccountantRole]

    def get(self, request):
        entries = apply_campus_scope(JournalEntry.objects.filter(institution=request.institution, status="posted"), request, "campus_id")
        lines = JournalLine.objects.filter(entry__in=entries).values("account__account_type").annotate(debit=Sum("debit"), credit=Sum("credit"))
        income = Decimal("0.00")
        expense = Decimal("0.00")
        for line in lines:
            if line["account__account_type"] == "income":
                income += (line["credit"] or 0) - (line["debit"] or 0)
            elif line["account__account_type"] == "expense":
                expense += (line["debit"] or 0) - (line["credit"] or 0)
        return Response({"income": str(income), "expense": str(expense), "net": str(income - expense)})


class ReceivablesReportView(APIView):
    permission_classes = [IsAccountantRole]

    def get(self, request):
        today = date.today()
        invoices = (
            scoped_invoice_queryset(request)
            .select_related("student")
            .prefetch_related(
                "items",
                "concessions",
                "payments__refunds",
                "payments__reversals",
            )
        )
        rows = [{"invoice": invoice.invoice_number, "student": invoice.student.full_name, "balance": str(invoice.balance)} for invoice in invoices if invoice.balance > 0]
        total = sum((Decimal(row["balance"]) for row in rows), Decimal("0.00"))

        # AR aging buckets keyed off the invoice due date.
        aging = {
            "current": Decimal("0.00"),       # not yet due or due within 30 days
            "31_60": Decimal("0.00"),
            "61_90": Decimal("0.00"),
            "90_plus": Decimal("0.00"),
        }
        for invoice in invoices:
            if invoice.balance <= 0:
                continue
            days_overdue = (today - invoice.due_date).days
            balance = Decimal(invoice.balance)
            if days_overdue <= 30:
                aging["current"] += balance
            elif days_overdue <= 60:
                aging["31_60"] += balance
            elif days_overdue <= 90:
                aging["61_90"] += balance
            else:
                aging["90_plus"] += balance

        overdue_total = aging["31_60"] + aging["61_90"] + aging["90_plus"]

        return Response({
            "rows": rows,
            "total": str(total),
            "aging": {
                "current": str(aging["current"]),
                "31_60": str(aging["31_60"]),
                "61_90": str(aging["61_90"]),
                "90_plus": str(aging["90_plus"]),
            },
            "overdue_total": str(overdue_total),
            "as_of": today.isoformat(),
        })


class InvoiceListView(generics.ListAPIView):
    serializer_class = InvoiceSerializer
    permission_classes = [IsFinanceReaderRole]

    def get_queryset(self):
        queryset = (
            Invoice.objects
            .select_related(
                "student",
                "enrollment__campus",
                "enrollment__class_obj",
                "academic_year",
            )
            .prefetch_related(
                "items__category",
                "payments__refunds",
                "payments__reversals",
                "concessions",
            )
            .order_by("-issue_date", "-id")
        )
        queryset = queryset.filter(
            academic_year__school=self.request.institution
        )
        queryset = apply_campus_scope(queryset, self.request, "enrollment__campus_id")

        user = self.request.user

        if not is_manager(user):
            if is_parent(user):
                student_ids = parent_student_ids(user)

                if not student_ids:
                    return queryset.none()

                queryset = queryset.filter(student_id__in=student_ids)
            elif is_student(user):
                profile = get_student_profile(user)

                if profile is None:
                    return queryset.none()

                queryset = queryset.filter(student=profile)

        search = self.request.query_params.get("search")

        if search:
            queryset = queryset.filter(
                Q(invoice_number__icontains=search)
                | Q(student__first_name__icontains=search)
                | Q(student__middle_name__icontains=search)
                | Q(student__last_name__icontains=search)
                | Q(student__admission_number__icontains=search)
            )

        status = self.request.query_params.get("status")

        if status:
            queryset = queryset.filter(status=status)

        return queryset


class PaymentListView(generics.ListAPIView):
    serializer_class = PaymentSerializer
    permission_classes = [IsFinanceReaderRole]

    def get_queryset(self):
        queryset = (
            Payment.objects
            .select_related(
                "invoice",
                "invoice__student",
            )
            .order_by("-payment_date", "-id")
        )
        queryset = queryset.filter(
            invoice__academic_year__school=self.request.institution
        )
        queryset = apply_campus_scope(queryset, self.request, "invoice__enrollment__campus_id")

        user = self.request.user

        if not is_manager(user):
            if is_parent(user):
                student_ids = parent_student_ids(user)

                if not student_ids:
                    return queryset.none()

                queryset = queryset.filter(
                    invoice__student_id__in=student_ids
                )
            elif is_student(user):
                profile = get_student_profile(user)

                if profile is None:
                    return queryset.none()

                queryset = queryset.filter(invoice__student=profile)

        search = self.request.query_params.get("search")

        if search:
            queryset = queryset.filter(
                Q(receipt_number__icontains=search)
                | Q(invoice__invoice_number__icontains=search)
                | Q(invoice__student__first_name__icontains=search)
                | Q(invoice__student__last_name__icontains=search)
                | Q(invoice__student__admission_number__icontains=search)
            )

        status = self.request.query_params.get("status")

        if status:
            queryset = queryset.filter(status=status)

        payment_method = self.request.query_params.get("payment_method")

        if payment_method:
            queryset = queryset.filter(payment_method=payment_method)

        return queryset


class FeeCategoryListView(generics.ListCreateAPIView):
    serializer_class = FeeCategorySerializer
    permission_classes = [IsAccountantRole]
    pagination_class = None

    def get_queryset(self):
        queryset = FeeCategory.objects.filter(
            institution=self.request.institution
        ).order_by("name")

        status = self.request.query_params.get("status")

        if status:
            queryset = queryset.filter(status=status)

        return queryset

    def perform_create(self, serializer):
        from django.db import IntegrityError, transaction

        institution = getattr(self.request, "institution", None)
        if institution is None:
            raise serializers.ValidationError({"institution": "Select a school before creating a fee category."})
        try:
            with transaction.atomic():
                serializer.save(institution=institution)
        except IntegrityError:
            raise serializers.ValidationError({"name": "A fee category with this name already exists in this school."})


class FeeStructureListView(generics.ListCreateAPIView):
    serializer_class = FeeStructureSerializer
    permission_classes = [IsAccountantRole]
    pagination_class = None

    def get_queryset(self):
        queryset = (
            FeeStructure.objects
            .select_related(
                "academic_year",
                "campus",
                "class_obj__unit__campus",
                "category",
            )
            .order_by("campus", "class_obj", "category")
        )

        params = self.request.query_params

        if params.get("academic_year"):
            queryset = queryset.filter(
                academic_year_id=params.get("academic_year")
            )

        queryset = apply_campus_scope(
            queryset,
            self.request,
            "campus_id",
        )

        if params.get("class_obj"):
            queryset = queryset.filter(class_obj_id=params.get("class_obj"))

        if params.get("category"):
            queryset = queryset.filter(category_id=params.get("category"))

        status = params.get("status")

        if status:
            queryset = queryset.filter(status=status)

        return queryset


class FeeStructureDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = FeeStructureSerializer
    permission_classes = [IsAccountantRole]

    def get_queryset(self):
        queryset = FeeStructure.objects.filter(
            academic_year__school=self.request.institution
        ).select_related(
            "academic_year",
            "campus",
            "class_obj__unit__campus",
            "category",
        )
        return apply_campus_scope(queryset, self.request, "campus_id")


class InvoiceDetailView(generics.RetrieveAPIView):
    serializer_class = InvoiceSerializer
    permission_classes = [IsFinanceReaderRole]

    def get_queryset(self):
        queryset = Invoice.objects.select_related(
            "student",
            "enrollment__campus",
            "enrollment__class_obj",
            "enrollment__section",
            "academic_year",
        ).prefetch_related("items__category", "payments")
        queryset = queryset.filter(
            academic_year__school=self.request.institution
        )
        queryset = apply_campus_scope(queryset, self.request, "enrollment__campus_id")

        user = self.request.user

        if not is_manager(user):
            if is_parent(user):
                student_ids = parent_student_ids(user)

                if not student_ids:
                    return queryset.none()

                queryset = queryset.filter(
                    student_id__in=student_ids
                )
            elif is_student(user):
                profile = get_student_profile(user)

                if profile is None:
                    return queryset.none()

                queryset = queryset.filter(student=profile)

        return queryset


class InvoiceCreateView(generics.CreateAPIView):
    serializer_class = InvoiceCreateSerializer
    permission_classes = [IsAccountantRole]

    def perform_create(self, serializer):
        enrollment = serializer.validated_data["enrollment"]
        if enrollment.academic_year.school_id != self.request.institution.id:
            raise PermissionDenied("Enrollment is outside the active institution.")
        from apps.accounts.access import assert_campus_allowed
        assert_campus_allowed(self.request.user, enrollment.campus_id, request=self.request)
        invoice = serializer.save()

        record_audit(
            request=self.request,
            action="invoice",
            model_name="Invoice",
            object_id=str(invoice.pk),
            object_repr=str(invoice),
            details={
                "invoice_number": invoice.invoice_number,
                "total": str(invoice.total_amount),
            },
        )


class PaymentDetailView(generics.RetrieveAPIView):
    serializer_class = PaymentSerializer
    permission_classes = [IsFinanceReaderRole]

    def get_queryset(self):
        queryset = Payment.objects.select_related(
            "invoice",
            "invoice__student",
            "invoice__enrollment__class_obj",
            "invoice__enrollment__section",
            "invoice__academic_year",
        ).prefetch_related("invoice__items__category")
        queryset = queryset.filter(
            invoice__academic_year__school=self.request.institution
        )
        queryset = apply_campus_scope(queryset, self.request, "invoice__enrollment__campus_id")

        user = self.request.user

        if not is_manager(user):
            if is_parent(user):
                student_ids = parent_student_ids(user)

                if not student_ids:
                    return queryset.none()

                queryset = queryset.filter(
                    invoice__student_id__in=student_ids
                )
            elif is_student(user):
                profile = get_student_profile(user)

                if profile is None:
                    return queryset.none()

                queryset = queryset.filter(invoice__student=profile)

        return queryset


class PaymentCreateView(generics.CreateAPIView):
    serializer_class = PaymentCreateSerializer
    permission_classes = [IsAccountantRole]

    def perform_create(self, serializer):
        invoice = serializer.validated_data["invoice"]
        if invoice.academic_year.school_id != self.request.institution.id:
            raise PermissionDenied("Invoice is outside the active institution.")
        from apps.accounts.access import assert_campus_allowed
        assert_campus_allowed(self.request.user, invoice.enrollment.campus_id, request=self.request)
        payment = serializer.save()

        record_audit(
            request=self.request,
            action="payment",
            model_name="Payment",
            object_id=str(payment.pk),
            object_repr=str(payment),
            details={
                "receipt_number": payment.receipt_number,
                "invoice": payment.invoice.invoice_number,
                "amount": str(payment.amount),
            },
        )


class PaymentReversalCreateView(generics.CreateAPIView):
    serializer_class = PaymentReversalSerializer
    permission_classes = [IsAccountantRole]

    def perform_create(self, serializer):
        payment = serializer.validated_data["payment"]
        if not scoped_invoice_queryset(self.request).filter(
            pk=payment.invoice_id
        ).exists():
            raise PermissionDenied(
                "You cannot reverse a payment outside your institution or campus."
            )
        reversal = serializer.save(created_by=self.request.user)
        record_audit(request=self.request, action="payment_reversal", model_name="PaymentReversal", object_id=str(reversal.pk), object_repr=str(reversal.payment), details={"amount": str(reversal.amount), "payment": reversal.payment.receipt_number})


class PaymentReceiptHTMLView(APIView):
    """Printable HTML receipt for a single payment."""

    permission_classes = [IsFinanceReaderRole]

    def get_object(self):
        payment = (
            Payment.objects
            .filter(
                pk=self.kwargs["pk"],
                invoice__academic_year__school=self.request.institution,
            )
            .select_related(
                "invoice",
                "invoice__student",
                "invoice__enrollment__class_obj",
                "invoice__enrollment__section",
                "invoice__academic_year",
            )
            .prefetch_related("invoice__items__category")
            .first()
        )

        if payment is None:
            return None

        user = self.request.user
        from apps.accounts.access import assert_campus_allowed
        assert_campus_allowed(user, payment.invoice.enrollment.campus_id, request=self.request)

        if not is_manager(user):
            if is_parent(user):
                student_ids = parent_student_ids(user)

                if payment.invoice.student_id not in student_ids:
                    raise PermissionDenied(
                        "You cannot view this receipt."
                    )
            elif is_student(user):
                profile = get_student_profile(user)

                if (
                    profile is None
                    or payment.invoice.student_id != profile.pk
                ):
                    raise PermissionDenied(
                        "You cannot view this receipt."
                    )

        return payment

    def get(self, request, pk):
        payment = self.get_object()

        if payment is None:
            return Response(
                {"detail": "Not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        invoice = payment.invoice
        items = "".join(
            f"""
            <tr>
              <td>{item.description}</td>
              <td class="right">Rs. {item.amount:,.2f}</td>
            </tr>
            """
            for item in invoice.items.all()
        )

        if invoice.discount:
            items += (
                f"""
                <tr>
                  <td>Discount</td>
                  <td class="right">- Rs. {invoice.discount:,.2f}</td>
                </tr>
                """
            )

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Receipt {payment.receipt_number}</title>
<style>
  body {{ font-family: Arial, sans-serif; color: #111; margin: 24px; }}
  h1 {{ text-align: center; margin-bottom: 2px; }}
  h2 {{ text-align: center; font-size: 13px; color: #555; margin-top: 0; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 14px; }}
  td, th {{ padding: 6px 8px; border: 1px solid #ccc; font-size: 13px; }}
  th {{ background: #f2f4f7; text-align: left; }}
  .right {{ text-align: right; }}
  .meta td {{ border: none; padding: 2px 8px; }}
  .title-row td {{ font-weight: bold; }}
  @media print {{ body {{ margin: 0; }} }}
</style>
</head>
<body>
  <h1>School</h1>
  <h2>Official Payment Receipt</h2>

  <table class="meta">
    <tr>
      <td><strong>Receipt No.</strong> {payment.receipt_number}</td>
      <td class="right"><strong>Date</strong> {payment.payment_date}</td>
    </tr>
    <tr>
      <td><strong>Invoice No.</strong> {invoice.invoice_number}</td>
      <td class="right"><strong>Method</strong> {payment.get_payment_method_display()}</td>
    </tr>
    <tr>
      <td><strong>Student</strong> {invoice.student.full_name}</td>
      <td class="right"><strong>Admission No.</strong> {invoice.student.admission_number}</td>
    </tr>
    <tr>
      <td><strong>Class</strong> {invoice.enrollment.class_obj.name} - {invoice.enrollment.section.name}</td>
      <td class="right"><strong>Year</strong> {invoice.academic_year.name}</td>
    </tr>
  </table>

  <table>
    <tr><th>Description</th><th class="right">Amount</th></tr>
    {items}
    <tr class="title-row">
      <td>Invoice Total</td>
      <td class="right">Rs. {invoice.total_amount:,.2f}</td>
    </tr>
    <tr>
      <td>Amount Paid</td>
      <td class="right">Rs. {payment.amount:,.2f}</td>
    </tr>
    <tr class="title-row">
      <td>Balance Due</td>
      <td class="right">Rs. {invoice.balance:,.2f}</td>
    </tr>
  </table>

  <p style="font-size: 11px; color: #777; margin-top: 18px;">
    This is a computer-generated receipt. Reference: {payment.reference or "—"}
  </p>
</body>
</html>"""

        return HttpResponse(html)


class PaymentReceiptPDFView(APIView):
    """Download a PDF receipt for a single payment."""

    permission_classes = [IsFinanceReaderRole]

    def get(self, request, pk):
        payment = (
            Payment.objects
            .filter(
                pk=pk,
                invoice__academic_year__school=request.institution,
            )
            .select_related(
                "invoice",
                "invoice__student",
                "invoice__enrollment__class_obj",
                "invoice__enrollment__section",
                "invoice__academic_year",
            )
            .prefetch_related("invoice__items__category")
            .first()
        )

        if payment is None:
            return Response(
                {"detail": "Not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        user = request.user
        from apps.accounts.access import assert_campus_allowed
        assert_campus_allowed(user, payment.invoice.enrollment.campus_id, request=request)

        if not is_manager(user):
            if is_parent(user):
                student_ids = parent_student_ids(user)

                if payment.invoice.student_id not in student_ids:
                    raise PermissionDenied(
                        "You cannot view this receipt."
                    )
            elif is_student(user):
                profile = get_student_profile(user)

                if (
                    profile is None
                    or payment.invoice.student_id != profile.pk
                ):
                    raise PermissionDenied(
                        "You cannot view this receipt."
                    )

        record_audit(
            request=request,
            action="export",
            model_name="Payment",
            object_id=str(payment.pk),
            object_repr=str(payment),
            details={"format": "pdf"},
        )

        response = HttpResponse(
            payment_receipt_pdf(payment),
            content_type="application/pdf",
        )

        response[
            "Content-Disposition"
        ] = f'attachment; filename="receipt-{payment.receipt_number}.pdf"'

        return response


class BulkInvoiceCreateView(APIView):
    """Create invoices for all active enrollments matching the given filters.

    POST body:
        academic_year (int, required)
        campus (int, required)
        class_obj (int, required)
        category (int, required)  — fee category id
        due_date (str, optional)  — defaults to today
        notes (str, optional)
        skip_existing (bool, optional, default true) — skip enrollments that already
            have an issued/partial/paid invoice for this category in the same year
    """

    permission_classes = [IsAccountantRole]

    @transaction.atomic
    def post(self, request):
        from datetime import date as _date
        from django.core.exceptions import ValidationError as ModelValidationError
        from apps.students.models import Enrollment
        from apps.accounts.access import assert_campus_allowed
        from .services import next_invoice_number

        academic_year_id = request.data.get("academic_year")
        campus_id = request.data.get("campus")
        class_obj_id = request.data.get("class_obj")
        category_id = request.data.get("category")
        due_date_str = request.data.get("due_date")
        notes = request.data.get("notes", "")
        skip_existing = request.data.get("skip_existing", True)

        if not all([academic_year_id, campus_id, class_obj_id, category_id]):
            return Response(
                {"detail": "academic_year, campus, class_obj, and category are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        assert_campus_allowed(request.user, campus_id, request=request)

        try:
            fee_structure = FeeStructure.objects.get(
                academic_year_id=academic_year_id,
                campus_id=campus_id,
                class_obj_id=class_obj_id,
                category_id=category_id,
                status="active",
            )
        except FeeStructure.DoesNotExist:
            return Response(
                {"detail": "No active fee structure found for the selected filters."},
                status=status.HTTP_404_NOT_FOUND,
            )

        due_date = _date.today()
        if due_date_str:
            from datetime import date as _parse_date
            try:
                due_date = _parse_date.fromisoformat(due_date_str)
            except ValueError:
                return Response(
                    {"detail": "Invalid due_date format. Use YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        enrollments = Enrollment.objects.filter(
            academic_year_id=academic_year_id,
            campus_id=campus_id,
            class_obj_id=class_obj_id,
            status="active",
        ).select_related("student", "academic_year", "campus", "class_obj", "section")

        if skip_existing:
            enrolled_with_invoice = set(
                InvoiceItem.objects.filter(
                    category_id=category_id,
                    invoice__academic_year_id=academic_year_id,
                    invoice__status__in=("issued", "partial", "paid"),
                    invoice__enrollment__campus_id=campus_id,
                    invoice__enrollment__class_obj_id=class_obj_id,
                ).values_list("invoice__enrollment_id", flat=True)
            )
            enrollments = enrollments.exclude(pk__in=enrolled_with_invoice)

        created = []
        skipped = []

        for enrollment in enrollments:
            try:
                invoice = Invoice.objects.create(
                    invoice_number=next_invoice_number(request.institution),
                    institution=request.institution,
                    campus=campus_id,
                    enrollment=enrollment,
                    student=enrollment.student,
                    academic_year=enrollment.academic_year,
                    issue_date=_date.today(),
                    due_date=due_date,
                    status="issued",
                    notes=notes,
                )
                InvoiceItem.objects.create(
                    invoice=invoice,
                    category=fee_structure.category,
                    description=fee_structure.category.name,
                    amount=fee_structure.amount,
                )
                created.append(invoice.pk)
            except (ModelValidationError, Exception) as exc:
                skipped.append({
                    "enrollment": enrollment.pk,
                    "student": str(enrollment.student),
                    "reason": str(exc),
                })

        record_audit(
            request=request,
            action="create",
            model_name="Invoice",
            object_id="bulk",
            object_repr=f"Bulk invoice creation for class {class_obj_id}",
            details={
                "created": len(created),
                "skipped": len(skipped),
                "category": category_id,
            },
        )

        return Response(
            {
                "created": len(created),
                "skipped": len(skipped),
                "skipped_details": skipped,
                "invoice_ids": created,
            },
            status=status.HTTP_201_CREATED,
        )


class BulkPaymentCreateView(APIView):
    """Record payments for multiple invoices at once.

    POST body:
        payments: [
            { invoice (int), amount (decimal), payment_method (str), reference (str, optional), notes (str, optional) }
        ]
        payment_date (str, optional) — defaults to today, applied to all
    """

    permission_classes = [IsAccountantRole]

    @transaction.atomic
    def post(self, request):
        from datetime import date as _date
        from django.core.exceptions import ValidationError as ModelValidationError
        from apps.accounts.access import assert_campus_allowed
        from .services import next_receipt_number

        payments_data = request.data.get("payments", [])
        payment_date_str = request.data.get("payment_date")

        if not payments_data:
            return Response(
                {"detail": "A list of payments is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment_date = _date.today()
        if payment_date_str:
            try:
                payment_date = _date.fromisoformat(payment_date_str)
            except ValueError:
                return Response(
                    {"detail": "Invalid payment_date format. Use YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        created = []
        errors = []

        for idx, item in enumerate(payments_data):
            invoice_id = item.get("invoice")
            amount = item.get("amount")
            payment_method = item.get("payment_method", "cash")
            reference = item.get("reference", "")
            notes = item.get("notes", "")

            if not invoice_id or not amount:
                errors.append({"index": idx, "reason": "invoice and amount are required."})
                continue

            try:
                invoice = Invoice.objects.select_for_update().get(pk=invoice_id)
            except Invoice.DoesNotExist:
                errors.append({"index": idx, "reason": f"Invoice {invoice_id} not found."})
                continue

            if invoice.academic_year.school_id != request.institution.id:
                errors.append({"index": idx, "reason": "Invoice belongs to a different institution."})
                continue

            assert_campus_allowed(request.user, invoice.enrollment.campus_id, request=request)

            if invoice.status in ("cancelled", "draft"):
                errors.append({"index": idx, "reason": f"Invoice {invoice.invoice_number} is {invoice.status}."})
                continue

            if amount <= 0:
                errors.append({"index": idx, "reason": "Amount must be greater than zero."})
                continue

            locked_invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
            if amount > locked_invoice.balance:
                errors.append({
                    "index": idx,
                    "reason": f"Amount {amount} exceeds balance {locked_invoice.balance} for {locked_invoice.invoice_number}.",
                })
                continue

            try:
                payment = Payment.objects.create(
                    receipt_number=next_receipt_number(request.institution),
                    invoice=locked_invoice,
                    amount=amount,
                    payment_date=payment_date,
                    payment_method=payment_method,
                    status="completed",
                    reference=reference,
                    notes=notes,
                )
                created.append({
                    "payment_id": payment.pk,
                    "receipt_number": payment.receipt_number,
                    "invoice_number": locked_invoice.invoice_number,
                    "amount": str(payment.amount),
                })
            except (ModelValidationError, Exception) as exc:
                errors.append({"index": idx, "reason": str(exc)})

        record_audit(
            request=request,
            action="payment",
            model_name="Payment",
            object_id="bulk",
            object_repr=f"Bulk payment: {len(created)} payments",
            details={"created": len(created), "errors": len(errors)},
        )

        return Response(
            {
                "created": len(created),
                "errors": len(errors),
                "payments": created,
                "error_details": errors,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_400_BAD_REQUEST,
        )


class LateFeeApplyView(APIView):
    """Apply late fees to overdue invoices.

    POST body:
        percent (decimal, optional) — percentage of balance to charge as late fee
        flat (decimal, optional) — fixed amount per overdue invoice
        grace_days (int, optional, default 5) — days past due before late fee applies
        dry_run (bool, optional, default false) — if true, only calculate without applying
    """

    permission_classes = [IsAccountantRole]

    def post(self, request):
        serializer = LateFeeApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from .late_fee_service import apply_late_fees

        result = apply_late_fees(
            percent=serializer.validated_data.get("percent"),
            flat=serializer.validated_data.get("flat"),
            grace_days=serializer.validated_data.get("grace_days", 5),
            dry_run=serializer.validated_data.get("dry_run", False),
            institution=request.institution,
        )

        if not serializer.validated_data.get("dry_run", False) and result["charged"] > 0:
            record_audit(
                request=request,
                action="late_fee_applied",
                model_name="Invoice",
                object_id="bulk",
                object_repr=f"Late fees applied to {result['charged']} invoices",
                details={
                    "charged": result["charged"],
                    "total": str(result["total"]),
                    "grace_days": serializer.validated_data.get("grace_days", 5),
                    "percent": str(serializer.validated_data.get("percent", "")),
                    "flat": str(serializer.validated_data.get("flat", "")),
                },
            )

        return Response(LateFeeResultSerializer(result).data)


class LateFeePreviewView(APIView):
    """Preview late fees that would be applied without actually applying them."""

    permission_classes = [IsAccountantRole]

    def get(self, request):
        from .late_fee_service import apply_late_fees

        percent = request.query_params.get("percent")
        flat = request.query_params.get("flat")
        grace_days = int(request.query_params.get("grace_days", 5))

        if percent:
            percent = Decimal(percent)
        if flat:
            flat = Decimal(flat)

        result = apply_late_fees(
            percent=percent,
            flat=flat,
            grace_days=grace_days,
            dry_run=True,
            institution=request.institution,
        )

        return Response(LateFeeResultSerializer(result).data)


class OutstandingBalanceView(APIView):
    """Get outstanding balances for students, optionally filtered."""

    permission_classes = [IsFinanceReaderRole]

    def get(self, request):
        from .services import InvoiceService

        service = InvoiceService(request.institution)

        student_id = request.query_params.get("student")
        campus_id = request.query_params.get("campus")
        academic_year_id = request.query_params.get("academic_year")

        student = None
        campus = None
        academic_year = None

        if student_id:
            from apps.students.models import Student
            try:
                student = Student.objects.get(pk=student_id)
                # Verify student belongs to institution
                if student.enrollment_set.filter(
                    academic_year__school=request.institution
                ).exists():
                    pass
                else:
                    return Response(
                        {"detail": "Student not found in this institution."},
                        status=status.HTTP_404_NOT_FOUND,
                    )
            except Student.DoesNotExist:
                return Response(
                    {"detail": "Student not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        if campus_id:
            try:
                campus = Campus.objects.get(pk=campus_id, school=request.institution)
            except Campus.DoesNotExist:
                return Response(
                    {"detail": "Campus not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        if academic_year_id:
            try:
                academic_year = AcademicYear.objects.get(
                    pk=academic_year_id, school=request.institution
                )
            except AcademicYear.DoesNotExist:
                return Response(
                    {"detail": "Academic year not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        invoices = service.get_outstanding_invoices(
            student=student,
            campus=campus,
            academic_year=academic_year,
        ).select_related("student", "enrollment__campus", "enrollment__class_obj", "enrollment__section")

        invoices = apply_campus_scope(invoices, request, "enrollment__campus_id")

        rows = []
        for invoice in invoices:
            rows.append({
                "invoice_id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "student_id": invoice.student_id,
                "student_name": invoice.student.full_name,
                "admission_number": invoice.student.admission_number,
                "campus": invoice.enrollment.campus.name,
                "class": invoice.enrollment.class_obj.name,
                "section": invoice.enrollment.section.name if invoice.enrollment.section_id else "",
                "issue_date": invoice.issue_date,
                "due_date": invoice.due_date,
                "total_amount": str(invoice.total_amount),
                "paid_amount": str(invoice.paid_amount),
                "balance": str(invoice.balance),
                "status": invoice.status,
                "is_overdue": invoice.due_date < date.today() and invoice.balance > 0,
                "days_overdue": (date.today() - invoice.due_date).days if invoice.due_date < date.today() else 0,
                "late_fee_applied": invoice.late_fee_applied,
                "late_fee_amount": str(invoice.late_fee_amount),
            })

        total_outstanding = sum(Decimal(row["balance"]) for row in rows)
        overdue_count = sum(1 for row in rows if row["is_overdue"])

        return Response({
            "rows": rows,
            "summary": {
                "total_students": len(set(row["student_id"] for row in rows)),
                "total_invoices": len(rows),
                "total_outstanding": str(total_outstanding),
                "overdue_invoices": overdue_count,
            },
        })


class StudentOutstandingBalanceView(APIView):
    """Get outstanding balance for a specific student (parent/student access)."""

    permission_classes = [IsFinanceReaderRole]

    def get(self, request, student_id):
        from .services import InvoiceService
        from apps.students.models import Student
        from apps.accounts.scopes import (
            is_parent,
            is_student,
            parent_student_ids,
            get_student_profile,
        )

        user = request.user

        # Determine if user can access this student's data
        if is_manager(user):
            pass  # Managers can access all
        elif is_parent(user):
            if int(student_id) not in parent_student_ids(user):
                raise PermissionDenied("You cannot access this student's balance.")
        elif is_student(user):
            profile = get_student_profile(user)
            if profile is None or profile.pk != int(student_id):
                raise PermissionDenied("You cannot access this student's balance.")
        else:
            raise PermissionDenied("Access denied.")

        try:
            student = Student.objects.select_related("guardian").get(
                pk=student_id,
                enrollment__academic_year__school=request.institution,
            )
        except Student.DoesNotExist:
            return Response(
                {"detail": "Student not found in this institution."},
                status=status.HTTP_404_NOT_FOUND,
            )

        service = InvoiceService(request.institution)
        invoices = service.get_outstanding_invoices(student=student).select_related(
            "enrollment__campus", "enrollment__class_obj", "enrollment__section"
        )

        rows = []
        for invoice in invoices:
            rows.append({
                "invoice_id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "issue_date": invoice.issue_date,
                "due_date": invoice.due_date,
                "total_amount": str(invoice.total_amount),
                "paid_amount": str(invoice.paid_amount),
                "balance": str(invoice.balance),
                "status": invoice.status,
                "is_overdue": invoice.due_date < date.today() and invoice.balance > 0,
                "days_overdue": (date.today() - invoice.due_date).days if invoice.due_date < date.today() else 0,
                "late_fee_applied": invoice.late_fee_applied,
                "late_fee_amount": str(invoice.late_fee_amount),
            })

        total_outstanding = sum(Decimal(row["balance"]) for row in rows)

        return Response({
            "student": {
                "id": student.id,
                "name": student.full_name,
                "admission_number": student.admission_number,
            },
            "invoices": rows,
            "total_outstanding": str(total_outstanding),
        })


class StudentFeeOverrideListCreateView(generics.ListCreateAPIView):
    """Manage student-specific fee overrides."""

    permission_classes = [IsAccountantRole]
    serializer_class = StudentFeeOverrideSerializer

    def get_queryset(self):
        return StudentFeeOverride.objects.filter(
            institution=self.request.institution
        ).select_related("student", "fee_structure__category", "fee_structure__campus", "fee_structure__class_obj")

    def perform_create(self, serializer):
        fee_structure = serializer.validated_data["fee_structure"]
        if fee_structure.academic_year.school_id != self.request.institution.id:
            raise PermissionDenied("Fee structure belongs to a different institution.")
        student = serializer.validated_data.get("student")
        if student is not None and student.institution_id != self.request.institution.id:
            raise PermissionDenied("Student does not belong to the active institution.")
        serializer.save(institution=self.request.institution)

        record_audit(
            request=self.request,
            action="fee_override_created",
            model_name="StudentFeeOverride",
            object_id=str(serializer.instance.pk),
            object_repr=str(serializer.instance),
            details={
                "student": serializer.instance.student.full_name,
                "fee_structure": str(serializer.instance.fee_structure),
                "amount": str(serializer.instance.amount),
            },
        )


class StudentFeeOverrideDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = StudentFeeOverrideSerializer

    def get_queryset(self):
        return StudentFeeOverride.objects.filter(
            institution=self.request.institution
        ).select_related("student", "fee_structure")

    def perform_update(self, serializer):
        serializer.save()
        record_audit(
            request=self.request,
            action="fee_override_updated",
            model_name="StudentFeeOverride",
            object_id=str(serializer.instance.pk),
            object_repr=str(serializer.instance),
            details={
                "student": serializer.instance.student.full_name,
                "fee_structure": str(serializer.instance.fee_structure),
                "amount": str(serializer.instance.amount),
            },
        )


class InstallmentScheduleView(APIView):
    """Get the installment schedule for an invoice."""

    permission_classes = [IsFinanceReaderRole]

    def get(self, request, invoice_id):
        invoice = get_object_or_404(
            Invoice.objects.filter(
                academic_year__school=request.institution
            ).select_related("enrollment__campus", "enrollment__class_obj"),
            pk=invoice_id,
        )

        from apps.accounts.access import assert_campus_allowed
        assert_campus_allowed(request.user, invoice.enrollment.campus_id, request=request)

        if invoice.installment_count <= 1:
            return Response({
                "invoice": invoice.invoice_number,
                "installment_count": 1,
                "schedule": [{
                    "number": 1,
                    "amount": str(invoice.total_amount),
                    "due_date": invoice.due_date,
                    "status": "paid" if invoice.status == "paid" else "pending",
                }],
            })

        # Generate installment schedule
        schedule = []
        installment_amount = invoice.installment_amount
        remaining = invoice.total_amount

        from datetime import timedelta
        import calendar

        def add_months(d, months):
            month = d.month - 1 + months
            year = d.year + month // 12
            month = month % 12 + 1
            day = min(d.day, calendar.monthrange(year, month)[1])
            return date(year, month, day)

        current_due = invoice.due_date
        for i in range(1, invoice.installment_count + 1):
            amt = installment_amount if i < invoice.installment_count else remaining
            remaining -= amt

            paid = sum(
                p.net_amount for p in invoice.payments.filter(
                    status="completed", installment_number=i
                )
            )
            status = "paid" if paid >= amt else ("partial" if paid > 0 else "pending")

            schedule.append({
                "number": i,
                "amount": str(amt),
                "due_date": current_due,
                "paid": str(paid),
                "balance": str(max(amt - paid, Decimal("0"))),
                "status": status,
            })

            if i < invoice.installment_count:
                if invoice.installment_frequency == "monthly":
                    current_due = add_months(current_due, 1)
                elif invoice.installment_frequency == "quarterly":
                    current_due = add_months(current_due, 3)
                elif invoice.installment_frequency == "termly":
                    # Approximate: 4 months per term
                    current_due = add_months(current_due, 4)

        return Response({
            "invoice": invoice.invoice_number,
            "installment_count": invoice.installment_count,
            "installment_frequency": invoice.installment_frequency,
            "total_amount": str(invoice.total_amount),
            "paid_amount": str(invoice.paid_amount),
            "balance": str(invoice.balance),
            "schedule": schedule,
        })


class FeeAssignmentPreviewView(APIView):
    """Preview fee assignments for enrollments without creating invoices."""

    permission_classes = [IsAccountantRole]

    def post(self, request):
        from apps.students.models import Enrollment
        from apps.schools.models import AcademicYear, Campus, Class
        from .services import FeeInvoiceService

        academic_year_id = request.data.get("academic_year")
        campus_id = request.data.get("campus")
        class_obj_id = request.data.get("class_obj")
        section_id = request.data.get("section")

        if not all([academic_year_id, campus_id, class_obj_id]):
            return Response(
                {"detail": "academic_year, campus, and class_obj are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from apps.accounts.access import assert_campus_allowed
        assert_campus_allowed(request.user, campus_id, request=request)

        academic_year = get_object_or_404(AcademicYear, pk=academic_year_id, school=request.institution)
        campus = get_object_or_404(Campus, pk=campus_id, school=request.institution)
        class_obj = get_object_or_404(Class, pk=class_obj_id, unit__campus=campus)

        service = FeeInvoiceService(request.institution, academic_year)

        enrollments = Enrollment.objects.filter(
            academic_year=academic_year,
            campus=campus,
            class_obj=class_obj,
            status="active",
        ).select_related("student", "section")

        if section_id:
            enrollments = enrollments.filter(section_id=section_id)

        preview = []
        for enrollment in enrollments:
            fee_structures = service.get_fee_structures_for_enrollment(enrollment)
            if fee_structures.exists():
                total = sum(fs.amount for fs in fee_structures)
                items = [{
                    "category": fs.category.name,
                    "amount": str(fs.amount),
                    "frequency": fs.category.frequency,
                    "installments": fs.installment_count,
                } for fs in fee_structures]

                # Check for student overrides
                overrides = StudentFeeOverride.objects.filter(
                    student=enrollment.student,
                    fee_structure__in=fee_structures,
                    status="active",
                ).select_related("fee_structure")

                if overrides.exists():
                    total = Decimal("0")
                    items = []
                    for fs in fee_structures:
                        override = overrides.filter(fee_structure=fs).first()
                        amount = override.amount if override else fs.amount
                        total += amount
                        items.append({
                            "category": fs.category.name,
                            "amount": str(amount),
                            "frequency": fs.category.frequency,
                            "installments": fs.installment_count,
                            "overridden": bool(override),
                        })

                preview.append({
                    "enrollment_id": enrollment.id,
                    "student_id": enrollment.student_id,
                    "student_name": enrollment.student.full_name,
                    "admission_number": enrollment.student.admission_number,
                    "section": enrollment.section.name if enrollment.section_id else "",
                    "fee_structures_count": fee_structures.count(),
                    "total_amount": str(total),
                    "items": items,
                    "has_override": overrides.exists(),
                })
            else:
                preview.append({
                    "enrollment_id": enrollment.id,
                    "student_id": enrollment.student_id,
                    "student_name": enrollment.student.full_name,
                    "admission_number": enrollment.student.admission_number,
                    "section": enrollment.section.name if enrollment.section_id else "",
                    "fee_structures_count": 0,
                    "total_amount": "0.00",
                    "items": [],
                    "has_override": False,
                    "warning": "No fee structure found for this enrollment",
                })

        return Response({
            "academic_year": academic_year.name,
            "campus": campus.name,
            "class": class_obj.name,
            "section": section_id,
            "total_students": len(preview),
            "total_amount": str(sum(Decimal(p["total_amount"]) for p in preview)),
            "preview": preview,
        })


class ConcessionListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = ConcessionSerializer

    def get_queryset(self):
        queryset = Concession.objects.filter(
            institution=self.request.institution
        ).select_related("invoice", "invoice__student", "invoice__enrollment__campus")
        return apply_campus_scope(queryset, self.request, "invoice__enrollment__campus_id")

    def perform_create(self, serializer):
        invoice = serializer.validated_data["invoice"]
        if invoice.academic_year.school_id != self.request.institution.id:
            raise PermissionDenied("Invoice is outside the active institution.")
        from apps.accounts.access import assert_campus_allowed
        assert_campus_allowed(self.request.user, invoice.enrollment.campus_id, request=self.request)
        serializer.save(institution=self.request.institution)


class ConcessionDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = ConcessionSerializer

    def get_queryset(self):
        queryset = Concession.objects.filter(
            institution=self.request.institution
        ).select_related("invoice", "invoice__student", "invoice__enrollment__campus")
        return apply_campus_scope(queryset, self.request, "invoice__enrollment__campus_id")


class ConcessionApproveView(APIView):
    permission_classes = [IsAccountantRole]

    @transaction.atomic
    def post(self, request, pk):
        concession = get_object_or_404(
            Concession.objects.select_related("invoice__enrollment"),
            pk=pk,
            institution=request.institution,
        )
        from apps.accounts.access import assert_campus_allowed
        assert_campus_allowed(request.user, concession.invoice.enrollment.campus_id, request=request)

        if concession.status != "pending":
            return Response({"detail": "Only pending concessions can be approved."}, status=400)

        from django.utils import timezone
        concession.status = "approved"
        concession.approved_by = request.user
        concession.approved_at = timezone.now()
        concession.save(update_fields=["status", "approved_by", "approved_at"])
        concession.invoice.refresh_status()

        record_audit(
            request=request,
            action="concession_approved",
            model_name="Concession",
            object_id=str(pk),
            object_repr=str(concession),
            details={"amount": str(concession.amount), "type": concession.type},
        )
        return Response(ConcessionSerializer(concession).data)


class FineListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = FineSerializer

    def get_queryset(self):
        queryset = Fine.objects.filter(
            institution=self.request.institution
        ).select_related("student", "academic_year")
        return apply_campus_scope(queryset, self.request, "student__enrollments__campus_id")

    def perform_create(self, serializer):
        academic_year = serializer.validated_data["academic_year"]
        if academic_year.school_id != self.request.institution.id:
            raise PermissionDenied("Academic year is outside the active institution.")
        student = serializer.validated_data["student"]
        if student.institution_id != self.request.institution.id:
            raise PermissionDenied("Student does not belong to the active institution.")
        from apps.accounts.access import assert_campus_allowed
        enrollment = student.enrollments.filter(status="active").first()
        if enrollment is not None:
            assert_campus_allowed(self.request.user, enrollment.campus_id, request=self.request)
        serializer.save(institution=self.request.institution, issued_by=self.request.user)


class FineDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = FineSerializer

    def get_queryset(self):
        queryset = Fine.objects.filter(
            institution=self.request.institution
        ).select_related("student", "academic_year")
        return apply_campus_scope(queryset, self.request, "student__enrollments__campus_id")


class FineApproveView(APIView):
    permission_classes = [IsAccountantRole]

    @transaction.atomic
    def post(self, request, pk):
        fine = get_object_or_404(
            Fine.objects.select_related("student__enrollments"),
            pk=pk,
            institution=request.institution,
        )

        # Check campus access for the student's enrollment
        enrollment = fine.student.enrollments.filter(
            academic_year=fine.academic_year, status="active"
        ).first()
        if enrollment:
            from apps.accounts.access import assert_campus_allowed
            assert_campus_allowed(request.user, enrollment.campus_id, request=request)

        if fine.status != "pending":
            return Response({"detail": "Only pending fines can be approved."}, status=400)

        from django.utils import timezone
        fine.status = "approved"
        fine.approved_by = request.user
        fine.approved_at = timezone.now()
        fine.save(update_fields=["status", "approved_by", "approved_at"])

        record_audit(
            request=request,
            action="fine_approved",
            model_name="Fine",
            object_id=str(pk),
            object_repr=str(fine),
            details={"amount": str(fine.amount), "type": fine.type},
        )
        return Response(FineSerializer(fine).data)


class FineWaiveView(APIView):
    permission_classes = [IsAccountantRole]

    @transaction.atomic
    def post(self, request, pk):
        fine = get_object_or_404(
            Fine.objects.select_related("student__enrollments"),
            pk=pk,
            institution=request.institution,
        )

        enrollment = fine.student.enrollments.filter(
            academic_year=fine.academic_year, status="active"
        ).first()
        if enrollment:
            from apps.accounts.access import assert_campus_allowed
            assert_campus_allowed(request.user, enrollment.campus_id, request=request)

        serializer = FineWaiveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from django.utils import timezone
        fine.status = "waived"
        fine.waived_by = request.user
        fine.waived_at = timezone.now()
        fine.waiver_reason = serializer.validated_data["waiver_reason"]
        fine.save(update_fields=["status", "waived_by", "waived_at", "waiver_reason"])

        record_audit(
            request=request,
            action="fine_waived",
            model_name="Fine",
            object_id=str(pk),
            object_repr=str(fine),
            details={"amount": str(fine.amount), "reason": fine.waiver_reason},
        )
        return Response(FineSerializer(fine).data)


class AdjustmentListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = AdjustmentSerializer

    def get_queryset(self):
        queryset = Adjustment.objects.filter(
            institution=self.request.institution
        ).select_related("student", "invoice", "payment")
        return apply_campus_scope(queryset, self.request, "student__enrollments__campus_id")

    def perform_create(self, serializer):
        invoice = serializer.validated_data.get("invoice")
        if invoice is not None and invoice.academic_year.school_id != self.request.institution.id:
            raise PermissionDenied("Invoice is outside the active institution.")
        payment = serializer.validated_data.get("payment")
        if payment is not None and payment.invoice.academic_year.school_id != self.request.institution.id:
            raise PermissionDenied("Payment is outside the active institution.")
        student = serializer.validated_data.get("student")
        if student is not None:
            if student.institution_id != self.request.institution.id:
                raise PermissionDenied("Student does not belong to the active institution.")
            from apps.accounts.access import assert_campus_allowed
            enrollment = student.enrollments.filter(status="active").first()
            if enrollment is not None:
                assert_campus_allowed(self.request.user, enrollment.campus_id, request=self.request)
        serializer.save(institution=self.request.institution, created_by=self.request.user)


class AdjustmentDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = AdjustmentSerializer

    def get_queryset(self):
        queryset = Adjustment.objects.filter(
            institution=self.request.institution
        ).select_related("student", "invoice", "payment")
        return apply_campus_scope(queryset, self.request, "student__enrollments__campus_id")


class AdjustmentApplyView(APIView):
    permission_classes = [IsAccountantRole]

    @transaction.atomic
    def post(self, request, pk):
        adjustment = get_object_or_404(
            Adjustment.objects.select_related("student", "invoice", "payment"),
            pk=pk,
            institution=request.institution,
        )

        if adjustment.status != "pending":
            return Response({"detail": "Only pending adjustments can be applied."}, status=400)

        # Apply the adjustment
        from django.utils import timezone
        if adjustment.type == "credit" and adjustment.invoice:
            # Create a concession for credit adjustments
            Concession.objects.create(
                institution=adjustment.institution,
                invoice=adjustment.invoice,
                type="adjustment",
                amount=adjustment.amount,
                reason=f"Adjustment: {adjustment.reason}",
                status="approved",
            )
            adjustment.invoice.refresh_status()

        elif adjustment.type == "debit" and adjustment.invoice:
            # Create a fine for debit adjustments
            Fine.objects.create(
                institution=adjustment.institution,
                student=adjustment.student,
                academic_year=adjustment.invoice.academic_year,
                type="other",
                amount=adjustment.amount,
                reason=f"Adjustment: {adjustment.reason}",
                status="approved",
            )

        elif adjustment.type == "write_off" and adjustment.invoice:
            # Write off the invoice balance
            Concession.objects.create(
                institution=adjustment.institution,
                invoice=adjustment.invoice,
                type="waiver",
                amount=adjustment.invoice.balance,
                reason=f"Write off: {adjustment.reason}",
                status="approved",
            )
            adjustment.invoice.refresh_status()

        adjustment.status = "applied"
        adjustment.approved_by = request.user
        adjustment.approved_at = timezone.now()
        adjustment.applied_at = timezone.now()
        adjustment.save(update_fields=["status", "approved_by", "approved_at", "applied_at"])

        record_audit(
            request=request,
            action="adjustment_applied",
            model_name="Adjustment",
            object_id=str(pk),
            object_repr=str(adjustment),
            details={"amount": str(adjustment.amount), "type": adjustment.type},
        )
        return Response(AdjustmentSerializer(adjustment).data)


class PaymentRefundListCreateView(generics.ListCreateAPIView):
    """Enhanced refund view with duplicate protection."""

    permission_classes = [IsAccountantRole]
    serializer_class = PaymentRefundSerializer

    def get_queryset(self):
        queryset = PaymentRefund.objects.filter(
            institution=self.request.institution
        ).select_related("payment", "payment__invoice", "payment__invoice__enrollment__campus")
        return apply_campus_scope(queryset, self.request, "payment__invoice__enrollment__campus_id")

    def perform_create(self, serializer):
        payment = serializer.validated_data["payment"]
        invoice = payment.invoice

        # Verify access to the invoice
        from apps.finance.views import scoped_invoice_queryset
        if not scoped_invoice_queryset(self.request).filter(pk=invoice.pk).exists():
            raise PermissionDenied("You cannot refund a payment outside your institution or campus.")

        # Check for duplicate refund on same payment with same amount
        existing = PaymentRefund.objects.filter(
            payment=payment,
            amount=serializer.validated_data["amount"],
            status="completed",
        ).first()
        if existing:
            raise serializers.ValidationError(
                {"detail": "A refund with the same amount already exists for this payment."}
            )

        refund = serializer.save(created_by=self.request.user)
        record_audit(
            request=self.request,
            action="payment_refund",
            model_name="PaymentRefund",
            object_id=str(refund.pk),
            object_repr=str(refund),
            details={"amount": str(refund.amount), "payment": payment.receipt_number},
        )


class JournalEntryListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return JournalEntryCreateSerializer
        return JournalEntrySerializer

    def get_queryset(self):
        queryset = institution_filter(
            JournalEntry.objects.prefetch_related("lines__account").order_by("-posting_date", "-id"),
            self.request,
        )
        return apply_campus_scope(queryset, self.request, "campus_id")

    def perform_create(self, serializer):
        campus = serializer.validated_data.get("campus")
        if campus is not None:
            from apps.accounts.access import assert_campus_allowed
            assert_campus_allowed(
                self.request.user, campus.id, request=self.request
            )
        serializer.save(
            institution=self.request.institution,
            created_by=self.request.user,
        )


class JournalEntryDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = JournalEntrySerializer

    def get_queryset(self):
        queryset = JournalEntry.objects.prefetch_related("lines__account").filter(
            institution=self.request.institution
        )
        return apply_campus_scope(queryset, self.request, "campus_id")


class JournalEntryPostView(APIView):
    permission_classes = [IsAccountantRole]

    @transaction.atomic
    def post(self, request, pk):
        serializer = JournalEntryPostSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        entry = get_object_or_404(
            JournalEntry.objects.filter(
                institution=request.institution
            ).prefetch_related("lines__account"),
            pk=pk,
        )

        if entry.campus_id:
            from apps.accounts.access import assert_campus_allowed
            assert_campus_allowed(request.user, entry.campus_id, request=request)

        try:
            entry.post(request.user)
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)

        record_audit(
            request=request,
            action="journal_posted",
            model_name="JournalEntry",
            object_id=str(entry.pk),
            object_repr=str(entry),
            details={"total_debit": str(entry.total_debit), "total_credit": str(entry.total_credit)},
        )

        return Response(JournalEntrySerializer(entry).data)


class JournalEntryVoidView(APIView):
    permission_classes = [IsAccountantRole]

    @transaction.atomic
    def post(self, request, pk):
        serializer = JournalEntryVoidSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        entry = get_object_or_404(
            JournalEntry.objects.filter(
                institution=request.institution
            ).prefetch_related("lines__account"),
            pk=pk,
        )

        if entry.campus_id:
            from apps.accounts.access import assert_campus_allowed
            assert_campus_allowed(request.user, entry.campus_id, request=request)

        reason = serializer.validated_data["reason"]

        try:
            reversal = entry.void(request.user, reason)
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)

        record_audit(
            request=request,
            action="journal_voided",
            model_name="JournalEntry",
            object_id=str(entry.pk),
            object_repr=str(entry),
            details={"reversal_id": str(reversal.pk), "reason": reason},
        )

        return Response(JournalEntrySerializer(entry).data)


class BankAccountListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = BankAccountSerializer

    def get_queryset(self):
        queryset = institution_filter(BankAccount.objects.select_related("account", "campus"), self.request)
        active = self.request.query_params.get("active")
        if active is not None:
            queryset = queryset.filter(is_active=active.lower() == "true")
        return queryset

    def perform_create(self, serializer):
        serializer.save(institution=self.request.institution, created_by=self.request.user)


class BankAccountDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = BankAccountSerializer

    def get_queryset(self):
        queryset = BankAccount.objects.select_related("account", "campus").filter(
            institution=self.request.institution
        )
        return apply_campus_scope(queryset, self.request, "campus_id")


class BankReconciliationListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return BankReconciliationCreateSerializer
        return BankReconciliationSerializer

    def get_queryset(self):
        queryset = BankReconciliation.objects.select_related("bank_account", "bank_account__campus").filter(
            institution=self.request.institution
        )
        return apply_campus_scope(queryset, self.request, "bank_account__campus_id")

    def perform_create(self, serializer):
        serializer.save(institution=self.request.institution, prepared_by=self.request.user)


class BankReconciliationDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = BankReconciliationSerializer

    def get_queryset(self):
        queryset = BankReconciliation.objects.select_related("bank_account", "bank_account__campus").filter(
            institution=self.request.institution
        )
        return apply_campus_scope(queryset, self.request, "bank_account__campus_id")


class BankReconciliationApproveView(APIView):
    permission_classes = [IsAccountantRole]

    @transaction.atomic
    def post(self, request, pk):
        reconciliation = get_object_or_404(
            BankReconciliation.objects.select_related("bank_account"),
            pk=pk,
            institution=request.institution,
        )

        if reconciliation.bank_account.campus_id:
            from apps.accounts.access import assert_campus_allowed
            assert_campus_allowed(request.user, reconciliation.bank_account.campus_id, request=request)

        if reconciliation.status != "completed":
            return Response({"detail": "Only completed reconciliations can be approved."}, status=400)

        reconciliation.approve(request.user)

        record_audit(
            request=request,
            action="bank_reconciliation_approved",
            model_name="BankReconciliation",
            object_id=str(reconciliation.pk),
            object_repr=str(reconciliation),
            details={"difference": str(reconciliation.difference)},
        )

        return Response(BankReconciliationSerializer(reconciliation).data)


class BudgetListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = BudgetSerializer

    def get_queryset(self):
        queryset = institution_filter(
            Budget.objects.select_related("campus", "academic_year").order_by("-start_date", "-id"),
            self.request,
        )
        return apply_campus_scope(queryset, self.request, "campus_id")

    def perform_create(self, serializer):
        serializer.save(institution=self.request.institution, created_by=self.request.user)


class BudgetDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = BudgetSerializer

    def get_queryset(self):
        queryset = Budget.objects.select_related("campus", "academic_year").filter(
            institution=self.request.institution
        )
        return apply_campus_scope(queryset, self.request, "campus_id")


class BudgetLineListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAccountantRole]
    serializer_class = BudgetLineSerializer

    def get_queryset(self):
        budget_id = self.kwargs.get("budget_id")
        return BudgetLine.objects.select_related("account").filter(
            budget_id=budget_id,
            budget__institution=self.request.institution,
        )

    def perform_create(self, serializer):
        budget = get_object_or_404(
            Budget.objects.filter(institution=self.request.institution),
            pk=self.kwargs.get("budget_id"),
        )
        serializer.save(budget=budget)


class BudgetApproveView(APIView):
    permission_classes = [IsAccountantRole]

    @transaction.atomic
    def post(self, request, pk):
        budget = get_object_or_404(
            Budget.objects.select_related("campus"),
            pk=pk,
            institution=request.institution,
        )

        if budget.campus_id:
            from apps.accounts.access import assert_campus_allowed
            assert_campus_allowed(request.user, budget.campus_id, request=request)

        if budget.status != "draft":
            return Response({"detail": "Only draft budgets can be approved."}, status=400)

        budget.approve(request.user)

        record_audit(
            request=request,
            action="budget_approved",
            model_name="Budget",
            object_id=str(budget.pk),
            object_repr=str(budget),
            details={"total_income": str(budget.total_budgeted_income), "total_expense": str(budget.total_budgeted_expense)},
        )

        return Response(BudgetSerializer(budget).data)


class BudgetCloseView(APIView):
    permission_classes = [IsAccountantRole]

    @transaction.atomic
    def post(self, request, pk):
        budget = get_object_or_404(
            Budget.objects.select_related("campus"),
            pk=pk,
            institution=request.institution,
        )

        if budget.campus_id:
            from apps.accounts.access import assert_campus_allowed
            assert_campus_allowed(request.user, budget.campus_id, request=request)

        if budget.status != "active":
            return Response({"detail": "Only active budgets can be closed."}, status=400)

        budget.close(request.user)

        record_audit(
            request=request,
            action="budget_closed",
            model_name="Budget",
            object_id=str(budget.pk),
            object_repr=str(budget),
            details={},
        )

        return Response(BudgetSerializer(budget).data)

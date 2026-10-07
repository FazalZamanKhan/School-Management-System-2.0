from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from apps.accounts.access import get_institution

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
from .services import next_invoice_number, next_receipt_number


class InvoiceItemWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = ["category", "description", "amount"]


class InvoiceCreateSerializer(serializers.ModelSerializer):
    items = InvoiceItemWriteSerializer(many=True, write_only=True)
    invoice_number = serializers.CharField(read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "invoice_number",
            "student",
            "enrollment",
            "academic_year",
            "issue_date",
            "due_date",
            "discount",
            "notes",
            "items",
        ]

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError(
                "At least one invoice item is required."
            )

        for item in items:
            if item["amount"] <= 0:
                raise serializers.ValidationError(
                    "Invoice item amounts must be greater than zero."
                )

        return items

    @transaction.atomic
    def create(self, validated_data):
        from django.core.exceptions import ValidationError as ModelValidationError

        items = validated_data.pop("items")

        institution = get_institution(self.context.get("request"))
        validated_data["institution"] = institution
        validated_data["invoice_number"] = next_invoice_number(institution)
        validated_data["status"] = "issued"

        try:
            invoice = Invoice.objects.create(**validated_data)
        except ModelValidationError as exc:
            raise serializers.ValidationError(exc.message_dict)

        for item in items:
            InvoiceItem.objects.create(invoice=invoice, **item)

        return invoice


class PaymentCreateSerializer(serializers.ModelSerializer):
    receipt_number = serializers.CharField(read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "receipt_number",
            "invoice",
            "amount",
            "payment_date",
            "payment_method",
            "status",
            "reference",
            "notes",
        ]

    def validate(self, attrs):
        invoice = attrs.get("invoice")
        amount = attrs.get("amount")

        if invoice and amount is not None:
            if amount <= 0:
                raise serializers.ValidationError(
                    {"amount": "Payment amount must be greater than zero."}
                )

            if amount > invoice.balance:
                raise serializers.ValidationError(
                    {
                        "amount": (
                            "Payment cannot be greater than the "
                            f"invoice balance (Rs. {invoice.balance:,.2f})."
                        )
                    }
                )

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        from django.core.exceptions import ValidationError as ModelValidationError

        invoice = validated_data["invoice"]
        locked_invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
        if validated_data["amount"] > locked_invoice.balance:
            raise serializers.ValidationError(
                {"amount": "Payment cannot be greater than the current invoice balance."}
            )
        validated_data["invoice"] = locked_invoice
        institution = get_institution(self.context.get("request"))
        validated_data["institution"] = institution
        validated_data["receipt_number"] = next_receipt_number(institution)

        try:
            return Payment.objects.create(**validated_data)
        except ModelValidationError as exc:
            raise serializers.ValidationError(exc.message_dict)


class FeeCategorySerializer(serializers.ModelSerializer):
    frequency_display = serializers.CharField(
        source="get_frequency_display",
        read_only=True,
    )

    def validate_name(self, value):
        institution = get_institution(self.context.get("request"))
        if institution and FeeCategory._base_manager.filter(institution=institution, name=value).exists():
            raise serializers.ValidationError("A fee category with this name already exists in this school.")
        return value

    class Meta:
        model = FeeCategory
        fields = [
            "id",
            "name",
            "description",
            "frequency",
            "frequency_display",
            "status",
            "created_at",
            "updated_at",
        ]


class FeeStructureSerializer(serializers.ModelSerializer):
    academic_year_name = serializers.CharField(
        source="academic_year.name",
        read_only=True,
    )
    campus_name = serializers.CharField(
        source="campus.name",
        read_only=True,
    )
    class_name = serializers.CharField(
        source="class_obj.name",
        read_only=True,
    )
    section_name = serializers.CharField(
        source="section.name",
        read_only=True,
    )
    category_name = serializers.CharField(
        source="category.name",
        read_only=True,
    )
    category_frequency = serializers.CharField(
        source="category.frequency",
        read_only=True,
    )
    category_frequency_display = serializers.CharField(
        source="category.get_frequency_display",
        read_only=True,
    )
    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    class Meta:
        model = FeeStructure
        fields = [
            "id",
            "academic_year",
            "academic_year_name",
            "campus",
            "campus_name",
            "class_obj",
            "class_name",
            "section",
            "section_name",
            "category",
            "category_name",
            "category_frequency",
            "category_frequency_display",
            "amount",
            "due_day",
            "installment_count",
            "installment_frequency",
            "status",
            "status_display",
            "created_at",
            "updated_at",
        ]

    def validate(self, attrs):
        from django.core.exceptions import ValidationError as ModelValidationError

        if self.instance is not None:
            candidate = self.instance

            for field, value in attrs.items():
                setattr(candidate, field, value)
        else:
            candidate = FeeStructure(**attrs)

        try:
            candidate.clean()
        except ModelValidationError as exc:
            raise serializers.ValidationError(exc.message_dict)

        return attrs

    def create(self, validated_data):
        from django.core.exceptions import ValidationError as ModelValidationError

        try:
            return FeeStructure.objects.create(**validated_data)
        except ModelValidationError as exc:
            raise serializers.ValidationError(exc.message_dict)


class InvoiceItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(
        source="category.name",
        read_only=True,
    )

    class Meta:
        model = InvoiceItem
        fields = [
            "id",
            "category",
            "category_name",
            "description",
            "amount",
        ]


class InvoiceSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source="student.full_name",
        read_only=True,
    )
    admission_number = serializers.CharField(
        source="student.admission_number",
        read_only=True,
    )
    academic_year_name = serializers.CharField(
        source="academic_year.name",
        read_only=True,
    )
    campus_name = serializers.CharField(
        source="enrollment.campus.name",
        read_only=True,
    )
    class_name = serializers.CharField(
        source="enrollment.class_obj.name",
        read_only=True,
    )
    section_name = serializers.CharField(
        source="enrollment.section.name",
        read_only=True,
    )
    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )
    items = InvoiceItemSerializer(many=True, read_only=True)
    installment_amount = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    installments_paid = serializers.IntegerField(read_only=True)
    installments_remaining = serializers.IntegerField(read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "invoice_number",
            "student",
            "student_name",
            "admission_number",
            "enrollment",
            "academic_year",
            "academic_year_name",
            "campus_name",
            "class_name",
            "section_name",
            "issue_date",
            "due_date",
            "installment_count",
            "installment_frequency",
            "next_installment_due",
            "discount",
            "subtotal",
            "total_amount",
            "paid_amount",
            "balance",
            "installment_amount",
            "installments_paid",
            "installments_remaining",
            "status",
            "status_display",
            "late_fee_applied",
            "late_fee_amount",
            "late_fee_date",
            "notes",
            "items",
            "created_at",
            "updated_at",
        ]


class PaymentSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(
        source="invoice.invoice_number",
        read_only=True,
    )
    student_name = serializers.CharField(
        source="invoice.student.full_name",
        read_only=True,
    )
    admission_number = serializers.CharField(
        source="invoice.student.admission_number",
        read_only=True,
    )
    payment_method_display = serializers.CharField(
        source="get_payment_method_display",
        read_only=True,
    )
    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

    class Meta:
        model = Payment
        fields = [
            "id",
            "receipt_number",
            "invoice",
            "invoice_number",
            "student_name",
            "admission_number",
            "amount",
            "net_amount",
            "payment_date",
            "payment_method",
            "payment_method_display",
            "status",
            "status_display",
            "reference",
            "notes",
            "installment_number",
            "created_at",
            "updated_at",
        ]


class PaymentReversalSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentReversal
        fields = ["id", "payment", "amount", "reversal_date", "reason", "status", "created_by", "created_at"]
        read_only_fields = ["id", "created_by", "created_at"]


class AccountSerializer(serializers.ModelSerializer):
    account_type_display = serializers.CharField(source="get_account_type_display", read_only=True)

    class Meta:
        model = Account
        fields = [
            "id", "institution", "parent", "code", "name", "account_type",
            "account_type_display", "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "institution", "created_at", "updated_at"]


class JournalLineSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source="account.code", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)

    class Meta:
        model = JournalLine
        fields = ["id", "account", "account_code", "account_name", "debit", "credit", "memo"]
        read_only_fields = ["id"]


class JournalEntrySerializer(serializers.ModelSerializer):
    lines = JournalLineSerializer(many=True, read_only=True)
    total_debit = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    total_credit = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    is_balanced = serializers.BooleanField(read_only=True)

    class Meta:
        model = JournalEntry
        fields = [
            "id", "institution", "campus", "posting_date", "description",
            "source_type", "source_id", "status", "created_by", "created_at",
            "lines", "total_debit", "total_credit", "is_balanced",
        ]
        read_only_fields = ["id", "institution", "created_by", "created_at"]


class ExpenseSerializer(serializers.ModelSerializer):
    expense_account_name = serializers.CharField(source="expense_account.name", read_only=True)
    payment_account_name = serializers.CharField(source="payment_account.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Expense
        fields = [
            "id", "institution", "campus", "expense_account", "expense_account_name",
            "payment_account", "payment_account_name", "vendor", "expense_date", "amount",
            "status", "status_display", "reference", "notes", "journal_entry",
            "created_by", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "institution", "journal_entry", "created_by", "created_at", "updated_at"]


class ConcessionSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    invoice_number = serializers.CharField(source="invoice.invoice_number", read_only=True)
    type_display = serializers.CharField(source="get_type_display", read_only=True)

    class Meta:
        model = Concession
        fields = [
            "id", "invoice", "invoice_number", "type", "type_display",
            "amount", "reason", "status", "status_display",
            "approved_by", "approved_at", "created_at",
        ]
        read_only_fields = ["id", "approved_by", "approved_at", "created_at"]


class PaymentRefundSerializer(serializers.ModelSerializer):
    receipt_number = serializers.CharField(source="payment.receipt_number", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = PaymentRefund
        fields = [
            "id", "payment", "receipt_number", "amount", "refund_date", "refund_method",
            "reason", "status", "status_display", "created_by", "created_at",
        ]
        read_only_fields = ["id", "created_by", "created_at"]


class StudentFeeOverrideSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    admission_number = serializers.CharField(source="student.admission_number", read_only=True)
    fee_structure_name = serializers.CharField(source="fee_structure.category.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = StudentFeeOverride
        fields = [
            "id", "student", "student_name", "admission_number", "fee_structure",
            "fee_structure_name", "amount", "reason", "status", "status_display",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "institution"]


class LateFeeApplySerializer(serializers.Serializer):
    percent = serializers.DecimalField(max_digits=5, decimal_places=2, required=False, min_value=Decimal("0.01"), max_value=Decimal("100"))
    flat = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, min_value=Decimal("0.01"))
    grace_days = serializers.IntegerField(default=5, min_value=0)
    dry_run = serializers.BooleanField(default=False)

    def validate(self, attrs):
        if not attrs.get("percent") and not attrs.get("flat"):
            raise serializers.ValidationError("Provide either percent or flat.")
        if attrs.get("percent") and attrs.get("flat"):
            raise serializers.ValidationError("Provide only one of percent or flat.")
        return attrs


class LateFeeResultSerializer(serializers.Serializer):
    charged = serializers.IntegerField()
    total = serializers.DecimalField(max_digits=14, decimal_places=2)
    rows = serializers.ListField(child=serializers.DictField())
    truncated_rows = serializers.IntegerField()
    dry_run = serializers.BooleanField()


class FineSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    type_display = serializers.CharField(source="get_type_display", read_only=True)
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    admission_number = serializers.CharField(source="student.admission_number", read_only=True)

    class Meta:
        model = Fine
        fields = [
            "id", "student", "student_name", "admission_number", "academic_year",
            "type", "type_display", "amount", "reason", "status", "status_display",
            "issued_by", "approved_by", "approved_at", "waived_by", "waived_at",
            "waiver_reason", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "issued_by", "approved_by", "approved_at", "waived_by", "waived_at", "created_at", "updated_at"]


class FineApproveSerializer(serializers.Serializer):
    pass


class FineWaiveSerializer(serializers.Serializer):
    waiver_reason = serializers.CharField(required=True)


class AdjustmentSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    type_display = serializers.CharField(source="get_type_display", read_only=True)
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    invoice_number = serializers.CharField(source="invoice.invoice_number", read_only=True)
    receipt_number = serializers.CharField(source="payment.receipt_number", read_only=True)

    class Meta:
        model = Adjustment
        fields = [
            "id", "student", "student_name", "invoice", "invoice_number",
            "payment", "receipt_number", "type", "type_display", "amount",
            "reason", "status", "status_display", "created_by", "approved_by",
            "approved_at", "applied_at", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_by", "approved_by", "approved_at", "applied_at", "created_at", "updated_at"]


class AdjustmentApplySerializer(serializers.Serializer):
    pass


class JournalEntrySerializer(serializers.ModelSerializer):
    lines = JournalLineSerializer(many=True, read_only=True)
    total_debit = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    total_credit = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    is_balanced = serializers.BooleanField(read_only=True)
    posted_by_name = serializers.CharField(source="posted_by.get_full_name", read_only=True)
    voided_by_name = serializers.CharField(source="voided_by.get_full_name", read_only=True)
    reversal_id = serializers.IntegerField(source="reversed_entry.id", read_only=True)

    class Meta:
        model = JournalEntry
        fields = [
            "id", "institution", "campus", "posting_date", "description", "reference",
            "source_type", "source_id", "status", "created_by", "posted_by", "posted_by_name",
            "posted_at", "voided_by", "voided_by_name", "voided_at", "void_reason",
            "reversed_entry", "reversal_id", "created_at", "updated_at",
            "lines", "total_debit", "total_credit", "is_balanced",
        ]
        read_only_fields = ["id", "institution", "created_by", "posted_by", "posted_at", 
                           "voided_by", "voided_at", "reversed_entry", "created_at", "updated_at"]


class JournalEntryCreateSerializer(serializers.ModelSerializer):
    lines = JournalLineSerializer(many=True, write_only=True)

    class Meta:
        model = JournalEntry
        fields = [
            "id", "campus", "posting_date", "description", "reference",
            "source_type", "source_id", "lines",
        ]

    def validate_lines(self, lines):
        if not lines:
            raise serializers.ValidationError("At least one journal line is required.")
        total_debit = sum(Decimal(str(line.get("debit", 0))) for line in lines)
        total_credit = sum(Decimal(str(line.get("credit", 0))) for line in lines)
        if total_debit != total_credit:
            raise serializers.ValidationError(
                f"Journal entry unbalanced: debit={total_debit}, credit={total_credit}"
            )
        return lines

    def create(self, validated_data):
        lines = validated_data.pop("lines")
        validated_data["institution"] = self.context["request"].institution
        validated_data["created_by"] = self.context["request"].user
        validated_data["status"] = "draft"

        entry = JournalEntry.objects.create(**validated_data)
        for line in lines:
            JournalLine.objects.create(entry=entry, **line)
        return entry


class JournalEntryPostSerializer(serializers.Serializer):
    pass


class JournalEntryVoidSerializer(serializers.Serializer):
    reason = serializers.CharField(required=True)


class BankAccountSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source="account.code", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)
    current_balance = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = BankAccount
        fields = [
            "id", "institution", "campus", "account", "account_code", "account_name",
            "bank_name", "account_number", "account_holder", "branch",
            "swift_code", "iban", "currency", "opening_balance", "opening_date",
            "current_balance", "is_active", "last_reconciled_date",
            "last_reconciled_balance", "created_by", "created_at", "updated_at",
            "status_display",
        ]
        read_only_fields = ["id", "institution", "current_balance", "last_reconciled_date",
                           "last_reconciled_balance", "created_by", "created_at", "updated_at"]


class BankReconciliationSerializer(serializers.ModelSerializer):
    bank_account_name = serializers.CharField(source="bank_account.__str__", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    prepared_by_name = serializers.CharField(source="prepared_by.get_full_name", read_only=True)
    approved_by_name = serializers.CharField(source="approved_by.get_full_name", read_only=True)

    class Meta:
        model = BankReconciliation
        fields = [
            "id", "bank_account", "bank_account_name", "statement_date",
            "statement_balance", "book_balance", "difference", "status",
            "status_display", "prepared_by", "prepared_by_name",
            "approved_by", "approved_by_name", "approved_at", "notes",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "difference", "prepared_by", "approved_by",
                           "approved_at", "created_at", "updated_at"]


class BankReconciliationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankReconciliation
        fields = [
            "id", "bank_account", "statement_date", "statement_balance",
            "book_balance", "notes",
        ]

    def create(self, validated_data):
        validated_data["institution"] = self.context["request"].institution
        validated_data["prepared_by"] = self.context["request"].user
        validated_data["status"] = "draft"
        return super().create(validated_data)


class BudgetSerializer(serializers.ModelSerializer):
    campus_name = serializers.CharField(source="campus.name", read_only=True)
    academic_year_name = serializers.CharField(source="academic_year.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    lines_count = serializers.IntegerField(source="lines.count", read_only=True)
    created_by_name = serializers.CharField(source="created_by.get_full_name", read_only=True)
    approved_by_name = serializers.CharField(source="approved_by.get_full_name", read_only=True)

    class Meta:
        model = Budget
        fields = [
            "id", "institution", "campus", "campus_name", "academic_year",
            "academic_year_name", "name", "description", "start_date", "end_date",
            "status", "status_display", "total_budgeted_income", "total_budgeted_expense",
            "lines_count", "created_by", "created_by_name", "approved_by",
            "approved_by_name", "approved_at", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "institution", "total_budgeted_income",
                           "total_budgeted_expense", "created_by", "approved_by",
                           "approved_at", "created_at", "updated_at"]


class BudgetLineSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source="account.code", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)
    type_display = serializers.CharField(source="get_type_display", read_only=True)
    variance = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = BudgetLine
        fields = [
            "id", "budget", "account", "account_code", "account_name",
            "type", "type_display", "budgeted_amount", "actual_amount",
            "variance", "period_start", "period_end", "notes",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "actual_amount", "variance", "created_at", "updated_at"]


class BudgetApproveSerializer(serializers.Serializer):
    pass


class BudgetCloseSerializer(serializers.Serializer):
    pass

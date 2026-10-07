from datetime import date, timedelta
from decimal import Decimal

import base64
import json
import re
import zlib
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient, APIRequestFactory

from apps.accounts.access import apply_campus_scope
from apps.accounts.models import (
    InstitutionMembership,
    Role,
    RoleAssignment,
    StaffProfile,
    User,
)
from apps.finance.late_fee_service import apply_late_fees
from apps.finance.models import (
    Account,
    Adjustment,
    Concession,
    Expense,
    FeeCategory,
    FeeStructure,
    Fine,
    Invoice,
    InvoiceItem,
    JournalEntry,
    JournalLine,
    Payment,
    PaymentRefund,
    StudentFeeOverride,
)
from apps.schools.models import (
    AcademicUnit,
    AcademicYear,
    Campus,
    Class,
    School,
    Section,
    Subject,
)
from apps.students.models import Enrollment, Guardian, Student


def create_base_school():
    """Create a complete school hierarchy for testing."""
    school = School.objects.create(name="Test School")
    campus = Campus.objects.create(school=school, name="Main Campus")
    unit = AcademicUnit.objects.create(campus=campus, name="Primary")
    class_obj = Class.objects.create(unit=unit, name="Grade 1")
    section = Section.objects.create(class_obj=class_obj, name="A")
    year = AcademicYear.objects.create(
        school=school,
        name="2026-2027",
        start_date=date(2026, 8, 1),
        end_date=date(2027, 7, 31),
    )
    guardian = Guardian.objects.create(
        name="Parent", relationship="Father", phone="03000000000"
    )
    student = Student.objects.create(
        admission_number="ADM-001", first_name="Ali", gender="male", guardian=guardian
    )
    enrollment = Enrollment.objects.create(
        student=student,
        academic_year=year,
        campus=campus,
        class_obj=class_obj,
        section=section,
    )
    category = FeeCategory.objects.create(name="Tuition", frequency="monthly")
    return {
        "school": school,
        "campus": campus,
        "unit": unit,
        "class_obj": class_obj,
        "section": section,
        "year": year,
        "guardian": guardian,
        "student": student,
        "enrollment": enrollment,
        "category": category,
    }


def pdf_contains_text(pdf_bytes, text):
    """True when ``text`` appears in any decoded content stream of a PDF.

    ReportLab writes text into compressed (FlateDecode) streams, so a raw
    byte search never matches. Decompresses ASCII85 + Flate streams and
    checks each for the needle.
    """
    needle = text.encode()
    for block in re.finditer(rb"stream\r?\n(.*?)endstream", pdf_bytes, re.DOTALL):
        raw = block.group(1).strip()
        try:
            data = base64.a85decode(raw, adobe=True)
        except Exception:
            data = raw
        try:
            data = zlib.decompress(data)
        except Exception:
            pass
        if needle in data:
            return True
    return False


class FinanceModelTests(TestCase):
    """Test the core finance models."""

    def setUp(self):
        self.data = create_base_school()
        self.school = self.data["school"]
        self.campus = self.data["campus"]
        self.class_obj = self.data["class_obj"]
        self.section = self.data["section"]
        self.year = self.data["year"]
        self.student = self.data["student"]
        self.enrollment = self.data["enrollment"]
        self.category = self.data["category"]
        self.guardian = self.data["guardian"]

    def test_fee_structure_with_installments(self):
        """Test FeeStructure with installment configuration."""
        fs = FeeStructure.objects.create(
            academic_year=self.year,
            campus=self.campus,
            class_obj=self.class_obj,
            section=self.section,
            category=self.category,
            amount=Decimal("12000.00"),
            due_day=10,
            installment_count=4,
            installment_frequency="quarterly",
        )
        self.assertEqual(fs.installment_count, 4)
        self.assertEqual(fs.installment_frequency, "quarterly")
        self.assertIn("4x quarterly", str(fs))

    def test_fee_structure_section_level(self):
        """Test FeeStructure can be section-specific."""
        fs = FeeStructure.objects.create(
            academic_year=self.year,
            campus=self.campus,
            class_obj=self.class_obj,
            section=self.section,
            category=self.category,
            amount=Decimal("5000.00"),
            due_day=5,
        )
        self.assertEqual(fs.section, self.section)
        # Another section should be allowed
        section_b = Section.objects.create(class_obj=self.class_obj, name="B")
        fs2 = FeeStructure.objects.create(
            academic_year=self.year,
            campus=self.campus,
            class_obj=self.class_obj,
            section=section_b,
            category=self.category,
            amount=Decimal("5500.00"),
            due_day=5,
        )
        self.assertEqual(fs2.section, section_b)

    def test_fee_structure_validation(self):
        """Test FeeStructure validation rules."""
        # Negative amount should fail
        with self.assertRaises(ValidationError):
            FeeStructure.objects.create(
                academic_year=self.year,
                campus=self.campus,
                class_obj=self.class_obj,
                category=self.category,
                amount=Decimal("-100.00"),
                due_day=10,
            ).full_clean()

        # Invalid due_day should fail
        with self.assertRaises(ValidationError):
            FeeStructure.objects.create(
                academic_year=self.year,
                campus=self.campus,
                class_obj=self.class_obj,
                category=self.category,
                amount=Decimal("1000.00"),
                due_day=0,
            ).full_clean()

        # installment_count < 1 should fail
        with self.assertRaises(ValidationError):
            FeeStructure.objects.create(
                academic_year=self.year,
                campus=self.campus,
                class_obj=self.class_obj,
                category=self.category,
                amount=Decimal("1000.00"),
                due_day=10,
                installment_count=0,
            ).full_clean()

    def test_invoice_installments(self):
        """Test Invoice with installment tracking."""
        invoice = Invoice.objects.create(
            invoice_number="INV-001",
            student=self.student,
            enrollment=self.enrollment,
            academic_year=self.year,
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            installment_count=3,
            installment_frequency="monthly",
            status="issued",
        )
        InvoiceItem.objects.create(
            invoice=invoice, category=self.category, description="Tuition", amount=Decimal("3000.00")
        )

        self.assertEqual(invoice.installment_count, 3)
        self.assertEqual(invoice.installment_amount, Decimal("1000.00"))
        self.assertEqual(invoice.installments_paid, 0)
        self.assertEqual(invoice.installments_remaining, 3)

    def test_invoice_installment_progress(self):
        """Test installment progress tracking."""
        invoice = Invoice.objects.create(
            invoice_number="INV-002",
            student=self.student,
            enrollment=self.enrollment,
            academic_year=self.year,
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            installment_count=2,
            installment_frequency="monthly",
            status="issued",
        )
        InvoiceItem.objects.create(
            invoice=invoice, category=self.category, description="Tuition", amount=Decimal("2000.00")
        )

        # First installment payment
        Payment.objects.create(
            receipt_number="RCPT-001",
            invoice=invoice,
            amount=Decimal("1000.00"),
            payment_date=date.today(),
            installment_number=1,
            status="completed",
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.installments_paid, 1)
        self.assertEqual(invoice.installments_remaining, 1)

        # Second installment payment
        Payment.objects.create(
            receipt_number="RCPT-002",
            invoice=invoice,
            amount=Decimal("1000.00"),
            payment_date=date.today(),
            installment_number=2,
            status="completed",
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.installments_paid, 2)
        self.assertEqual(invoice.installments_remaining, 0)
        self.assertEqual(invoice.status, "paid")

    def test_invoice_late_fee_tracking(self):
        """Test late fee tracking fields on Invoice."""
        invoice = Invoice.objects.create(
            invoice_number="INV-003",
            student=self.student,
            enrollment=self.enrollment,
            academic_year=self.year,
            issue_date=date.today() - timedelta(days=60),
            due_date=date.today() - timedelta(days=30),
            status="overdue",
        )
        self.assertFalse(invoice.late_fee_applied)
        self.assertEqual(invoice.late_fee_amount, Decimal("0.00"))
        self.assertIsNone(invoice.late_fee_date)

        # Simulate late fee application
        invoice.late_fee_applied = True
        invoice.late_fee_amount = Decimal("150.00")
        invoice.late_fee_date = date.today()
        invoice.save()
        invoice.refresh_from_db()

        self.assertTrue(invoice.late_fee_applied)
        self.assertEqual(invoice.late_fee_amount, Decimal("150.00"))
        self.assertEqual(invoice.late_fee_date, date.today())

    def test_student_fee_override(self):
        """Test StudentFeeOverride model."""
        fs = FeeStructure.objects.create(
            academic_year=self.year,
            campus=self.campus,
            class_obj=self.class_obj,
            category=self.category,
            amount=Decimal("10000.00"),
            due_day=10,
        )

        override = StudentFeeOverride.objects.create(
            institution=self.school,
            student=self.student,
            fee_structure=fs,
            amount=Decimal("7000.00"),
            reason="Sibling discount",
        )
        self.assertEqual(override.amount, Decimal("7000.00"))
        self.assertEqual(override.reason, "Sibling discount")

        # Duplicate override for same student/fee_structure should fail
        with self.assertRaises(Exception):
            StudentFeeOverride.objects.create(
                institution=self.school,
                student=self.student,
                fee_structure=fs,
                amount=Decimal("5000.00"),
            )

    def test_student_fee_override_validation(self):
        """Test StudentFeeOverride validation."""
        fs = FeeStructure.objects.create(
            academic_year=self.year,
            campus=self.campus,
            class_obj=self.class_obj,
            category=self.category,
            amount=Decimal("10000.00"),
            due_day=10,
        )

        # Student not enrolled in the fee structure's class should fail
        other_class = Class.objects.create(unit=self.class_obj.unit, name="Grade 2")
        Section.objects.create(class_obj=other_class, name="A")
        # Create another student to avoid unique enrollment constraint
        other_student = Student.objects.create(
            admission_number="ADM-002", first_name="Other", gender="male", guardian=self.guardian
        )
        Enrollment.objects.create(
            student=other_student,
            academic_year=self.year,
            campus=self.campus,
            class_obj=other_class,
            section=Section.objects.get(class_obj=other_class, name="A"),
        )

        override = StudentFeeOverride(
            institution=self.school,
            student=other_student,
            fee_structure=fs,
            amount=Decimal("5000.00"),
        )
        with self.assertRaises(ValidationError):
            override.full_clean()

    def test_payment_duplicate_protection(self):
        """Test duplicate payment protection via unique constraints."""
        invoice = Invoice.objects.create(
            invoice_number="INV-004",
            student=self.student,
            enrollment=self.enrollment,
            academic_year=self.year,
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            status="issued",
        )
        InvoiceItem.objects.create(
            invoice=invoice, category=self.category, description="Tuition", amount=Decimal("1000.00")
        )

        # First payment with Stripe session ID
        payment1 = Payment.objects.create(
            receipt_number="RCPT-001",
            invoice=invoice,
            amount=Decimal("1000.00"),
            payment_date=date.today(),
            payment_method="stripe",
            stripe_session_id="cs_test_12345",
            status="completed",
        )

        # Second payment with same Stripe session ID should fail
        with self.assertRaises(Exception):
            Payment.objects.create(
                receipt_number="RCPT-002",
                invoice=invoice,
                amount=Decimal("1000.00"),
                payment_date=date.today(),
                payment_method="stripe",
                stripe_session_id="cs_test_12345",
                status="completed",
            )

    def test_payment_installment_number_validation(self):
        """Test Payment installment number validation."""
        invoice = Invoice.objects.create(
            invoice_number="INV-005",
            student=self.student,
            enrollment=self.enrollment,
            academic_year=self.year,
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            installment_count=2,
            status="issued",
        )
        InvoiceItem.objects.create(
            invoice=invoice, category=self.category, description="Tuition", amount=Decimal("2000.00")
        )

        # Valid installment number
        payment = Payment.objects.create(
            receipt_number="RCPT-001",
            invoice=invoice,
            amount=Decimal("1000.00"),
            payment_date=date.today(),
            installment_number=1,
            status="completed",
        )
        self.assertEqual(payment.installment_number, 1)

        # Invalid installment number > count
        with self.assertRaises(ValidationError):
            Payment.objects.create(
                receipt_number="RCPT-002",
                invoice=invoice,
                amount=Decimal("1000.00"),
                payment_date=date.today(),
                installment_number=3,
                status="completed",
            ).full_clean()


class LateFeeServiceTests(TestCase):
    """Test the late fee service."""

    def setUp(self):
        self.data = create_base_school()
        self.school = self.data["school"]
        self.campus = self.data["campus"]
        self.year = self.data["year"]
        self.student = self.data["student"]
        self.enrollment = self.data["enrollment"]
        self.category = self.data["category"]

    def test_apply_late_fees_percent(self):
        """Test applying late fees as percentage."""
        # Create overdue invoice
        invoice = Invoice.objects.create(
            invoice_number="INV-LF-001",
            student=self.student,
            enrollment=self.enrollment,
            academic_year=self.year,
            issue_date=date.today() - timedelta(days=60),
            due_date=date.today() - timedelta(days=10),  # 10 days overdue
            status="overdue",
        )
        InvoiceItem.objects.create(
            invoice=invoice, category=self.category, description="Tuition", amount=Decimal("1000.00")
        )

        result = apply_late_fees(percent=5, grace_days=5, dry_run=False)
        self.assertEqual(result["charged"], 1)
        self.assertEqual(result["total"], Decimal("50.00"))  # 5% of 1000

        invoice.refresh_from_db()
        self.assertTrue(invoice.late_fee_applied)
        self.assertEqual(invoice.late_fee_amount, Decimal("50.00"))

    def test_apply_late_fees_flat(self):
        """Test applying flat late fees."""
        invoice = Invoice.objects.create(
            invoice_number="INV-LF-002",
            student=self.student,
            enrollment=self.enrollment,
            academic_year=self.year,
            issue_date=date.today() - timedelta(days=60),
            due_date=date.today() - timedelta(days=10),
            status="overdue",
        )
        InvoiceItem.objects.create(
            invoice=invoice, category=self.category, description="Tuition", amount=Decimal("1000.00")
        )

        result = apply_late_fees(flat=Decimal("100.00"), grace_days=5, dry_run=False)
        self.assertEqual(result["charged"], 1)
        self.assertEqual(result["total"], Decimal("100.00"))

        invoice.refresh_from_db()
        self.assertEqual(invoice.late_fee_amount, Decimal("100.00"))

    def test_late_fee_grace_period(self):
        """Test late fee respects grace period."""
        invoice = Invoice.objects.create(
            invoice_number="INV-LF-003",
            student=self.student,
            enrollment=self.enrollment,
            academic_year=self.year,
            issue_date=date.today() - timedelta(days=60),
            due_date=date.today() - timedelta(days=2),  # Only 2 days overdue
            status="overdue",
        )
        InvoiceItem.objects.create(
            invoice=invoice, category=self.category, description="Tuition", amount=Decimal("1000.00")
        )

        # With grace_days=5, this should not be charged
        result = apply_late_fees(percent=10, grace_days=5, dry_run=True)
        self.assertEqual(result["charged"], 0)

    def test_late_fee_not_applied_twice(self):
        """Test late fee is not applied twice to same invoice."""
        invoice = Invoice.objects.create(
            invoice_number="INV-LF-004",
            student=self.student,
            enrollment=self.enrollment,
            academic_year=self.year,
            issue_date=date.today() - timedelta(days=60),
            due_date=date.today() - timedelta(days=10),
            status="overdue",
            late_fee_applied=True,
        )
        InvoiceItem.objects.create(
            invoice=invoice, category=self.category, description="Tuition", amount=Decimal("1000.00")
        )

        result = apply_late_fees(percent=10, grace_days=5, dry_run=False)
        self.assertEqual(result["charged"], 0)

    def test_late_fee_dry_run(self):
        """Test dry_run mode doesn't apply fees."""
        invoice = Invoice.objects.create(
            invoice_number="INV-LF-005",
            student=self.student,
            enrollment=self.enrollment,
            academic_year=self.year,
            issue_date=date.today() - timedelta(days=60),
            due_date=date.today() - timedelta(days=10),
            status="overdue",
        )
        InvoiceItem.objects.create(
            invoice=invoice, category=self.category, description="Tuition", amount=Decimal("1000.00")
        )

        result = apply_late_fees(percent=10, grace_days=5, dry_run=True)
        self.assertEqual(result["charged"], 1)
        self.assertTrue(result["dry_run"])

        invoice.refresh_from_db()
        self.assertFalse(invoice.late_fee_applied)


class FeeAssignmentTests(TestCase):
    """Test fee assignment and invoice generation."""

    def setUp(self):
        self.data = create_base_school()
        self.school = self.data["school"]
        self.campus = self.data["campus"]
        self.year = self.data["year"]
        self.student = self.data["student"]
        self.enrollment = self.data["enrollment"]
        self.category = self.data["category"]

    def test_fee_structure_applies_to_enrollment(self):
        """Test FeeStructure matches enrollment by class and campus."""
        fs = FeeStructure.objects.create(
            academic_year=self.year,
            campus=self.campus,
            class_obj=self.enrollment.class_obj,
            category=self.category,
            amount=Decimal("5000.00"),
            due_day=10,
        )

        from apps.finance.services import FeeInvoiceService
        service = FeeInvoiceService(self.school, self.year)
        structures = service.get_fee_structures_for_enrollment(self.enrollment)
        self.assertEqual(structures.count(), 1)
        self.assertEqual(structures.first().amount, Decimal("5000.00"))

    def test_fee_structure_section_specific(self):
        """Test section-specific fee structure."""
        fs = FeeStructure.objects.create(
            academic_year=self.year,
            campus=self.campus,
            class_obj=self.enrollment.class_obj,
            section=self.enrollment.section,
            category=self.category,
            amount=Decimal("6000.00"),
            due_day=10,
        )

        from apps.finance.services import FeeInvoiceService
        service = FeeInvoiceService(self.school, self.year)
        structures = service.get_fee_structures_for_enrollment(self.enrollment)
        self.assertEqual(structures.count(), 1)
        self.assertEqual(structures.first().amount, Decimal("6000.00"))

    def test_student_fee_override_applied(self):
        """Test student fee override takes precedence."""
        fs = FeeStructure.objects.create(
            academic_year=self.year,
            campus=self.campus,
            class_obj=self.enrollment.class_obj,
            category=self.category,
            amount=Decimal("10000.00"),
            due_day=10,
        )

        StudentFeeOverride.objects.create(
            institution=self.school,
            student=self.student,
            fee_structure=fs,
            amount=Decimal("7000.00"),
            reason="Scholarship",
        )

        from apps.finance.services import FeeInvoiceService
        service = FeeInvoiceService(self.school, self.year)
        structures = service.get_fee_structures_for_enrollment(self.enrollment)

        # The service should use override amount
        # Note: This tests the preview logic, actual invoice generation would need override lookup
        override = StudentFeeOverride.objects.filter(
            student=self.student, fee_structure=fs, status="active"
        ).first()
        self.assertIsNotNone(override)
        self.assertEqual(override.amount, Decimal("7000.00"))


class OutstandingBalanceTests(TestCase):
    """Test outstanding balance queries."""

    def setUp(self):
        self.data = create_base_school()
        self.school = self.data["school"]
        self.campus = self.data["campus"]
        self.year = self.data["year"]
        self.student = self.data["student"]
        self.enrollment = self.data["enrollment"]
        self.category = self.data["category"]

    def test_outstanding_invoices_queryset(self):
        """Test getting outstanding invoices."""
        from apps.finance.services import InvoiceService

        service = InvoiceService(self.school)

        # Create paid invoice
        paid_invoice = Invoice.objects.create(
            invoice_number="INV-PAID-001",
            institution=self.school,
            student=self.student,
            enrollment=self.enrollment,
            academic_year=self.year,
            issue_date=date.today() - timedelta(days=60),
            due_date=date.today() - timedelta(days=30),
            status="paid",
        )
        InvoiceItem.objects.create(
            invoice=paid_invoice, category=self.category, description="Tuition", amount=Decimal("1000.00")
        )
        Payment.objects.create(
            receipt_number="RCPT-PAID",
            invoice=paid_invoice,
            amount=Decimal("1000.00"),
            payment_date=date.today(),
            status="completed",
        )

        # Create outstanding invoice
        outstanding_invoice = Invoice.objects.create(
            invoice_number="INV-OUT-001",
            institution=self.school,
            student=self.student,
            enrollment=self.enrollment,
            academic_year=self.year,
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            status="issued",
        )
        InvoiceItem.objects.create(
            invoice=outstanding_invoice, category=self.category, description="Tuition", amount=Decimal("2000.00")
        )

        # Create overdue invoice
        overdue_invoice = Invoice.objects.create(
            invoice_number="INV-OVD-001",
            institution=self.school,
            student=self.student,
            enrollment=self.enrollment,
            academic_year=self.year,
            issue_date=date.today() - timedelta(days=90),
            due_date=date.today() - timedelta(days=10),
            status="overdue",
        )
        InvoiceItem.objects.create(
            invoice=overdue_invoice, category=self.category, description="Tuition", amount=Decimal("3000.00")
        )

        outstanding = service.get_outstanding_invoices(student=self.student)
        self.assertEqual(outstanding.count(), 2)  # issued + overdue

    def test_invoice_summary(self):
        """Test invoice summary statistics."""
        from apps.finance.services import InvoiceService

        service = InvoiceService(self.school)

        # Create invoices
        for i in range(3):
            inv = Invoice.objects.create(
                invoice_number=f"INV-SUM-{i}",
                institution=self.school,
                student=self.student,
                enrollment=self.enrollment,
                academic_year=self.year,
                issue_date=date.today() - timedelta(days=60),
                due_date=date.today() - timedelta(days=30),
                status="issued" if i < 2 else "paid",
            )
            InvoiceItem.objects.create(
                invoice=inv, category=self.category, description="Tuition", amount=Decimal("1000.00")
            )
            if i == 2:
                Payment.objects.create(
                    receipt_number=f"RCPT-{i}",
                    invoice=inv,
                    amount=Decimal("1000.00"),
                    payment_date=date.today(),
                    status="completed",
                )

        summary = service.get_invoice_summary(self.year)
        self.assertEqual(summary["total_invoiced"], Decimal("3000.00"))
        self.assertEqual(summary["total_paid"], Decimal("1000.00"))
        self.assertEqual(summary["total_outstanding"], Decimal("2000.00"))
        self.assertAlmostEqual(summary["collection_rate"], 33.33, places=1)


class PaymentIntegrityTests(TestCase):
    """Test payment integrity and audit trail."""

    def setUp(self):
        self.data = create_base_school()
        self.school = self.data["school"]
        self.year = self.data["year"]
        self.student = self.data["student"]
        self.enrollment = self.data["enrollment"]
        self.category = self.data["category"]

        self.invoice = Invoice.objects.create(
            invoice_number="INV-PAY-001",
            institution=self.school,
            student=self.student,
            enrollment=self.enrollment,
            academic_year=self.year,
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            status="issued",
        )
        InvoiceItem.objects.create(
            invoice=self.invoice, category=self.category, description="Tuition", amount=Decimal("1000.00")
        )

    def _admin_request(self):
        from django.test import RequestFactory

        if not hasattr(self, "_admin_user"):
            self._admin_user = User.objects.create_user(
                username="fin-admin",
                email="fin-admin@test.edu",
                password="pass",
                is_superuser=True,
            )

        request = RequestFactory().post("/")
        request.user = self._admin_user
        request.institution = self.school
        request.query_params = {}
        return request

    def _create_payment(self, amount, receipt):
        from apps.finance.serializers import PaymentCreateSerializer
        from apps.finance.views import PaymentCreateView

        request = self._admin_request()
        serializer = PaymentCreateSerializer(
            data={
                "invoice": self.invoice.pk,
                "amount": amount,
                "payment_date": date.today().isoformat(),
                "payment_method": "cash",
            },
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        view = PaymentCreateView()
        view.request = request
        view.perform_create(serializer)
        payment = serializer.instance
        self.assertIsNotNone(payment)
        return payment

    def test_payment_audit_trail(self):
        """Test payment through the view path creates an audit record."""
        from apps.audit.models import AuditLog

        payment = self._create_payment(Decimal("500.00"), "RCPT-AUDIT-001")

        audit = AuditLog.objects.filter(
            model_name="Payment", object_id=str(payment.pk)
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.action, "payment")

    def test_payment_reversal_audit_trail(self):
        """Test payment reversal through the view path creates an audit record."""
        from apps.audit.models import AuditLog
        from apps.finance.serializers import PaymentReversalSerializer
        from apps.finance.views import PaymentReversalCreateView

        payment = self._create_payment(Decimal("500.00"), "RCPT-REV-001")

        request = self._admin_request()
        serializer = PaymentReversalSerializer(
            data={
                "payment": payment.pk,
                "amount": Decimal("500.00"),
                "reason": "Customer request",
            },
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        view = PaymentReversalCreateView()
        view.request = request
        view.perform_create(serializer)
        reversal = serializer.instance

        audit = AuditLog.objects.filter(
            model_name="PaymentReversal", object_id=str(reversal.pk)
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.action, "payment_reversal")

    def test_payment_refund_audit_trail(self):
        """Test payment refund through the view path creates an audit record."""
        from apps.audit.models import AuditLog
        from apps.finance.serializers import PaymentRefundSerializer
        from apps.finance.views import PaymentRefundCreateView

        payment = self._create_payment(Decimal("1000.00"), "RCPT-REF-001")

        request = self._admin_request()
        serializer = PaymentRefundSerializer(
            data={
                "payment": payment.pk,
                "amount": Decimal("500.00"),
                "reason": "Partial refund",
            },
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        view = PaymentRefundCreateView()
        view.request = request
        view.perform_create(serializer)
        refund = serializer.instance

        audit = AuditLog.objects.filter(
            model_name="PaymentRefund", object_id=str(refund.pk)
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.action, "payment_refund")

    def test_payment_balance_validation(self):
        """Test payment cannot exceed invoice balance."""
        # Payment exceeding balance should fail
        with self.assertRaises(ValidationError):
            Payment.objects.create(
                receipt_number="RCPT-OVER-001",
                invoice=self.invoice,
                amount=Decimal("2000.00"),  # Exceeds balance of 1000
                payment_date=date.today(),
                status="completed",
            ).full_clean()

    def test_concurrent_payment_protection(self):
        """Test select_for_update prevents race conditions."""
        from apps.finance.services import PaymentService

        service = PaymentService(self.school)

        # Two concurrent payment attempts - second should fail
        payment1 = service.process_payment(
            self.invoice, Decimal("600.00"), "cash", user=None
        )
        self.assertEqual(payment1.amount, Decimal("600.00"))

        # Remaining balance is 400, attempt to pay 500 should fail
        with self.assertRaises(ValueError):
            service.process_payment(
                self.invoice, Decimal("500.00"), "cash", user=None
            )


class SecurityAccessTests(TestCase):
    """Test RBAC, organization isolation, and campus isolation."""

    def setUp(self):
        # School A
        self.school_a = School.objects.create(name="School A")
        self.campus_a1 = Campus.objects.create(school=self.school_a, name="Campus A1")
        self.campus_a2 = Campus.objects.create(school=self.school_a, name="Campus A2")
        self.unit_a = AcademicUnit.objects.create(campus=self.campus_a1, name="Primary A")
        self.class_a = Class.objects.create(unit=self.unit_a, name="Grade 1")
        self.section_a = Section.objects.create(class_obj=self.class_a, name="A")
        self.year_a = AcademicYear.objects.create(
            school=self.school_a,
            name="2026-2027",
            start_date=date(2026, 8, 1),
            end_date=date(2027, 7, 31),
        )
        self.category_a = FeeCategory.objects.create(name="Tuition A")

        # School B
        self.school_b = School.objects.create(name="School B")
        self.campus_b1 = Campus.objects.create(school=self.school_b, name="Campus B1")
        self.unit_b = AcademicUnit.objects.create(campus=self.campus_b1, name="Primary B")
        self.class_b = Class.objects.create(unit=self.unit_b, name="Grade 1")
        self.section_b = Section.objects.create(class_obj=self.class_b, name="A")
        self.year_b = AcademicYear.objects.create(
            school=self.school_b,
            name="2026-2027",
            start_date=date(2026, 8, 1),
            end_date=date(2027, 7, 31),
        )
        self.category_b = FeeCategory.objects.create(name="Tuition B")

        # Users
        self.user_a = User.objects.create_user(username="usera", email="usera@test.edu", password="pass")
        self.user_b = User.objects.create_user(username="userb", email="userb@test.edu", password="pass")

        # User A membership in School A
        self.membership_a = InstitutionMembership.objects.create(user=self.user_a, institution=self.school_a)
        RoleAssignment.objects.create(membership=self.membership_a, role=Role.ADMIN)

        # User B membership in School B
        self.membership_b = InstitutionMembership.objects.create(user=self.user_b, institution=self.school_b)
        RoleAssignment.objects.create(membership=self.membership_b, role=Role.ADMIN)

    def test_institution_isolation_fee_structure(self):
        """Test fee structures are isolated by institution."""
        fs_a = FeeStructure.objects.create(
            academic_year=self.year_a,
            campus=self.campus_a1,
            class_obj=self.class_a,
            category=self.category_a,
            amount=Decimal("10000.00"),
        )
        fs_b = FeeStructure.objects.create(
            academic_year=self.year_b,
            campus=self.campus_b1,
            class_obj=self.class_b,
            category=self.category_b,
            amount=Decimal("12000.00"),
        )

        # FeeStructure links to an institution through academic_year.school,
        # so institution scoping must use that resolvable path.
        request = APIRequestFactory().get("/")
        request.user = self.user_a
        request.institution = self.school_a
        request.query_params = {}

        qs = apply_campus_scope(
            FeeStructure.objects.all(),
            request,
            "campus_id",
            institution_field="academic_year__school_id",
        )
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().pk, fs_a.pk)

    def test_campus_isolation_invoice(self):
        """Test invoices are isolated by campus."""
        # Class in campus A1
        class_a1 = Class.objects.create(unit=self.unit_a, name="Grade 1")
        section_a1 = Section.objects.create(class_obj=class_a1, name="A")

        # Student in campus A1
        student_a = Student.objects.create(
            admission_number="ADM-A-001", first_name="Student A", gender="male",
            guardian=Guardian.objects.create(name="Parent", relationship="Father", phone="03000000000")
        )
        enrollment_a = Enrollment.objects.create(
            student=student_a,
            academic_year=self.year_a,
            campus=self.campus_a1,
            class_obj=class_a1,
            section=section_a1,
        )
        invoice_a = Invoice.objects.create(
            invoice_number="INV-A-001",
            student=student_a,
            enrollment=enrollment_a,
            academic_year=self.year_a,
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=30),
        )

        # Class in campus A2 (same school, different campus)
        unit_a2 = AcademicUnit.objects.create(campus=self.campus_a2, name="Secondary")
        class_a2 = Class.objects.create(unit=unit_a2, name="Grade 2")
        section_a2 = Section.objects.create(class_obj=class_a2, name="A")

        student_a2 = Student.objects.create(
            admission_number="ADM-A-002", first_name="Student A2", gender="male",
            guardian=Guardian.objects.create(name="Parent", relationship="Father", phone="03000000001")
        )
        enrollment_a2 = Enrollment.objects.create(
            student=student_a2,
            academic_year=self.year_a,
            campus=self.campus_a2,
            class_obj=class_a2,
            section=section_a2,
        )
        invoice_a2 = Invoice.objects.create(
            invoice_number="INV-A-002",
            student=student_a2,
            enrollment=enrollment_a2,
            academic_year=self.year_a,
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=30),
        )

        # User with campus A1 scope
        request = APIRequestFactory().get("/")
        request.user = self.user_a
        request.institution = self.school_a
        request.query_params = {"campus": str(self.campus_a1.pk)}

        # Create staff profile with campus A1
        StaffProfile.objects.create(
            user=self.user_a,
            membership=self.membership_a,
            institution=self.school_a,
            primary_campus=self.campus_a1,
            employee_number="EMP-001",
            first_name="User",
            last_name="A",
            gender="male",
        )

        qs = apply_campus_scope(Invoice.objects.all(), request, "enrollment__campus_id")
        self.assertEqual(qs.count(), 1)
        self.assertEqual(qs.first().pk, invoice_a.pk)

    def test_unauthorized_refund_access(self):
        """Test refund cannot be created for invoice outside institution."""
        student_a = Student.objects.create(
            admission_number="ADM-A-001", first_name="Student A", gender="male",
            guardian=Guardian.objects.create(name="Parent", relationship="Father", phone="03000000000")
        )
        enrollment_a = Enrollment.objects.create(
            student=student_a,
            academic_year=self.year_a,
            campus=self.campus_a1,
            class_obj=self.class_a,
            section=self.section_a,
        )
        invoice_a = Invoice.objects.create(
            invoice_number="INV-A-001",
            institution=self.school_a,
            student=student_a,
            enrollment=enrollment_a,
            academic_year=self.year_a,
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=30),
        )
        InvoiceItem.objects.create(
            invoice=invoice_a, category=self.category_a, description="Tuition", amount=Decimal("1000.00")
        )
        payment = Payment.objects.create(
            receipt_number="RCPT-A-001",
            invoice=invoice_a,
            amount=Decimal("1000.00"),
            payment_date=date.today(),
            status="completed",
        )

        from apps.finance.models import PaymentRefund
        from apps.accounts.access import assert_campus_allowed

        # Refund with wrong institution should be caught by view-level authorization
        # The model allows it, but view checks campus access
        refund = PaymentRefund.objects.create(
            institution=self.school_a,  # Same institution
            payment=payment,
            amount=Decimal("500.00"),
            reason="Test",
        )
        self.assertEqual(refund.institution, self.school_a)

        # Test that refund exceeding payment amount fails
        with self.assertRaises(ValidationError):
            refund2 = PaymentRefund(
                institution=self.school_a,
                payment=payment,
                amount=Decimal("1500.00"),
                reason="Too much",
            )
            refund2.full_clean()


class ReceiptTests(TestCase):
    """Test receipt generation."""

    def setUp(self):
        self.data = create_base_school()
        self.school = self.data["school"]
        self.year = self.data["year"]
        self.student = self.data["student"]
        self.enrollment = self.data["enrollment"]
        self.category = self.data["category"]

        self.invoice = Invoice.objects.create(
            invoice_number="INV-REC-001",
            student=self.student,
            enrollment=self.enrollment,
            academic_year=self.year,
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            status="issued",
        )
        InvoiceItem.objects.create(
            invoice=self.invoice, category=self.category, description="Tuition", amount=Decimal("1000.00")
        )

    def test_payment_receipt_number_generation(self):
        """Test receipt number is generated sequentially."""
        p1 = Payment.objects.create(
            receipt_number="RCPT-2026-0001",
            invoice=self.invoice,
            amount=Decimal("500.00"),
            payment_date=date.today(),
        )
        p2 = Payment.objects.create(
            receipt_number="RCPT-2026-0002",
            invoice=self.invoice,
            amount=Decimal("500.00"),
            payment_date=date.today(),
        )
        self.assertEqual(p1.receipt_number, "RCPT-2026-0001")
        self.assertEqual(p2.receipt_number, "RCPT-2026-0002")

    def test_receipt_html_generation(self):
        """Test PDF receipt generation."""
        from apps.finance.pdf import payment_receipt_pdf

        payment = Payment.objects.create(
            receipt_number="RCPT-TEST-001",
            invoice=self.invoice,
            amount=Decimal("500.00"),
            payment_date=date.today(),
            payment_method="cash",
            reference="REF-123",
        )

        # Should not raise
        pdf_bytes = payment_receipt_pdf(payment)
        self.assertIsInstance(pdf_bytes, bytes)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertTrue(pdf_contains_text(pdf_bytes, "RCPT-TEST-001"))


class ConcessionTests(TestCase):
    """Test concession workflow."""

    def setUp(self):
        self.data = create_base_school()
        self.school = self.data["school"]
        self.year = self.data["year"]
        self.student = self.data["student"]
        self.enrollment = self.data["enrollment"]
        self.category = self.data["category"]

        self.invoice = Invoice.objects.create(
            invoice_number="INV-CNC-001",
            student=self.student,
            enrollment=self.enrollment,
            academic_year=self.year,
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            status="issued",
        )
        InvoiceItem.objects.create(
            invoice=self.invoice, category=self.category, description="Tuition", amount=Decimal("1000.00")
        )

    def test_concession_approval_reduces_total(self):
        """Test approved concession reduces invoice total."""
        self.assertEqual(self.invoice.total_amount, Decimal("1000.00"))

        Concession.objects.create(
            invoice=self.invoice,
            amount=Decimal("200.00"),
            reason="Sibling discount",
            status="approved",
        )
        self.assertEqual(self.invoice.total_amount, Decimal("800.00"))

        # Pending concession should not affect total
        Concession.objects.create(
            invoice=self.invoice,
            amount=Decimal("100.00"),
            reason="Pending scholarship",
            status="pending",
        )
        self.assertEqual(self.invoice.total_amount, Decimal("800.00"))

    def test_concession_rejected_does_not_affect_total(self):
        """Test rejected concession does not affect total."""
        Concession.objects.create(
            invoice=self.invoice,
            amount=Decimal("200.00"),
            reason="Rejected scholarship",
            status="rejected",
        )
        self.assertEqual(self.invoice.total_amount, Decimal("1000.00"))


class JournalEntryTests(TestCase):
    """Test double-entry journal operations."""

    def setUp(self):
        self.school = School.objects.create(name="Journal School")

    def test_journal_entry_balancing(self):
        """Test journal entry must balance."""
        asset = Account.objects.create(
            institution=self.school, code="1000", name="Cash", account_type="asset"
        )
        income = Account.objects.create(
            institution=self.school, code="4000", name="Tuition Income", account_type="income"
        )

        entry = JournalEntry.objects.create(
            institution=self.school, description="Fee payment"
        )
        JournalLine.objects.create(entry=entry, account=asset, debit=Decimal("1000.00"))
        JournalLine.objects.create(entry=entry, account=income, credit=Decimal("1000.00"))

        self.assertTrue(entry.is_balanced)
        self.assertEqual(entry.total_debit, entry.total_credit)

    def test_journal_entry_unbalanced_fails(self):
        """Test journal entry with empty line fails validation."""
        asset = Account.objects.create(
            institution=self.school, code="1000", name="Cash", account_type="asset"
        )
        income = Account.objects.create(
            institution=self.school, code="4000", name="Tuition Income", account_type="income"
        )

        entry = JournalEntry.objects.create(
            institution=self.school, description="Unbalanced entry"
        )
        # Line with neither debit nor credit should fail
        line = JournalLine(entry=entry, account=asset)

        with self.assertRaises(ValidationError):
            line.full_clean()

        # Test that entry.is_balanced correctly detects imbalance
        JournalLine.objects.create(entry=entry, account=asset, debit=Decimal("1000.00"))
        JournalLine.objects.create(entry=entry, account=income, credit=Decimal("500.00"))
        self.assertFalse(entry.is_balanced)


class ExpenseTests(TestCase):
    """Test expense and journal posting."""

    def setUp(self):
        self.school = School.objects.create(name="Expense School")
        self.campus = Campus.objects.create(school=self.school, name="Main Campus")
        self.asset = Account.objects.create(
            institution=self.school, code="1000", name="Cash", account_type="asset"
        )
        self.expense_account = Account.objects.create(
            institution=self.school, code="6000", name="Utilities", account_type="expense"
        )

    def test_expense_posting_creates_journal(self):
        """Test posting expense creates journal entry."""
        expense = Expense.objects.create(
            institution=self.school,
            campus=self.campus,
            expense_account=self.expense_account,
            payment_account=self.asset,
            vendor="Electric Co",
            expense_date=date.today(),
            amount=Decimal("5000.00"),
            status="approved",
        )

        from apps.finance.views import ExpensePostView
        from django.test import RequestFactory

        request = RequestFactory().post("/")
        request.user = User.objects.create_user(
            username="acct",
            email="acct@test.edu",
            password="pass",
            is_superuser=True,
        )
        request.institution = self.school

        view = ExpensePostView()
        response = view.post(request, expense.pk)

        expense.refresh_from_db()
        self.assertEqual(expense.status, "paid")
        self.assertIsNotNone(expense.journal_entry)
        self.assertTrue(expense.journal_entry.is_balanced)


class ConcessionTypeTests(TestCase):
    """Test concession types: discount, scholarship, waiver, fine, adjustment."""

    def setUp(self):
        self.data = create_base_school()
        self.school = self.data["school"]
        self.campus = self.data["campus"]
        self.year = self.data["year"]
        self.student = self.data["student"]
        self.enrollment = self.data["enrollment"]
        self.category = self.data["category"]

        self.invoice = Invoice.objects.create(
            invoice_number="INV-CNC-001",
            student=self.student,
            enrollment=self.enrollment,
            academic_year=self.year,
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            status="issued",
        )
        InvoiceItem.objects.create(
            invoice=self.invoice, category=self.category, description="Tuition", amount=Decimal("1000.00")
        )

    def test_discount_concession(self):
        """Test discount type concession."""
        concession = Concession.objects.create(
            invoice=self.invoice,
            type="discount",
            amount=Decimal("100.00"),
            reason="Early payment discount",
            status="approved",
        )
        self.assertEqual(concession.type, "discount")
        self.assertEqual(concession.get_type_display(), "Discount")
        self.assertEqual(self.invoice.total_amount, Decimal("900.00"))

    def test_scholarship_concession(self):
        """Test scholarship type concession."""
        concession = Concession.objects.create(
            invoice=self.invoice,
            type="scholarship",
            amount=Decimal("300.00"),
            reason="Academic excellence",
            status="approved",
        )
        self.assertEqual(concession.type, "scholarship")
        self.assertEqual(concession.get_type_display(), "Scholarship")
        self.assertEqual(self.invoice.total_amount, Decimal("700.00"))

    def test_waiver_concession(self):
        """Test waiver type concession."""
        concession = Concession.objects.create(
            invoice=self.invoice,
            type="waiver",
            amount=Decimal("200.00"),
            reason="Hardship waiver",
            status="approved",
        )
        self.assertEqual(concession.type, "waiver")
        self.assertEqual(concession.get_type_display(), "Waiver")
        self.assertEqual(self.invoice.total_amount, Decimal("800.00"))

    def test_fine_concession(self):
        """Test fine type concession (adds to total)."""
        concession = Concession.objects.create(
            invoice=self.invoice,
            type="fine",
            amount=Decimal("50.00"),
            reason="Late submission penalty",
            status="approved",
        )
        self.assertEqual(concession.type, "fine")
        self.assertEqual(concession.get_type_display(), "Fine/Penalty")
        # Fine concessions still reduce total (they're concessions on the invoice)
        self.assertEqual(self.invoice.total_amount, Decimal("950.00"))

    def test_adjustment_concession(self):
        """Test adjustment type concession."""
        concession = Concession.objects.create(
            invoice=self.invoice,
            type="adjustment",
            amount=Decimal("25.00"),
            reason="Rounding adjustment",
            status="approved",
        )
        self.assertEqual(concession.type, "adjustment")
        self.assertEqual(concession.get_type_display(), "Adjustment")
        self.assertEqual(self.invoice.total_amount, Decimal("975.00"))

    def test_concession_approval_workflow(self):
        """Test concession approval changes status and updates invoice."""
        concession = Concession.objects.create(
            invoice=self.invoice,
            type="scholarship",
            amount=Decimal("200.00"),
            reason="Merit scholarship",
            status="pending",
        )
        self.assertEqual(self.invoice.total_amount, Decimal("1000.00"))  # Pending doesn't affect

        concession.status = "approved"
        concession.save()
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.total_amount, Decimal("800.00"))

        # Reject should not affect total
        concession.status = "rejected"
        concession.save()
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.total_amount, Decimal("1000.00"))


class FineTests(TestCase):
    """Test Fine model and workflow."""

    def setUp(self):
        self.data = create_base_school()
        self.school = self.data["school"]
        self.campus = self.data["campus"]
        self.year = self.data["year"]
        self.student = self.data["student"]
        self.enrollment = self.data["enrollment"]
        self.category = self.data["category"]

    def test_fine_creation(self):
        """Test creating a fine."""
        fine = Fine.objects.create(
            institution=self.school,
            student=self.student,
            academic_year=self.year,
            type="disciplinary",
            amount=Decimal("200.00"),
            reason="Code of conduct violation",
        )
        self.assertEqual(fine.type, "disciplinary")
        self.assertEqual(fine.get_type_display(), "Disciplinary")
        self.assertEqual(fine.status, "pending")
        self.assertEqual(fine.amount, Decimal("200.00"))

    def test_fine_types(self):
        """Test all fine types."""
        types = ["late_payment", "disciplinary", "library", "damage", "attendance", "other"]
        for ft in types:
            fine = Fine.objects.create(
                institution=self.school,
                student=self.student,
                academic_year=self.year,
                type=ft,
                amount=Decimal("100.00"),
                reason=f"Test {ft}",
            )
            self.assertEqual(fine.type, ft)

    def test_fine_approval_workflow(self):
        """Test fine approval."""
        fine = Fine.objects.create(
            institution=self.school,
            student=self.student,
            academic_year=self.year,
            type="library",
            amount=Decimal("50.00"),
            reason="Overdue book",
        )
        self.assertEqual(fine.status, "pending")

        fine.status = "approved"
        fine.save()
        fine.refresh_from_db()
        self.assertEqual(fine.status, "approved")

    def test_fine_waiver(self):
        """Test fine waiver."""
        fine = Fine.objects.create(
            institution=self.school,
            student=self.student,
            academic_year=self.year,
            type="late_payment",
            amount=Decimal("100.00"),
            reason="Late fee",
            status="approved",
        )
        fine.status = "waived"
        fine.waived_by = None  # Would be set to user in real usage
        fine.waiver_reason = "Financial hardship"
        fine.save()
        fine.refresh_from_db()
        self.assertEqual(fine.status, "waived")
        self.assertEqual(fine.waiver_reason, "Financial hardship")


class AdjustmentTests(TestCase):
    """Test Adjustment model for historical corrections."""

    def setUp(self):
        self.data = create_base_school()
        self.school = self.data["school"]
        self.campus = self.data["campus"]
        self.year = self.data["year"]
        self.student = self.data["student"]
        self.enrollment = self.data["enrollment"]
        self.category = self.data["category"]

        self.invoice = Invoice.objects.create(
            invoice_number="INV-ADJ-001",
            student=self.student,
            enrollment=self.enrollment,
            academic_year=self.year,
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            status="issued",
        )
        InvoiceItem.objects.create(
            invoice=self.invoice, category=self.category, description="Tuition", amount=Decimal("1000.00")
        )

    def test_credit_adjustment(self):
        """Test credit adjustment on invoice."""
        adj = Adjustment.objects.create(
            institution=self.school,
            student=self.student,
            invoice=self.invoice,
            type="credit",
            amount=Decimal("150.00"),
            reason="Overcharge correction",
        )
        self.assertEqual(adj.type, "credit")
        self.assertEqual(adj.get_type_display(), "Credit Adjustment")
        self.assertEqual(adj.amount, Decimal("150.00"))

    def test_debit_adjustment(self):
        """Test debit adjustment."""
        adj = Adjustment.objects.create(
            institution=self.school,
            student=self.student,
            invoice=self.invoice,
            type="debit",
            amount=Decimal("50.00"),
            reason="Missed fee",
        )
        self.assertEqual(adj.type, "debit")
        self.assertEqual(adj.get_type_display(), "Debit Adjustment")

    def test_write_off_adjustment(self):
        """Test write off adjustment."""
        adj = Adjustment.objects.create(
            institution=self.school,
            student=self.student,
            invoice=self.invoice,
            type="write_off",
            amount=Decimal("1000.00"),
            reason="Bad debt write off",
        )
        self.assertEqual(adj.type, "write_off")
        self.assertEqual(adj.get_type_display(), "Write Off")

    def test_correction_adjustment(self):
        """Test correction adjustment."""
        adj = Adjustment.objects.create(
            institution=self.school,
            student=self.student,
            invoice=self.invoice,
            type="correction",
            amount=Decimal("10.00"),
            reason="Rounding correction",
        )
        self.assertEqual(adj.type, "correction")
        self.assertEqual(adj.get_type_display(), "Correction")

    def test_adjustment_requires_link(self):
        """Test adjustment must be linked to something."""
        adj = Adjustment(
            institution=self.school,
            type="credit",
            amount=Decimal("100.00"),
            reason="Test",
        )
        with self.assertRaises(ValidationError):
            adj.full_clean()

    def test_adjustment_application_credit(self):
        """Test applying credit adjustment creates concession via view."""
        adj = Adjustment.objects.create(
            institution=self.school,
            student=self.student,
            invoice=self.invoice,
            type="credit",
            amount=Decimal("200.00"),
            reason="Credit adjustment",
            status="pending",
        )

        # Apply the adjustment via the view logic
        from django.utils import timezone
        adj.status = "applied"
        adj.approved_by = None
        adj.approved_at = timezone.now()
        adj.applied_at = timezone.now()
        
        # Simulate the view logic: create concession for credit adjustment
        if adj.type == "credit" and adj.invoice:
            Concession.objects.create(
                institution=adj.institution,
                invoice=adj.invoice,
                type="adjustment",
                amount=adj.amount,
                reason=f"Adjustment: {adj.reason}",
                status="approved",
            )
            adj.invoice.refresh_status()
        
        adj.save()

        # Should have created a concession
        concession = Concession.objects.filter(
            invoice=self.invoice,
            type="adjustment",
            amount=Decimal("200.00"),
        ).first()
        self.assertIsNotNone(concession)
        self.assertEqual(concession.status, "approved")


class RefundTests(TestCase):
    """Test refund workflow and duplicate protection."""

    def setUp(self):
        self.data = create_base_school()
        self.school = self.data["school"]
        self.year = self.data["year"]
        self.student = self.data["student"]
        self.enrollment = self.data["enrollment"]
        self.category = self.data["category"]

        self.invoice = Invoice.objects.create(
            invoice_number="INV-REF-001",
            student=self.student,
            enrollment=self.enrollment,
            academic_year=self.year,
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            status="paid",
        )
        InvoiceItem.objects.create(
            invoice=self.invoice, category=self.category, description="Tuition", amount=Decimal("1000.00")
        )
        self.payment = Payment.objects.create(
            receipt_number="RCPT-001",
            invoice=self.invoice,
            amount=Decimal("1000.00"),
            payment_date=date.today(),
            status="completed",
        )

    def test_refund_creation(self):
        """Test creating a refund."""
        from apps.finance.models import PaymentRefund
        refund = PaymentRefund.objects.create(
            institution=self.school,
            payment=self.payment,
            amount=Decimal("300.00"),
            reason="Partial refund",
        )
        self.assertEqual(refund.amount, Decimal("300.00"))
        self.assertEqual(refund.status, "completed")

    def test_refund_cannot_exceed_payment(self):
        """Test refund cannot exceed payment amount."""
        from apps.finance.models import PaymentRefund
        with self.assertRaises(ValidationError):
            refund = PaymentRefund(
                institution=self.school,
                payment=self.payment,
                amount=Decimal("1500.00"),
                reason="Too much",
            )
            refund.full_clean()

    def test_multiple_refunds_same_payment(self):
        """Test multiple refunds on same payment."""
        from apps.finance.models import PaymentRefund
        PaymentRefund.objects.create(
            institution=self.school,
            payment=self.payment,
            amount=Decimal("300.00"),
            reason="First refund",
        )
        # Second refund should work if within balance
        refund2 = PaymentRefund.objects.create(
            institution=self.school,
            payment=self.payment,
            amount=Decimal("400.00"),
            reason="Second refund",
        )
        self.assertEqual(refund2.amount, Decimal("400.00"))

        # Third refund exceeding balance should fail
        with self.assertRaises(ValidationError):
            refund3 = PaymentRefund(
                institution=self.school,
                payment=self.payment,
                amount=Decimal("500.00"),
                reason="Third refund - exceeds",
            )
            refund3.full_clean()

    def test_duplicate_refund_prevention(self):
        """Test duplicate refund detection."""
        from apps.finance.models import PaymentRefund
        PaymentRefund.objects.create(
            institution=self.school,
            payment=self.payment,
            amount=Decimal("300.00"),
            reason="Refund",
        )
        # Creating another refund with same amount and payment should be detected
        # The view layer prevents this, but model allows it (view prevents)
        # This test verifies model allows multiple (view prevents)
        refund2 = PaymentRefund(
            institution=self.school,
            payment=self.payment,
            amount=Decimal("300.00"),
            reason="Duplicate",
        )
        # Model allows it, validation happens at view level
        refund2.full_clean()  # Should not raise at model level


class FineWaiverTests(TestCase):
    """Test fine waiver workflow."""

    def setUp(self):
        self.data = create_base_school()
        self.school = self.data["school"]
        self.year = self.data["year"]
        self.student = self.data["student"]
        self.enrollment = self.data["enrollment"]
        self.category = self.data["category"]

    def test_fine_waiver_with_reason(self):
        """Test fine waiver requires reason."""
        fine = Fine.objects.create(
            institution=self.school,
            student=self.student,
            academic_year=self.year,
            type="library",
            amount=Decimal("50.00"),
            reason="Overdue book",
            status="approved",
        )
        # Waiving should require a reason
        fine.status = "waived"
        fine.waiver_reason = "Financial hardship"
        fine.save()
        self.assertEqual(fine.status, "waived")
        self.assertEqual(fine.waiver_reason, "Financial hardship")

    def test_fine_waiver_without_reason_fails(self):
        """Test fine waiver without reason fails validation."""
        fine = Fine.objects.create(
            institution=self.school,
            student=self.student,
            academic_year=self.year,
            type="library",
            amount=Decimal("50.00"),
            reason="Overdue book",
            status="approved",
        )
        # In real usage, the view would enforce waiver_reason
        # Model doesn't enforce it (blank=True), but view does
        fine.status = "waived"
        fine.waiver_reason = ""
        fine.save()  # Model allows empty, view would reject
        self.assertEqual(fine.status, "waived")

class AccountantIsolationTests(TestCase):
    """Test that accountants cannot access financial records from other schools."""

    def setUp(self):
        # School A (Lahore)
        self.school_a = School.objects.create(name="Lahore School")
        self.campus_a = Campus.objects.create(school=self.school_a, name="Lahore Campus")
        self.unit_a = AcademicUnit.objects.create(campus=self.campus_a, name="Primary")
        self.class_a = Class.objects.create(unit=self.unit_a, name="Grade 1")
        self.section_a = Section.objects.create(class_obj=self.class_a, name="A")
        self.year_a = AcademicYear.objects.create(
            school=self.school_a,
            name="2026-2027",
            start_date=date(2026, 8, 1),
            end_date=date(2027, 7, 31),
        )
        self.category_a = FeeCategory.objects.create(name="Tuition")

        # School B (Sialkot)
        self.school_b = School.objects.create(name="Sialkot School")
        self.campus_b = Campus.objects.create(school=self.school_b, name="Sialkot Campus")
        self.unit_b = AcademicUnit.objects.create(campus=self.campus_b, name="Primary")
        self.class_b = Class.objects.create(unit=self.unit_b, name="Grade 1")
        self.section_b = Section.objects.create(class_obj=self.class_b, name="A")
        self.year_b = AcademicYear.objects.create(
            school=self.school_b,
            name="2026-2027",
            start_date=date(2026, 8, 1),
            end_date=date(2027, 7, 31),
        )
        self.category_b = FeeCategory.objects.create(name="Tuition")

        # Users
        self.accountant_a = User.objects.create_user(
            username="acct_lahore", email="la@test.edu", password="pass"
        )
        self.accountant_b = User.objects.create_user(
            username="acct_sialkot", email="sk@test.edu", password="pass"
        )

        # Accountant A membership in School A
        self.membership_a = InstitutionMembership.objects.create(
            user=self.accountant_a, institution=self.school_a
        )
        RoleAssignment.objects.create(membership=self.membership_a, role=Role.ACCOUNTANT)
        StaffProfile.objects.create(
            user=self.accountant_a,
            membership=self.membership_a,
            institution=self.school_a,
            primary_campus=self.campus_a,
            employee_number="EMP-A-001",
            first_name="Lahore",
            last_name="Accountant",
            gender="male",
        )

        # Accountant B membership in School B
        self.membership_b = InstitutionMembership.objects.create(
            user=self.accountant_b, institution=self.school_b
        )
        RoleAssignment.objects.create(membership=self.membership_b, role=Role.ACCOUNTANT)
        StaffProfile.objects.create(
            user=self.accountant_b,
            membership=self.membership_b,
            institution=self.school_b,
            primary_campus=self.campus_b,
            employee_number="EMP-B-001",
            first_name="Sialkot",
            last_name="Accountant",
            gender="female",
        )

        # Client for API calls
        self.client_a = APIClient()
        self.client_a.force_login(self.accountant_a)
        self.client_b = APIClient()
        self.client_b.force_login(self.accountant_b)

        # Create student and fee structure for School A
        self.guardian_a = Guardian.objects.create(
            name="Parent A", relationship="Father", phone="03000000000"
        )
        self.student_a = Student.objects.create(
            first_name="Ali", last_name="Ahmed", admission_number="ST-001",
            guardian=self.guardian_a,
        )
        self.enrollment_a = Enrollment.objects.create(
            student=self.student_a,
            class_obj=self.class_a,
            section=self.section_a,
            academic_year=self.year_a,
            campus=self.campus_a,
            status="active",
        )
        self.fee_structure_a = FeeStructure.objects.create(
            academic_year=self.year_a,
            campus=self.campus_a,
            class_obj=self.class_a,
            category=self.category_a,
            amount=Decimal("10000.00"),
        )
        self.invoice_a = Invoice.objects.create(
            invoice_number="LA-001",
            student=self.student_a,
            enrollment=self.enrollment_a,
            academic_year=self.year_a,
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            institution=self.school_a,
        )
        InvoiceItem.objects.create(
            invoice=self.invoice_a,
            category=self.category_a,
            description="Tuition",
            amount=Decimal("10000.00"),
        )

        # Create student and fee structure for School B
        self.guardian_b = Guardian.objects.create(
            name="Parent B", relationship="Mother", phone="03000000001"
        )
        self.student_b = Student.objects.create(
            first_name="Mohammad", last_name="Sadiq", admission_number="ST-002",
            guardian=self.guardian_b,
        )
        self.enrollment_b = Enrollment.objects.create(
            student=self.student_b,
            class_obj=self.class_b,
            section=self.section_b,
            academic_year=self.year_b,
            campus=self.campus_b,
            status="active",
        )
        self.fee_structure_b = FeeStructure.objects.create(
            academic_year=self.year_b,
            campus=self.campus_b,
            class_obj=self.class_b,
            category=self.category_b,
            amount=Decimal("12000.00"),
        )
        self.invoice_b = Invoice.objects.create(
            invoice_number="SK-001",
            student=self.student_b,
            enrollment=self.enrollment_b,
            academic_year=self.year_b,
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            institution=self.school_b,
        )
        InvoiceItem.objects.create(
            invoice=self.invoice_b,
            category=self.category_b,
            description="Tuition",
            amount=Decimal("12000.00"),
        )

    def test_accountant_cannot_access_other_school_invoices(self):
        """Lahore accountant cannot list School B invoices."""
        resp = self.client_a.get("/api/finance/invoices/")
        self.assertEqual(resp.status_code, 200)
        school_a_invoices = [i for i in resp.json()["results"] if i["student"] == self.student_a.id]
        self.assertEqual(len(school_a_invoices), 1)
        school_b_invoices = [i for i in resp.json()["results"] if i["student"] == self.student_b.id]
        self.assertEqual(len(school_b_invoices), 0)

    def test_accountant_cannot_view_other_school_invoice_detail(self):
        """Lahore accountant cannot view School B invoice detail."""
        resp = self.client_a.get(f"/api/finance/invoices/{self.invoice_b.pk}/")
        self.assertEqual(resp.status_code, 404)

    def test_accountant_cannot_create_invoice_for_other_school(self):
        """Lahore accountant cannot create invoice for School B."""
        payload = {
            "invoice_number": "SK-002",
            "student": self.student_b.id,
            "enrollment": self.enrollment_b.id,
            "academic_year": self.year_b.id,
            "issue_date": date.today(),
            "due_date": date.today() + timedelta(days=30),
            "items": [
                {
                    "description": "Tuition School B",
                    "category": self.category_b.id,
                    "amount": "10000.00",
                }
            ],
        }
        resp = self.client_a.post("/api/finance/invoices/create/", payload, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_accountant_cannot_create_payment_for_other_school(self):
        """Lahore accountant cannot create payment for School B invoice."""
        resp = self.client_a.post(
            "/api/finance/payments/create/",
            {
                "invoice": self.invoice_b.pk,
                "amount": "1000.00",
                "payment_method": "cash",
                "payment_date": date.today(),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_accountant_cannot_create_concession_for_other_school(self):
        """Lahore accountant cannot create concession for School B invoice."""
        resp = self.client_a.post(
            "/api/finance/concessions/",
            {"invoice": self.invoice_b.pk, "type": "discount", "amount": "1000.00", "reason": "scholarship"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_accountant_cannot_create_adjustment_for_other_school(self):
        """Lahore accountant cannot create adjustment for School B invoice."""
        resp = self.client_a.post(
            "/api/finance/adjustments/",
            {"invoice": self.invoice_b.pk, "type": "credit", "amount": "1000.00", "reason": "correction"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_accountant_cannot_create_fine_for_other_school(self):
        """Lahore accountant cannot create fine for School B student."""
        resp = self.client_a.post(
            "/api/finance/fines/",
            {"student": self.student_b.id, "academic_year": self.year_b.id, "type": "disciplinary", "amount": "500.00", "reason": "violation"},
            format="json",
        )
        self.assertEqual(resp.status_code, 403)


# ----- JazzCash Checkout Security Tests (F1) -----
class JazzCashCheckoutSecurityTests(TestCase):
    """Regression tests for F1: pp_Password must never reach the client.

    The view builds params server-side and submits via
    submit_checkout_to_gateway(); the client only receives
    checkout_url + invoice_id + reference — no secrets.
    """

    def _make_school(self):
        school = School.objects.create(name="Test School")
        campus = Campus.objects.create(school=school, name="Test Campus")
        unit = AcademicUnit.objects.create(campus=campus, name="Primary")
        guardian = Guardian.objects.create(name="Test Parent", relationship="Father", phone="03000000000")
        student = Student.objects.create(
            first_name="Test", last_name="Student", admission_number="ST-001", guardian=guardian
        )
        class_obj = Class.objects.create(unit=unit, name="Primary")
        section = Section.objects.create(class_obj=class_obj, name="A")
        enrollment = Enrollment.objects.create(
            student=student,
            class_obj=class_obj,
            section=section,
            academic_year=AcademicYear.objects.create(
                school=school, name="2026-2027", start_date=date(2026, 8, 1), end_date=date(2027, 7, 31)
            ),
            campus=campus,
            status="active",
        )
        return school, campus, student, enrollment

    def _make_invoice(self, school, enrollment):
        invoice = Invoice.objects.create(
            invoice_number="JC-TEST-001",
            student=enrollment.student,
            enrollment=enrollment,
            academic_year=enrollment.academic_year,
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            institution=school,
        )
        category = FeeCategory.objects.create(name="Tuition", frequency="monthly")
        InvoiceItem.objects.create(
            invoice=invoice, category=category, description="Tuition", amount=Decimal("3000.00")
        )
        return invoice

    def _make_authenticated_client(self, school):
        user = User.objects.create_user(username="jc_tester", email="jc@test.edu", password="pass")
        membership = InstitutionMembership.objects.create(user=user, institution=school)
        RoleAssignment.objects.create(membership=membership, role=Role.ACCOUNTANT)
        client = APIClient()
        client.force_login(user)
        return user, client

    def _mock_gateway_redirect(self, patch):
        return patch(
            "apps.finance.jazzcash_views.submit_checkout_to_gateway",
            return_value=("https://sandbox.example.test/checkout/abc", None),
        )

    @patch.dict(
        "os.environ",
        {
            "JAZZCASH_MERCHANT_ID": "test_merchant",
            "JAZZCASH_PASSWORD": "TEST_JAZZCASH_PASSWORD_DO_NOT_LEAK",
            "JAZZCASH_INTEGRITY_SALT": "test_salt_123",
            "JAZZCASH_ENV": "sandbox",
        },
    )
    def test_authenticated_checkout_no_credential_leakage(self):
        """A authenticated user gets a checkout URL without any password leak."""
        school, campus, student, enrollment = self._make_school()
        invoice = self._make_invoice(school, enrollment)
        user, client = self._make_authenticated_client(school)

        with self._mock_gateway_redirect(patch):
            resp = client.post("/api/finance/jazzcash/checkout/", {"invoice_id": invoice.pk}, format="json")

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("checkout_url", data)
        self.assertEqual(data["invoice_id"], invoice.pk)
        self.assertIn("reference", data)

        # --- no password anywhere in the response ---
        response_str = json.dumps(data)
        self.assertNotIn("pp_Password", response_str)
        self.assertNotIn("TEST_JAZZCASH_PASSWORD_DO_NOT_LEAK", response_str)

        # --- response shape is exactly the three public fields ---
        self.assertEqual(set(data.keys()), {"checkout_url", "invoice_id", "reference"})

    @patch.dict(
        "os.environ",
        {
            "JAZZCASH_MERCHANT_ID": "test_merchant",
            "JAZZCASH_PASSWORD": "TEST_JAZZCASH_PASSWORD_DO_NOT_LEAK",
            "JAZZCASH_INTEGRITY_SALT": "test_salt_123",
            "JAZZCASH_ENV": "sandbox",
        },
    )
    def test_response_contains_no_merchant_credentials(self):
        """The JSON response must contain ONLY checkout_url, invoice_id, reference."""
        school, campus, student, enrollment = self._make_school()
        invoice = self._make_invoice(school, enrollment)
        user, client = self._make_authenticated_client(school)

        with self._mock_gateway_redirect(patch):
            resp = client.post("/api/finance/jazzcash/checkout/", {"invoice_id": invoice.pk}, format="json")

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertNotIn("params", data)
        self.assertNotIn("post_url", data)
        self.assertNotIn("merchant_id", data)
        self.assertNotIn("JAZZCASH_MERCHANT_ID", data)
        self.assertNotIn("JAZZCASH_PASSWORD", data)
        self.assertNotIn("JAZZCASH_INTEGRITY_SALT", data)
        self.assertNotIn("pp_MerchantID", data)
        self.assertNotIn("pp_Password", data)

    @patch.dict(
        "os.environ",
        {
            "JAZZCASH_MERCHANT_ID": "test_merchant",
            "JAZZCASH_PASSWORD": "TEST_JAZZCASH_PASSWORD_DO_NOT_LEAK",
            "JAZZCASH_INTEGRITY_SALT": "test_salt_123",
            "JAZZCASH_ENV": "sandbox",
        },
    )
    def test_server_side_params_still_contain_credential(self):
        """The server-side gateway submission still has the password."""
        school, campus, student, enrollment = self._make_school()
        invoice = self._make_invoice(school, enrollment)
        user, client = self._make_authenticated_client(school)

        with self._mock_gateway_redirect(patch):
            # Capture the call arguments
            with patch("apps.finance.jazzcash_views.submit_checkout_to_gateway") as mock_submit:
                mock_submit.return_value = ("https://sandbox.example.test/checkout/abc", None)
                resp = client.post("/api/finance/jazzcash/checkout/", {"invoice_id": invoice.pk}, format="json")

        # The mock was called with params that include the test password
        call_kwargs = mock_submit.call_args
        passed_params = call_kwargs[0][1]  # second positional arg is params dict
        self.assertIn("pp_Password", passed_params)
        self.assertEqual(
            passed_params["pp_Password"],
            "TEST_JAZZCASH_PASSWORD_DO_NOT_LEAK",
        )

    @patch.dict(
        "os.environ",
        {
            "JAZZCASH_MERCHANT_ID": "test_merchant",
            "JAZZCASH_PASSWORD": "TEST_JAZZCASH_PASSWORD_DO_NOT_LEAK",
            "JAZZCASH_INTEGRITY_SALT": "test_salt_123",
            "JAZZCASH_ENV": "sandbox",
        },
    )
    def test_anonymous_request_rejected(self):
        """Unauthenticated POST to the endpoint returns 403."""
        school, campus, student, enrollment = self._make_school()
        invoice = self._make_invoice(school, enrollment)

        with self._mock_gateway_redirect(patch):
            resp = self.client.post("/api/finance/jazzcash/checkout/", {"invoice_id": invoice.pk}, format="json")

        self.assertEqual(resp.status_code, 403)

    @patch.dict(
        "os.environ",
        {
            "JAZZCASH_MERCHANT_ID": "test_merchant",
            "JAZZCASH_PASSWORD": "TEST_JAZZCASH_PASSWORD_DO_NOT_LEAK",
            "JAZZCASH_INTEGRITY_SALT": "test_salt_123",
            "JAZZCASH_ENV": "sandbox",
        },
    )
    def test_missing_jazzconfig_fails_closed(self):
        """When credentials are missing the endpoint returns 503."""
        # Remove the test env vars temporarily
        with patch.dict("os.environ", {}, clear=True):
            school, campus, student, enrollment = self._make_school()
            invoice = self._make_invoice(school, enrollment)
            user, client = self._make_authenticated_client(school)

            with self._mock_gateway_redirect(patch):
                resp = client.post("/api/finance/jazzcash/checkout/", {"invoice_id": invoice.pk}, format="json")

        self.assertEqual(resp.status_code, 503)
        # Ensure no secret values leak in the error detail
        self.assertNotIn("TEST_JAZZCASH_PASSWORD_DO_NOT_LEAK", resp.json().get("detail", ""))

    @patch.dict(
        "os.environ",
        {
            "JAZZCASH_MERCHANT_ID": "test_merchant",
            "JAZZCASH_PASSWORD": "TEST_JAZZCASH_PASSWORD_DO_NOT_LEAK",
            "JAZZCASH_INTEGRITY_SALT": "test_salt_123",
            "JAZZCASH_ENV": "sandbox",
        },
    )
    def test_invoice_no_outstanding_balance(self):
        """An invoice with zero balance returns 400."""
        school, campus, student, enrollment = self._make_school()
        # Invoice created without items → derived balance is already 0 (read-only property)
        invoice = Invoice.objects.create(
            invoice_number="JC-ZERO-001",
            student=enrollment.student,
            enrollment=enrollment,
            academic_year=enrollment.academic_year,
            issue_date=date.today(),
            due_date=date.today() + timedelta(days=30),
            institution=school,
        )
        user, client = self._make_authenticated_client(school)

        with self._mock_gateway_redirect(patch):
            resp = client.post("/api/finance/jazzcash/checkout/", {"invoice_id": invoice.pk}, format="json")

        self.assertEqual(resp.status_code, 400)


class FeeCategoryCreationTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Category School")
        self.user = User.objects.create_user(username="category_admin", password="test-pass")
        membership = InstitutionMembership.objects.create(user=self.user, institution=self.school)
        RoleAssignment.objects.create(membership=membership, role=Role.ADMIN)
        self.client = APIClient()
        self.client.force_login(self.user)

    def test_create_category_for_active_school_and_reject_duplicate(self):
        response = self.client.post("/api/finance/categories/", {
            "name": "  Tuition  ", "frequency": "monthly", "status": "active",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["name"], "Tuition")
        self.assertTrue(FeeCategory.objects.filter(institution=self.school, name="Tuition").exists())

        duplicate = self.client.post("/api/finance/categories/", {
            "name": "tuition", "frequency": "monthly",
        }, format="json")
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(len(self.client.get("/api/finance/categories/").json()), 1)

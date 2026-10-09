"""Executive dashboard aggregates.

One endpoint that gives owner / principal / academic staff a school-wide
snapshot: people and enrollment, financial health, attendance, academic
performance, per-campus comparison, and computed executive alerts.

Every queryset is institution- and campus-scoped through
``apply_campus_scope``, so a campus principal only ever sees their own
campuses while global admins see the whole school.
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce, TruncMonth
from django.utils import timezone

from apps.accounts.access import apply_campus_scope
from apps.attendance.models import Attendance
from apps.finance.models import Invoice, InvoiceItem, Payment

ZERO = Decimal("0.00")
SIX_MONTHS = 6


def _pct(part, whole):
    # Round via float so Decimal inputs still yield a JSON number,
    # not a stringified Decimal ("0.0" vs 0.0).
    if not whole:
        return 0.0
    return round(float(part) / float(whole) * 100, 1)


def _money(value):
    return str(Decimal(value or ZERO).quantize(Decimal("0.01")))


def executive_dashboard(request):
    """Build the executive dashboard payload for ``request``.

    Optional query params:

    - ``year``  — academic year id (enrollments, billing, exams only).
    """
    from apps.schools.models import AcademicYear, Campus
    from apps.students.models import Enrollment, Student
    from apps.teachers.models import Teacher

    # --- Resolve academic year filter --------------------------------
    year = None
    year_id = request.query_params.get("year")

    if year_id:
        year = (
            AcademicYear.objects.filter(pk=year_id).first()
            if str(year_id).isdigit()
            else None
        )

    # --- Scoped base querysets ---------------------------------------
    campuses = apply_campus_scope(
        Campus.objects.filter(status="active"),
        request,
        campus_field="id",
        institution_field="school_id",
    )

    campus_list = list(campuses.order_by("name"))
    campus_ids = [c.id for c in campus_list]

    from apps.students.querysets import school_scoped_students
    students = school_scoped_students(Student.objects.all(), request)

    enrollments = apply_campus_scope(
        Enrollment.objects.all(),
        request,
        campus_field="campus_id",
        institution_field="campus__school_id",
    ).filter(status="active")

    if year:
        enrollments = enrollments.filter(academic_year=year)

    teachers = apply_campus_scope(
        Teacher.objects.all(),
        request,
        campus_field="primary_campus_id",
        institution_field="institution_id",
    )

    from apps.accounts.models import StaffProfile

    staff = apply_campus_scope(
        StaffProfile.objects.all(),
        request,
        campus_field="primary_campus_id",
        institution_field="institution_id",
    ).filter(status="active")

    # --- Finance ------------------------------------------------------
    item_totals = (
        InvoiceItem.objects
        .filter(invoice=OuterRef("pk"))
        .values("invoice")
        .annotate(total=Sum("amount"))
        .values("total")
    )

    paid_totals = (
        Payment.objects
        .filter(invoice=OuterRef("pk"), status="completed")
        .values("invoice")
        .annotate(total=Sum("amount"))
        .values("total")
    )

    invoices = apply_campus_scope(
        Invoice.objects.all(),
        request,
        campus_field="enrollment__campus_id",
        institution_field="institution_id",
    ).annotate(
        items_total=Coalesce(Subquery(item_totals), ZERO),
        paid=Coalesce(Subquery(paid_totals), ZERO),
    )

    if year:
        invoices = invoices.filter(academic_year=year)

    invoices = list(invoices.select_related("enrollment__campus"))

    payments = apply_campus_scope(
        Payment.objects.filter(status="completed"),
        request,
        campus_field="invoice__enrollment__campus_id",
        institution_field="institution_id",
    )

    finance = _finance(invoices, payments)

    # --- Attendance ----------------------------------------------------
    attendance = apply_campus_scope(
        Attendance.objects.all(),
        request,
        campus_field="campus_id",
        institution_field="campus__school_id",
    )

    today = timezone.localdate()
    month_start = today.replace(day=1)
    trend_start = today - timedelta(days=180)

    today_qs = attendance.filter(date=today)
    month_qs = attendance.filter(date__gte=month_start)
    trend_qs = attendance.filter(date__gte=trend_start)

    attendance_data = _attendance(today_qs, month_qs, trend_qs)

    # --- Academic -----------------------------------------------------
    academic, exam_by_campus = _academic(request, year, campus_ids)

    # --- Per-campus comparison ---------------------------------------
    campus_rows = _campus_rows(
        request,
        campus_list,
        enrollments,
        teachers,
        staff,
        invoices,
        month_qs,
        exam_by_campus,
        year,
    )

    # --- Summary ------------------------------------------------------
    active_students = students.filter(status="active")

    summary = {
        "campuses": len(campus_list),
        "students": {
            "total": students.count(),
            "active": active_students.count(),
            "male": active_students.filter(gender="male").count(),
            "female": active_students.filter(gender="female").count(),
        },
        "enrollments": enrollments.count(),
        "teachers": {
            "total": teachers.count(),
            "active": teachers.filter(status="active").count(),
        },
        "staff": staff.count(),
        "sections": enrollments.values("section").distinct().count(),
    }

    alerts = _alerts(campus_rows, finance, attendance_data, academic)

    return {
        "generated_at": timezone.now().isoformat(),
        "academic_year": (
            {"id": year.pk, "name": year.name} if year else None
        ),
        "summary": summary,
        "finance": finance,
        "attendance": attendance_data,
        "academic": academic,
        "campuses": campus_rows,
        "alerts": alerts,
    }


# ---------------------------------------------------------------------------
# Finance
# ---------------------------------------------------------------------------

def _finance(invoices, payments):
    total_billed = ZERO
    total_collected = ZERO
    total_outstanding = ZERO
    status_counts = {}
    per_campus = {}

    for invoice in invoices:
        campus_id = invoice.enrollment.campus_id if invoice.enrollment else None
        billed = max(invoice.items_total - invoice.discount, ZERO)
        paid = invoice.paid
        balance = max(billed - paid, ZERO)

        total_billed += billed
        total_collected += paid
        total_outstanding += balance
        status_counts[invoice.status] = status_counts.get(invoice.status, 0) + 1

        if campus_id is not None:
            row = per_campus.setdefault(
                campus_id,
                {
                    "billed": ZERO,
                    "collected": ZERO,
                    "outstanding": ZERO,
                },
            )
            row["billed"] += billed
            row["collected"] += paid
            row["outstanding"] += balance

    # Collection trend across the last six months.
    monthly_collected = {
        row["month"]: row["total"]
        for row in payments.annotate(
            month=TruncMonth("payment_date")
        ).values("month").annotate(total=Sum("amount"))
    }

    monthly_billed = {}
    for invoice in invoices:
        key = invoice.issue_date.replace(day=1).strftime("%Y-%m")
        billed = max(invoice.items_total - invoice.discount, ZERO)
        monthly_billed[key] = monthly_billed.get(key, ZERO) + billed

    today = timezone.localdate()
    months = []
    for offset in range(SIX_MONTHS - 1, -1, -1):
        month = today.replace(day=1) - timedelta(days=31 * offset)
        key = month.strftime("%Y-%m")
        billed = monthly_billed.get(key, ZERO)
        collected = monthly_collected.get(key, ZERO)
        months.append(
            {
                "month": key,
                "billed": _money(billed),
                "collected": _money(collected),
                "outstanding": _money(max(billed - collected, ZERO)),
            }
        )

    payment_method_choices = dict(Payment.PAYMENT_METHOD_CHOICES)

    by_method = [
        {"method": payment_method_choices.get(row["payment_method"], row["payment_method"]),
         "total": _money(row["total"])}
        for row in payments.values("payment_method").annotate(
            total=Sum("amount")
        ).order_by("-total")
    ]

    overdue = [
        (invoice.id, max(invoice.items_total - invoice.discount, ZERO) - invoice.paid)
        for invoice in invoices
        if invoice.status == "overdue"
        and max(invoice.items_total - invoice.discount, ZERO) - invoice.paid > 0
    ]
    overdue_amount = sum((balance for _, balance in overdue), ZERO)

    collection_rate = (
        _pct(total_collected, total_billed)
        if total_billed
        else 0.0
    )

    return {
        "total_billed": _money(total_billed),
        "collected": _money(total_collected),
        "outstanding": _money(total_outstanding),
        "collection_rate": collection_rate,
        "invoice_counts": {
            "paid": status_counts.get("paid", 0),
            "partial": status_counts.get("partial", 0),
            "overdue": status_counts.get("overdue", 0),
            "issued": status_counts.get("issued", 0),
            "cancelled": status_counts.get("cancelled", 0),
        },
        "overdue": {
            "count": len(overdue),
            "amount": _money(overdue_amount),
        },
        "by_method": by_method,
        "monthly": months,
        "per_campus": {
            str(cid): {
                "billed": _money(row["billed"]),
                "collected": _money(row["collected"]),
                "outstanding": _money(row["outstanding"]),
            }
            for cid, row in per_campus.items()
        },
    }


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

def _attendance(today_qs, month_qs, trend_qs):
    def counts(qs):
        grouped = dict(qs.values_list("status").annotate(c=Count("id")))
        return {
            "present": grouped.get("present", 0),
            "absent": grouped.get("absent", 0),
            "late": grouped.get("late", 0),
            "leave": grouped.get("leave", 0),
        }

    today_c = counts(today_qs)
    month_c = counts(month_qs)

    trend_rows = (
        trend_qs
        .annotate(month=TruncMonth("date"))
        .values("month")
        .annotate(
            total=Count("id"),
            present=Count(Q(status__in=["present", "late"])),
        )
        .order_by("month")
    )

    by_month = {
        row["month"].strftime("%Y-%m"): _pct(row["present"], row["total"])
        for row in trend_rows
    }

    today_month_key = timezone.localdate().strftime("%Y-%m")
    trend = [
        {"month": key, "rate": by_month.get(key, 0.0)}
        for key in sorted(by_month)
    ][-SIX_MONTHS:]

    return {
        "today": {
            "rate": _pct(
                today_c["present"] + today_c["late"],
                sum(today_c.values()),
            ),
            **today_c,
        },
        "month": {
            "rate": _pct(
                month_c["present"] + month_c["late"],
                sum(month_c.values()),
            ),
            "total": sum(month_c.values()),
            **month_c,
        },
        "trend": trend,
    }


# ---------------------------------------------------------------------------
# Academic
# ---------------------------------------------------------------------------

def _academic(request, year, campus_ids):
    from apps.reportcards.models import ReportCard
    from apps.reports.utils import prefetch_reportcard_results

    cards = list(
        ReportCard.objects
        .filter(status__in=["approved", "published"])
        .select_related("exam")
    )

    if year:
        cards = [c for c in cards if c.exam.academic_year_id == year.pk]

    if campus_ids:
        keep = set(campus_ids)
        cards = [c for c in cards if c.exam.campus_id in keep]

    # percentage / overall_result are computed properties, so aggregate in
    # Python. Prefetch StudentResults to avoid an N+1 per card.
    prefetch_reportcard_results(cards)

    by_exam = {}
    per_campus_latest = {}
    latest_exam = None

    for card in cards:
        exam = card.exam
        row = by_exam.setdefault(
            exam.pk,
            {
                "exam": exam,
                "total": 0,
                "passed": 0,
                "sum_pct": 0.0,
            },
        )
        row["total"] += 1
        row["sum_pct"] += float(card.percentage or 0)
        if card.is_pass:
            row["passed"] += 1

        if (
            exam.start_date
            and (
                latest_exam is None
                or exam.start_date > latest_exam.start_date
            )
        ):
            latest_exam = exam

    if latest_exam:
        for card in cards:
            if card.exam_id != latest_exam.pk:
                continue
            entry = per_campus_latest.setdefault(
                card.exam.campus_id,
                {"total": 0, "passed": 0},
            )
            entry["total"] += 1
            if card.is_pass:
                entry["passed"] += 1

    def exam_payload(row):
        exam = row["exam"]
        return {
            "exam_id": exam.pk,
            "name": exam.name,
            "start_date": (
                exam.start_date.isoformat()
                if exam.start_date
                else None
            ),
            "total": row["total"],
            "pass_rate": _pct(row["passed"], row["total"]),
            "avg_percentage": (
                round(row["sum_pct"] / row["total"], 1)
                if row["total"]
                else None
            ),
        }

    ordered = sorted(
        by_exam.values(),
        key=lambda row: row["exam"].start_date,
        reverse=True,
    )
    by_exam_payload = [
        exam_payload(row) for row in reversed(ordered[:SIX_MONTHS])
    ]

    latest_payload = (
        exam_payload(by_exam[latest_exam.pk])
        if latest_exam
        else None
    )

    from apps.students.models import Enrollment

    class_strength_qs = apply_campus_scope(
        Enrollment.objects.filter(status="active"),
        request,
        campus_field="campus_id",
        institution_field="campus__school_id",
    )

    if year:
        class_strength_qs = class_strength_qs.filter(academic_year=year)

    class_strength = (
        class_strength_qs
        .filter(class_obj__isnull=False)
        .values("class_obj__name")
        .annotate(count=Count("id"))
        .order_by("-count")[:15]
    )

    return {
        "latest_exam": latest_payload,
        "by_exam": by_exam_payload,
        "class_strength": [
            {"class": row["class_obj__name"], "students": row["count"]}
            for row in class_strength
        ],
    }, per_campus_latest


# ---------------------------------------------------------------------------
# Campus comparison
# ---------------------------------------------------------------------------

def _campus_rows(
    request,
    campus_list,
    enrollments,
    teachers,
    staff,
    invoices,
    month_qs,
    exam_by_campus,
    year,
):
    rows = []

    enrollment_map = {
        row["campus_id"]: row["total"]
        for row in enrollments.values("campus_id").annotate(total=Count("id"))
    }

    teacher_map = {
        row["primary_campus_id"]: row["total"]
        for row in teachers.filter(
            status="active",
            primary_campus_id__isnull=False,
        ).values("primary_campus_id").annotate(total=Count("id"))
    }

    staff_map = {
        row["primary_campus_id"]: row["total"]
        for row in staff.values("primary_campus_id").annotate(
            total=Count("id")
        )
    }

    finance_map = {}
    for invoice in invoices:
        campus_id = invoice.enrollment.campus_id if invoice.enrollment else None
        if campus_id is None:
            continue
        row = finance_map.setdefault(
            campus_id,
            {"billed": ZERO, "collected": ZERO, "outstanding": ZERO},
        )
        billed = max(invoice.items_total - invoice.discount, ZERO)
        balance = max(billed - invoice.paid, ZERO)
        row["billed"] += billed
        row["collected"] += invoice.paid
        row["outstanding"] += balance

    exam_cards = exam_by_campus or None

    for campus in campus_list:
        month_c = {
            status: count
            for status, count in month_qs.filter(
                campus=campus
            ).values_list("status").annotate(c=Count("id"))
        }
        total_att = sum(month_c.values())
        present_att = month_c.get("present", 0) + month_c.get("late", 0)

        fin = finance_map.get(campus.pk, {})
        billed = fin.get("billed", ZERO)
        collected = fin.get("collected", ZERO)

        rows.append(
            {
                "id": campus.pk,
                "name": campus.name,
                "students": enrollment_map.get(campus.pk, 0),
                "teachers": teacher_map.get(campus.pk, 0),
                "staff": staff_map.get(campus.pk, 0),
                "attendance_rate_month": _pct(present_att, total_att),
                "billed": _money(billed),
                "collected": _money(collected),
                "outstanding": _money(max(billed - collected, ZERO)),
                "collection_rate": _pct(collected, billed),
                "pass_rate": (
                    _pct(
                        exam_cards[campus.pk]["passed"],
                        exam_cards[campus.pk]["total"],
                    )
                    if exam_cards and campus.pk in exam_cards
                    else None
                ),
                "exam_students": (
                    exam_cards[campus.pk]["total"]
                    if exam_cards and campus.pk in exam_cards
                    else 0
                ),
            }
        )

    return rows


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------

def _alerts(campus_rows, finance, attendance, academic):
    alerts = []
    total_outstanding = Decimal(finance["outstanding"])

    if total_outstanding > 0:
        alerts.append(
            {
                "severity": "info" if finance["collection_rate"] >= 70 else "high",
                "category": "finance",
                "title": "Outstanding fees",
                "message": (
                    f"Rs {total_outstanding:,.2f} across the school, "
                    f"{finance['invoice_counts'].get('overdue', 0)} overdue invoices."
                ),
                "value": finance["outstanding"],
            }
        )

    for campus in campus_rows:
        rate = campus["collection_rate"]
        if rate < 60:
            alerts.append(
                {
                    "severity": "high",
                    "category": "finance",
                    "title": "Low collection rate",
                    "message": (
                        f"{campus['name']} has collected only "
                        f"{rate}% of billed fees."
                    ),
                    "value": f"{rate}%",
                }
            )

    month_rate = attendance["month"]["rate"]
    if 0 < month_rate < 75:
        alerts.append(
            {
                "severity": "high",
                "category": "attendance",
                "title": "Attendance below norm",
                "message": (
                    f"School-wide attendance this month is {month_rate}%."
                ),
                "value": f"{month_rate}%",
            }
        )

    for campus in campus_rows:
        rate = campus["attendance_rate_month"]
        if 0 < rate < 70:
            alerts.append(
                {
                    "severity": "medium",
                    "category": "attendance",
                    "title": "Campus attendance lag",
                    "message": (
                        f"{campus['name']} is running at {rate}% for "
                        "the current month."
                    ),
                    "value": f"{rate}%",
                }
            )

    latest = academic["latest_exam"]
    if latest:
        if latest["pass_rate"] < 60:
            alerts.append(
                {
                    "severity": "medium",
                    "category": "academic",
                    "title": "Exam pass rate",
                    "message": (
                        f"{latest['name']}: {latest['pass_rate']}% pass "
                        f"rate with {latest['total']} students."
                    ),
                    "value": f"{latest['pass_rate']}%",
                }
            )
    else:
        alerts.append(
            {
                "severity": "info",
                "category": "academic",
                "title": "No published results yet",
                "message": (
                    "Publish a report card to see exam performance "
                    "trends here."
                ),
                "value": None,
            }
        )

    if not campus_rows:
        alerts.append(
            {
                "severity": "info",
                "category": "people",
                "title": "No campuses in scope",
                "message": (
                    "There are no active campuses in your scope to "
                    "report on."
                ),
                "value": None,
            }
        )

    order = {"high": 0, "medium": 1, "info": 2}
    alerts.sort(key=lambda a: order.get(a["severity"], 3))

    return alerts[:6]

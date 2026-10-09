from django.conf import settings
from django.db import models
from django.utils import timezone


class ReportCategory(models.Model):
    """Report categories for organizing reports in the Reports Center."""

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True, help_text="Lucide icon name")
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    required_roles = models.JSONField(
        default=list,
        blank=True,
        help_text="List of role names required to access this category",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "name"]
        verbose_name_plural = "Report Categories"

    def __str__(self):
        return self.name


class ReportDefinition(models.Model):
    """Centralized definition of all available reports."""

    REPORT_TYPE_CHOICES = [
        ("enrollment", "Enrollment Report"),
        ("attendance", "Attendance Report"),
        ("results", "Results Report"),
        ("fees", "Fees Report"),
        ("staff", "Staff Report"),
        ("subjects", "Subject Performance"),
        ("payments", "Payment Methods"),
        ("student_status", "Student Status"),
        ("fee_categories", "Fee Categories"),
        ("fee_defaulters", "Fee Defaulters"),
        ("teacher_workload", "Teacher Workload"),
        ("class_performance", "Class Performance"),
        ("student_progress", "Student Progress"),
        ("collection_trend", "Collection Trend"),
        ("discounts", "Discounts & Concessions"),
        ("chronic_absentee", "Chronic Absentees"),
        ("payroll_summary", "Payroll Summary"),
        ("library_overview", "Library Overview"),
        ("route_utilization", "Route Utilization"),
        ("inventory_value", "Inventory Value"),
        ("maintenance_due", "Maintenance Due"),
        ("event_participation", "Event Participation"),
        ("sms_usage", "SMS Usage"),
        ("top_performers", "Top Performers"),
        ("at_risk", "At-Risk Students"),
        ("admission_register", "Admission Register"),
        ("new_admissions", "New Admissions"),
        ("withdrawals", "Withdrawals"),
        ("transfers", "Transfers"),
        ("daily_attendance", "Daily Attendance"),
        ("monthly_attendance", "Monthly Attendance"),
        ("student_attendance", "Student Attendance"),
        ("class_attendance", "Class Attendance"),
        ("attendance_analytics", "Attendance Analytics"),
        ("exam_schedule", "Exam Schedule"),
        ("exam_marks", "Exam Marks"),
        ("exam_attendance", "Exam Attendance"),
        ("student_result", "Student Result"),
        ("result_analytics", "Result Analytics"),
        ("report_card", "Report Card"),
        ("fee_collection", "Fee Collection"),
        ("fee_outstanding", "Outstanding Fees"),
        ("fee_paid", "Paid Fees"),
        ("fee_unpaid", "Unpaid Fees"),
        ("fee_discounts", "Fee Discounts"),
        ("finance_income", "Income Report"),
        ("finance_expense", "Expense Report"),
        ("finance_pl", "Profit/Loss Summary"),
        ("finance_cashflow", "Cash Flow Report"),
        ("finance_ledger", "Account Ledger"),
        ("staff_master", "Staff Master"),
        ("teacher_master", "Teacher Master"),
        ("staff_attendance_report", "Staff Attendance"),
        ("teacher_attendance_report", "Teacher Attendance"),
        ("staff_leave_report", "Staff Leave"),
        ("teacher_leave_report", "Teacher Leave"),
        ("department_report", "Department Report"),
        ("designation_report", "Designation Report"),
        ("hr_employee", "Employee Master"),
        ("hr_attendance", "HR Attendance"),
        ("hr_leave", "HR Leave"),
        ("payroll_monthly", "Monthly Payroll"),
        ("payroll_salary_slip", "Salary Slip"),
        ("payroll_summary_report", "Payroll Summary"),
        ("class_strength", "Class Strength"),
        ("section_strength", "Section Strength"),
        ("class_teacher_report", "Class Teacher Report"),
        ("subject_allocation", "Subject Allocation"),
        ("timetable_student", "Student Timetable"),
        ("timetable_class", "Class Timetable"),
        ("timetable_teacher", "Teacher Timetable"),
        ("timetable_room", "Room Timetable"),
        ("library_inventory", "Book Inventory"),
        ("library_issued", "Issued Books"),
        ("library_overdue", "Overdue Books"),
        ("library_fines", "Library Fines"),
        ("transport_students", "Student Transport List"),
        ("transport_routes", "Route Report"),
        ("transport_vehicles", "Vehicle Report"),
        ("transport_fees", "Transport Fee Report"),
        ("inventory_stock", "Stock Report"),
        ("inventory_low_stock", "Low Stock"),
        ("inventory_movement", "Stock Movement"),
        ("discipline_incidents", "Discipline Incidents"),
        ("discipline_warnings", "Warning Report"),
        ("discipline_suspensions", "Suspension Report"),
        ("certificate_bonafide", "Bonafide Certificate"),
        ("certificate_character", "Character Certificate"),
        ("certificate_leaving", "Leaving Certificate"),
        ("certificate_transfer", "Transfer Certificate"),
        ("certificate_enrollment", "Enrollment Certificate"),
        ("certificate_fee_clearance", "Fee Clearance Certificate"),
        ("certificate_student_id", "Student ID Card"),
        ("certificate_staff_id", "Staff ID Card"),
        ("campus_students", "Campus Student Count"),
        ("campus_attendance", "Campus Attendance"),
        ("campus_performance", "Campus Academic Performance"),
        ("campus_fees", "Campus Fee Collection"),
        ("campus_staff", "Campus Staff Count"),
        ("campus_admissions", "Campus Admissions"),
        ("campus_finance", "Campus Financial Summary"),
    ]

    category = models.ForeignKey(
        ReportCategory,
        on_delete=models.PROTECT,
        related_name="report_definitions",
    )
    key = models.SlugField(max_length=100, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    report_type = models.CharField(max_length=50, choices=REPORT_TYPE_CHOICES)

    endpoint_url = models.CharField(max_length=200, help_text="API endpoint for this report")
    supports_csv = models.BooleanField(default=True)
    supports_pdf = models.BooleanField(default=False)
    supports_excel = models.BooleanField(default=False)
    supports_print = models.BooleanField(default=True)
    supports_schedule = models.BooleanField(default=False)

    default_filters = models.JSONField(default=dict, blank=True)
    available_filters = models.JSONField(default=list, blank=True)
    default_columns = models.JSONField(default=list, blank=True)
    available_columns = models.JSONField(default=list, blank=True)
    supports_grouping = models.BooleanField(default=False)
    grouping_fields = models.JSONField(default=list, blank=True)
    supports_drilldown = models.BooleanField(default=False)
    drilldown_target = models.CharField(max_length=100, blank=True)

    required_roles = models.JSONField(
        default=list,
        blank=True,
        help_text="List of role names required to access this report",
    )
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category__order", "order", "title"]

    def __str__(self):
        return f"{self.title} ({self.key})"


class SavedReport(models.Model):
    """User-saved report configurations."""

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    report_definition = models.ForeignKey(
        ReportDefinition,
        on_delete=models.PROTECT,
        related_name="saved_reports",
    )

    filters = models.JSONField(default=dict, blank=True)
    columns = models.JSONField(default=list, blank=True)
    column_order = models.JSONField(default=list, blank=True)
    column_labels = models.JSONField(default=dict, blank=True)
    grouping = models.JSONField(default=dict, blank=True)
    sorting = models.JSONField(default=list, blank=True)

    template = models.ForeignKey(
        "ReportTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="saved_reports",
    )

    is_favorite = models.BooleanField(default=False)
    is_shared = models.BooleanField(default=False)
    shared_with = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="shared_reports",
    )
    shared_with_roles = models.JSONField(default=list, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_saved_reports",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_saved_reports",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    run_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-is_favorite", "-updated_at"]

    def __str__(self):
        return f"{self.name} ({self.report_definition.title})"


class ReportTemplate(models.Model):
    """Enhanced report templates for PDF/Print output."""

    REPORT_TYPE_CHOICES = [
        ("enrollment", "Enrollment Report"),
        ("attendance", "Attendance Report"),
        ("results", "Results Report"),
        ("fees", "Fees Report"),
        ("staff", "Staff Report"),
        ("subjects", "Subject Performance"),
        ("payments", "Payment Methods"),
        ("student_status", "Student Status"),
        ("fee_categories", "Fee Categories"),
        ("fee_defaulters", "Fee Defaulters"),
        ("teacher_workload", "Teacher Workload"),
        ("class_performance", "Class Performance"),
        ("student_progress", "Student Progress"),
        ("collection_trend", "Collection Trend"),
        ("discounts", "Discounts & Concessions"),
        ("chronic_absentee", "Chronic Absentees"),
        ("payroll_summary", "Payroll Summary"),
        ("library_overview", "Library Overview"),
        ("route_utilization", "Route Utilization"),
        ("inventory_value", "Inventory Value"),
        ("maintenance_due", "Maintenance Due"),
        ("event_participation", "Event Participation"),
        ("sms_usage", "SMS Usage"),
        ("top_performers", "Top Performers"),
        ("at_risk", "At-Risk Students"),
        ("admission_register", "Admission Register"),
        ("report_card", "Report Card"),
        ("certificate", "Certificate"),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    report_type = models.CharField(max_length=50, choices=REPORT_TYPE_CHOICES)

    header_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Logo, school name, campus, address, report title",
    )
    footer_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Page numbers, generated date, generated by, signature lines",
    )
    column_config = models.JSONField(
        default=list,
        blank=True,
        help_text="Column widths, alignment, font sizes, visibility",
    )
    page_config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Page size (A4/Letter), orientation (portrait/landscape), margins",
    )
    styling = models.JSONField(
        default=dict,
        blank=True,
        help_text="Font family, colors, borders, alternating row colors",
    )
    watermark = models.CharField(max_length=200, blank=True)
    filters = models.JSONField(default=dict, blank=True)
    columns = models.JSONField(default=list, blank=True)

    is_default = models.BooleanField(default=False)
    is_system = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="report_templates",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_default", "name"]

    def __str__(self):
        return f"{self.name} ({self.get_report_type_display()})"


class ScheduledReport(models.Model):
    """Scheduled report generation and delivery."""

    FREQUENCY_CHOICES = [
        ("daily", "Daily"),
        ("weekly", "Weekly"),
        ("monthly", "Monthly"),
        ("custom", "Custom Cron"),
    ]

    FORMAT_CHOICES = [
        ("csv", "CSV"),
        ("pdf", "PDF"),
        ("excel", "Excel"),
    ]

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    saved_report = models.ForeignKey(
        SavedReport,
        on_delete=models.CASCADE,
        related_name="schedules",
    )

    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES)
    cron_expression = models.CharField(
        max_length=100,
        blank=True,
        help_text="Cron expression for custom frequency",
    )
    day_of_week = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="0=Monday, 6=Sunday (for weekly)",
    )
    day_of_month = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="1-31 (for monthly)",
    )
    time_of_day = models.TimeField(help_text="Time to run the report")

    output_format = models.CharField(max_length=10, choices=FORMAT_CHOICES, default="pdf")
    email_enabled = models.BooleanField(default=False)
    email_recipients = models.JSONField(
        default=list,
        blank=True,
        help_text="List of email addresses",
    )
    email_subject = models.CharField(max_length=200, blank=True)
    email_body = models.TextField(blank=True)

    last_run_at = models.DateTimeField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True)
    last_run_status = models.CharField(
        max_length=20,
        choices=[
            ("success", "Success"),
            ("failed", "Failed"),
            ("pending", "Pending"),
        ],
        default="pending",
    )
    last_run_error = models.TextField(blank=True)
    run_count = models.PositiveIntegerField(default=0)

    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scheduled_reports",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.get_frequency_display()})"


class ReportAuditLog(models.Model):
    """Audit log for report access and exports."""

    ACTION_CHOICES = [
        ("view", "View"),
        ("export_csv", "Export CSV"),
        ("export_pdf", "Export PDF"),
        ("export_excel", "Export Excel"),
        ("print", "Print"),
        ("schedule", "Schedule"),
        ("save", "Save"),
        ("share", "Share"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="report_audit_logs",
    )
    report_definition = models.ForeignKey(
        ReportDefinition,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    saved_report = models.ForeignKey(
        SavedReport,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )

    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    campus_id = models.PositiveIntegerField(null=True, blank=True)
    campus_name = models.CharField(max_length=200, blank=True)
    academic_year_id = models.PositiveIntegerField(null=True, blank=True)
    academic_year_name = models.CharField(max_length=100, blank=True)

    filters_used = models.JSONField(default=dict, blank=True)
    record_count = models.PositiveIntegerField(default=0)
    file_size = models.PositiveIntegerField(default=0, help_text="Size in bytes for exports")

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["report_definition", "created_at"]),
            models.Index(fields=["campus_id", "created_at"]),
        ]

    def __str__(self):
        return f"{self.user} - {self.action} - {self.report_definition}"


class CustomReportDataSource(models.Model):
    """Pre-approved data sources for custom report builder."""

    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    model_path = models.CharField(max_length=200, help_text="e.g., apps.students.models.Student")
    display_name_field = models.CharField(max_length=100, default="full_name")
    id_field = models.CharField(max_length=100, default="id")

    category = models.ForeignKey(
        ReportCategory,
        on_delete=models.PROTECT,
        related_name="data_sources",
    )

    base_queryset_method = models.CharField(
        max_length=100,
        blank=True,
        help_text="Method name on manager for base queryset",
    )
    select_related_fields = models.JSONField(default=list, blank=True)
    prefetch_related_fields = models.JSONField(default=list, blank=True)

    available_fields = models.JSONField(
        default=list,
        help_text="List of field configs: [{key, label, type, path, filterable, sortable, groupable}]",
    )
    default_filters = models.JSONField(default=dict, blank=True)
    relationships = models.JSONField(
        default=dict,
        blank=True,
        help_text="Related data sources that can be joined",
    )

    required_roles = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category__order", "name"]

    def __str__(self):
        return self.name


class CustomReport(models.Model):
    """User-created custom reports using approved data sources."""

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    primary_data_source = models.ForeignKey(
        CustomReportDataSource,
        on_delete=models.PROTECT,
        related_name="custom_reports",
    )
    joined_data_sources = models.JSONField(
        default=list,
        blank=True,
        help_text="List of joined data source configs",
    )

    selected_fields = models.JSONField(
        default=list,
        help_text="List of selected field configs with custom labels",
    )
    filters = models.JSONField(default=dict, blank=True)
    filter_logic = models.CharField(
        max_length=10,
        choices=[("AND", "AND"), ("OR", "OR")],
        default="AND",
    )
    grouping = models.JSONField(default=dict, blank=True)
    sorting = models.JSONField(default=list, blank=True)
    aggregations = models.JSONField(default=list, blank=True)

    template = models.ForeignKey(
        ReportTemplate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="custom_reports",
    )

    is_favorite = models.BooleanField(default=False)
    is_shared = models.BooleanField(default=False)
    shared_with = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="shared_custom_reports",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_custom_reports",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_custom_reports",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_run_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-is_favorite", "-updated_at"]

    def __str__(self):
        return self.name

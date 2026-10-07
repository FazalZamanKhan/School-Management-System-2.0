from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from urllib.parse import urlparse, urlunparse

from apps.schools.models import School


class AuditLog(models.Model):
    ACTION_CHOICES = [
        ("login", "Login"),
        ("login_failed", "Login Failed"),
        ("institution_switched", "Institution Switched"),
        ("logout", "Logout"),
        ("create", "Create"),
        ("update", "Update"),
        ("delete", "Delete"),
        ("export", "Export"),
        ("permission_change", "Permission Change"),
        ("settings_change", "Settings Change"),
        ("password_reset", "Password Reset"),
        ("grade_publish", "Grade Publish"),
        ("grade_amendment", "Grade Amendment"),
        ("payment", "Payment"),
        ("payment_reversal", "Payment Reversal"),
        ("payment_refund", "Payment Refund"),
        ("invoice", "Invoice"),
        ("expense_posted", "Expense Posted"),
        ("concession_approved", "Concession Approved"),
        ("staff_leave_approved", "Staff Leave Approved"),
        ("staff_leave_rejected", "Staff Leave Rejected"),
        ("other", "Other"),
        ("student_transfer_initiated", "Student Transfer Initiated"),
        ("student_transfer_approved", "Student Transfer Approved"),
        ("student_transfer_rejected", "Student Transfer Rejected"),
        ("subscription_changed", "Subscription Changed"),
        ("feature_flag_changed", "Feature Flag Changed"),
        ("role_change", "Role Changed"),
        ("brute_force_detected", "Brute Force Detected"),
        ("api_key_created", "API Key Created"),
        ("ai_ask", "AI Ask"),
        ("ai_search", "AI Search"),
        ("ai_insight", "AI Insight"),
        ("ai_anomaly", "AI Anomaly Scan"),
        ("ai_draft", "AI Communication Draft"),
    ]

    institution = models.ForeignKey(
        School,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )

    user = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )

    action = models.CharField(
        max_length=30,
        choices=ACTION_CHOICES,
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)

    model_name = models.CharField(
        max_length=100,
        blank=True,
    )

    object_id = models.CharField(
        max_length=50,
        blank=True,
    )

    object_repr = models.CharField(
        max_length=255,
        blank=True,
    )

    details = models.JSONField(
        default=dict,
        blank=True,
    )

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
    )

    timestamp = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(
                fields=["user", "timestamp"],
                name="audit_user_time_idx",
            ),
            models.Index(
                fields=["action", "timestamp"],
                name="audit_action_time_idx",
            ),
            models.Index(
                fields=["institution", "timestamp"],
                name="audit_inst_time_idx",
            ),
            models.Index(
                fields=["model_name", "object_id"],
                name="audit_model_obj_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.get_action_display()} "
            f"{self.model_name} @ {self.timestamp}"
        )


ACTION_CHOICES = AuditLog.ACTION_CHOICES


class CSPViolation(models.Model):
    """Stores Content Security Policy violation reports from browsers.

    Only stores sanitized, non-sensitive data useful for debugging CSP violations.
    Sensitive URL query parameters and script samples are sanitized before storage.
    """

    document_uri = models.URLField(
        max_length=2000,
        help_text="The document in which the violation occurred."
    )
    referrer = models.URLField(
        max_length=2000,
        blank=True,
        null=True,
        help_text="The referrer of the document."
    )
    blocked_uri = models.URLField(
        max_length=2000,
        blank=True,
        null=True,
        help_text="The blocked resource URI (sanitized: query string removed)."
    )
    violated_directive = models.CharField(
        max_length=255,
        help_text="The CSP directive that was violated."
    )
    effective_directive = models.CharField(
        max_length=255,
        blank=True,
        help_text="The effective directive that caused the violation."
    )
    original_policy = models.TextField(
        blank=True,
        help_text="The original CSP policy that was violated."
    )
    disposition = models.CharField(
        max_length=20,
        choices=[("enforce", "Enforce"), ("report", "Report")],
        default="enforce",
        help_text="Whether the policy was enforced or report-only."
    )
    script_sample = models.CharField(
        max_length=80,
        blank=True,
        help_text="Sample of the inline script that caused the violation (truncated)."
    )
    source_file = models.URLField(
        max_length=2000,
        blank=True,
        null=True,
        help_text="The file where the violation occurred."
    )
    line_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Line number in the source file where the violation occurred."
    )
    column_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Column number in the source file where the violation occurred."
    )
    user_agent = models.TextField(
        blank=True,
        help_text="The user agent string of the browser."
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the client."
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="csp_violations",
        help_text="Authenticated user who triggered the violation (if any)."
    )
    institution = models.ForeignKey(
        "schools.School",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="csp_violations",
        help_text="Institution context derived from request (if available)."
    )
    status_code = models.PositiveIntegerField(
        default=0,
        help_text="HTTP status code of the blocked resource (if applicable)."
    )
    resource_type = models.CharField(
        max_length=50,
        blank=True,
        help_text="Type of resource that was blocked (script, style, image, etc.)."
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When the violation was reported."
    )

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["institution", "timestamp"], name="csp_viol_inst_time_idx"),
            models.Index(fields=["violated_directive", "timestamp"], name="csp_viol_directive_idx"),
            models.Index(fields=["blocked_uri", "timestamp"], name="csp_viol_blocked_idx"),
            models.Index(fields=["user", "timestamp"], name="csp_viol_user_time_idx"),
        ]

    def __str__(self):
        return f"CSP Violation: {self.violated_directive} at {self.timestamp}"

    def save(self, *args, **kwargs):
        # Sanitize sensitive data before saving
        self.sanitize()
        super().save(*args, **kwargs)

    def sanitize(self):
        """Sanitize sensitive data before saving."""
        # Sanitize blocked_uri - remove query string
        if self.blocked_uri:
            from urllib.parse import urlparse, urlunparse
            try:
                parsed = urlparse(self.blocked_uri)
                # Rebuild URL without query string and fragment
                self.blocked_uri = urlunparse((
                    parsed.scheme, parsed.netloc, parsed.path, '', '', ''
                ))
            except Exception:
                pass

        # Sanitize document_uri
        if self.document_uri:
            from urllib.parse import urlparse, urlunparse
            try:
                parsed = urlparse(self.document_uri)
                self.document_uri = urlunparse((
                    parsed.scheme, parsed.netloc, parsed.path, '', '', ''
                ))
            except Exception:
                pass

        # Sanitize referrer
        if self.referrer:
            from urllib.parse import urlparse, urlunparse
            try:
                parsed = urlparse(self.referrer)
                self.referrer = urlunparse((
                    parsed.scheme, parsed.netloc, parsed.path, '', '', ''
                ))
            except Exception:
                pass

        # Sanitize source_file
        if self.source_file:
            from urllib.parse import urlparse, urlunparse
            try:
                parsed = urlparse(self.source_file)
                self.source_file = urlunparse((
                    parsed.scheme, parsed.netloc, parsed.path, '', '', ''
                ))
            except Exception:
                pass

        # Truncate script_sample to 80 chars
        if self.script_sample and len(self.script_sample) > 80:
            self.script_sample = self.script_sample[:77] + "..."

        # Redact secrets in script_sample
        if self.script_sample:
            import re
            self.script_sample = re.sub(
                r'(api[_-]?key|token|secret|password|authorization|secret)["\']?\s*[:=]\s*["\']?[^"\'\s]+',
                r'\1=***',
                self.script_sample,
                flags=re.IGNORECASE
            )

        # Truncate user agent
        if self.user_agent and len(self.user_agent) > 500:
            self.user_agent = self.user_agent[:500] + "..."

        # Ensure resource_type is valid
        valid_types = ['script', 'style', 'img', 'font', 'connect', 'object', 'media', 'child', 'frame', 'worker', 'manifest', 'script', 'style']
        if self.resource_type and self.resource_type not in valid_types:
            self.resource_type = ''

    def clean(self):
        super().clean()
        # Validate URLs
        for field_name in ['document_uri', 'referrer', 'blocked_uri', 'source_file']:
            url = getattr(self, field_name, None)
            if url and not (url.startswith('http://') or url.startswith('https://') or url.startswith('data:') or url.startswith('blob:')):
                raise ValidationError({field_name: f"Invalid URL format for {field_name}"})


def get_client_ip(request):
    if request is None:
        return None

    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")

    if forwarded:
        return forwarded.split(",")[0].strip()

    return request.META.get("REMOTE_ADDR")


def record_audit(
    *,
    request=None,
    user=None,
    action,
    model_name="",
    object_id="",
    object_repr="",
    details=None,
):
    """Create an audit entry. `user` falls back to request.user."""
    if user is None and request is not None:
        user = getattr(request, "user", None)

    if user is not None and not user.is_authenticated:
        user = None

    institution = None
    if request is not None:
        institution = getattr(request, "institution", None)
    if institution is None and user is not None:
        institution = getattr(user, "institution", None)

    user_agent = ""
    if request is not None:
        user_agent = request.META.get("HTTP_USER_AGENT", "")[:255]

    AuditLog.objects.create(
        user=user,
        action=action,
        model_name=model_name,
        object_id=object_id,
        object_repr=object_repr,
        details=details or {},
        ip_address=get_client_ip(request),
        institution=institution,
        user_agent=user_agent,
    )

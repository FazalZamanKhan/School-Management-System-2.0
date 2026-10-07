import csv
import json
from urllib.parse import urlparse, urlunparse

from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse
from rest_framework import generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.renderers import BaseRenderer, BrowsableAPIRenderer, JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import AnonRateThrottle

from apps.accounts.access import get_institution
from apps.accounts.permissions import IsAdminRole

from .models import AuditLog, ACTION_CHOICES, CSPViolation, sanitize_script_sample
from .serializers import AuditLogSerializer, CSPViolationSerializer


class CSPViolationThrottle(AnonRateThrottle):
    """Rate limiter for CSP violation reports: 100 requests per minute per IP."""
    scope = "csp_report"
    rate = "100/minute"


class CSPViolationReportView(APIView):
    """Endpoint to receive CSP violation reports from browsers.

    Accepts both the legacy 'csp-report' format and the newer
    Reporting API format.
    """
    permission_classes = [AllowAny]
    throttle_classes = [CSPViolationThrottle]

    def _sanitize_url(self, url):
        """Remove query string and fragment from URL."""
        if not url:
            return ""
        try:
            parsed = urlparse(url)
            return urlunparse((
                parsed.scheme, parsed.netloc, parsed.path, '', '', ''
            ))
        except Exception:
            return url

    def _get_client_ip(self, request):
        """Extract client IP from request."""
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")

    def _extract_report_data(self, report, request):
        """Extract and sanitize report data from the CSP violation report.

        Supports both legacy 'csp-report' format and modern Reporting API v1 format.
        """
        # Handle both legacy 'csp-report' format and modern Reporting API format
        # Legacy format: { "csp-report": { "document-uri": "...", ... } }
        # Modern format: { "type": "csp-violation", "body": { "documentURL": "...", ... } }

        # Check if this is the modern Reporting API format
        body = report.get("body", report)

        # Extract and sanitize fields (supporting both legacy and modern field names)
        document_uri = body.get("document-uri") or body.get("documentURL", "")
        referrer = body.get("referrer") or body.get("referrer", "")  # same key in both formats
        blocked_uri = body.get("blocked-uri") or body.get("blockedURL", "")
        # Modern Reporting API uses effectiveDirective as primary; fallback to violatedDirective for backwards compat
        violated_directive = body.get("violated-directive") or body.get("violatedDirective", "") or body.get("effectiveDirective", "") or body.get("effective-directive", "")
        effective_directive = body.get("effective-directive") or body.get("effectiveDirective", "") or body.get("violatedDirective", "") or body.get("violated-directive", "")
        original_policy = body.get("original-policy") or body.get("originalPolicy", "")
        disposition = body.get("disposition", "enforce")
        script_sample = body.get("script-sample") or body.get("scriptSample", "")
        source_file = body.get("source-file") or body.get("sourceFile", "")
        line_number = body.get("line-number") or body.get("lineNumber")
        column_number = body.get("column-number") or body.get("columnNumber")
        status_code = body.get("status-code") or body.get("statusCode")
        resource_type = body.get("resource-type") or body.get("resourceType", "")
        user_agent = body.get("user-agent") or body.get("userAgent", "")

        # Sanitize URLs
        document_uri = self._sanitize_url(document_uri)
        referrer = self._sanitize_url(referrer)
        blocked_uri = self._sanitize_url(blocked_uri)
        source_file = self._sanitize_url(source_file)

        # Sanitize script sample
        script_sample = sanitize_script_sample(script_sample)

        return {
            "document-uri": document_uri,
            "referrer": referrer,
            "blocked-uri": blocked_uri,
            "violated-directive": violated_directive,
            "effective-directive": effective_directive,
            "original-policy": original_policy,
            "disposition": disposition,
            "script-sample": script_sample,
            "source-file": source_file,
            "line-number": line_number,
            "column-number": column_number,
            "status-code": status_code if status_code is not None else 0,
            "resource-type": resource_type,
            "user-agent": user_agent,
        }

    def post(self, request):
        # Check request body size before processing (max 64KB for CSP reports)
        content_length = request.META.get('CONTENT_LENGTH')
        if content_length and int(content_length) > 65536:  # 64KB max for CSP reports
            return Response(
                {"detail": "Request body too large. Maximum size is 64KB."},
                status=413,
            )

        # Handle both legacy 'csp-report' format and new Reporting API format
        if "csp-report" in request.data:
            report = request.data["csp-report"]
            is_modern = False
        else:
            # New Reporting API format
            report = request.data
            is_modern = True

        # Validate required fields
        required_fields = ["document-uri", "violated-directive"]
        for field in required_fields:
            if is_modern:
                # Modern format: check in body
                body = report.get("body", {})
                field_modern = field.replace("-", "")  # convert to camelCase style
                if field == "document-uri":
                    field_modern = "documentURL"
                elif field == "violated-directive":
                    # Modern Reporting API uses effectiveDirective as primary directive field
                    # Accept either violatedDirective or effectiveDirective
                    field_modern = "violatedDirective"
                    field_modern_alt = "effectiveDirective"
                    if field not in body and field_modern not in body and field_modern_alt not in body:
                        return Response(
                            {"detail": f"Missing required field: {field} (expected violatedDirective or effectiveDirective)"},
                            status=400,
                        )
                    continue
                if field not in body and field_modern not in body:
                    return Response(
                        {"detail": f"Missing required field: {field}"},
                        status=400,
                    )
            else:
                # Legacy format: check in report directly
                if field not in report:
                    return Response(
                        {"detail": f"Missing required field: {field}"},
                        status=400,
                    )

        report_data = self._extract_report_data(report, request)

        # Create the violation record
        violation = CSPViolation.objects.create(
            document_uri=report_data.get("document-uri", ""),
            referrer=report_data.get("referrer", ""),
            blocked_uri=report_data.get("blocked-uri", ""),
            violated_directive=report_data.get("violated-directive", ""),
            effective_directive=report_data.get("effective-directive", ""),
            original_policy=report_data.get("original-policy", ""),
            disposition=report_data.get("disposition", "enforce"),
            script_sample=report_data.get("script-sample", ""),
            source_file=report_data.get("source-file", ""),
            line_number=report_data.get("line-number"),
            column_number=report_data.get("column-number"),
            user_agent=report_data.get("user-agent", ""),
            ip_address=self._get_client_ip(request),
            user=request.user if request.user.is_authenticated else None,
            institution=getattr(request, "institution", None),
            status_code=report_data.get("status-code", 0),
            resource_type=report_data.get("resource-type", ""),
        )

        return Response(status=204)


class AuditLogPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class AuditLogCSVRenderer(BaseRenderer):
    """Minimal CSV renderer so ``?format=csv`` content negotiation succeeds.

    The audit CSV export writes its rows into a plain ``HttpResponse`` inside
    ``AuditLogListView.list``; DRF only negotiates the media type here and
    then passes the view's ``HttpResponse`` through untouched.
    """

    media_type = "text/csv"
    format = "csv"

    def render(self, data, media_type=None, renderer_context=None):
        # Not used by the CSV export itself (that path returns an
        # ``HttpResponse`` directly); this only satisfies DRF's renderer
        # interface when negotiation is exercised for other outcomes.
        return ""


class AuditLogListView(generics.ListAPIView):
    serializer_class = AuditLogSerializer
    permission_classes = [IsAdminRole]
    pagination_class = AuditLogPagination
    renderer_classes = [
        JSONRenderer,
        BrowsableAPIRenderer,
        AuditLogCSVRenderer,
    ]

    def get_queryset(self):
        queryset = AuditLog.objects.select_related("user").all()

        institution = get_institution(self.request)
        if institution is not None:
            queryset = queryset.filter(institution=institution)

        action = self.request.query_params.get("action")
        if action:
            queryset = queryset.filter(action=action)

        user_id = self.request.query_params.get("user")
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        model = self.request.query_params.get("model")
        if model:
            queryset = queryset.filter(model_name=model)

        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(object_repr__icontains=search)
                | Q(model_name__icontains=search)
                | Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
                | Q(user__username__icontains=search)
            )

        date_from = self.request.query_params.get("date_from")
        if date_from:
            queryset = queryset.filter(timestamp__date__gte=date_from)

        date_to = self.request.query_params.get("date_to")
        if date_to:
            queryset = queryset.filter(timestamp__date__lte=date_to)

        object_id = self.request.query_params.get("object_id")
        if object_id:
            queryset = queryset.filter(object_id=object_id)

        return queryset

    def list(self, request, *args, **kwargs):
        fmt = request.query_params.get("format")

        if fmt == "csv":
            queryset = self.filter_queryset(self.get_queryset())[:5000]

            response = HttpResponse(content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = 'attachment; filename="audit_logs.csv"'
            response.write("\ufeff")
            writer = csv.writer(response)
            writer.writerow([
                "Timestamp", "User", "Action", "Model", "Object",
                "Object ID", "IP Address", "Details",
            ])
            for log in queryset:
                writer.writerow([
                    log.timestamp.isoformat(),
                    str(log.user) if log.user else "Anonymous",
                    log.get_action_display(),
                    log.model_name,
                    log.object_repr,
                    log.object_id,
                    log.ip_address or "",
                    json.dumps(log.details, default=str) if log.details else "",
                ])
            return response

        return super().list(request, *args, **kwargs)


class AuditLogActionChoicesView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        return Response([
            {"value": value, "label": label}
            for value, label in ACTION_CHOICES
        ])

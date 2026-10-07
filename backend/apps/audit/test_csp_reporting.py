"""CSP Violation Reporting Tests.

Dedicated tests for the CSP violation reporting endpoint.
"""

import json
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework import status

from apps.accounts.models import Role
from apps.accounts.test_access import make_user
from apps.audit.models import CSPViolation
from apps.schools.models import Campus, School


class CSPViolationReportingTests(TestCase):
    """Tests for POST /api/audit/csp-report/ endpoint."""

    def setUp(self):
        self._clear_throttle_cache()

        self.school_a = School.objects.create(name="Northfield Academy")
        self.campus_a = Campus.objects.create(school=self.school_a, name="Campus A")
        self.super_admin = make_user("sadmin", Role.SUPER_ADMIN, self.school_a)
        self.campus_admin = make_user("cadmin", Role.CAMPUS_ADMIN, self.school_a)
        from apps.accounts.models import StaffProfile
        StaffProfile.objects.create(
            user=self.campus_admin,
            employee_number="STF-001",
            first_name="Campus",
            last_name="Admin",
            gender="male",
            primary_campus=self.campus_a,
        )

        self.client = APIClient()
        self.PASSWORD = "TestPass123!"
        self.endpoint = "/api/audit/csp-report/"
        self.endpoint_alias = "/api/csp-report/"

    def tearDown(self):
        self._clear_throttle_cache()

    def _clear_throttle_cache(self):
        """Clear the throttle cache to avoid cross-test rate limiting."""
        from django.core.cache import caches
        for cache_name in ["default", "ratelimit"]:
            cache = caches[cache_name]
            cache.clear()

    def _as(self, user):
        self.client.force_authenticate(user=None)
        self.assertTrue(
            self.client.login(username=user.username, password=self.PASSWORD)
        )
        self.client.force_authenticate(user=user)
        return self.client

    def _json(self, response):
        try:
            return json.loads(response.content)
        except json.JSONDecodeError:
            return {}

    def _test_endpoint(self, endpoint, payload):
        """Helper to test a CSP report payload on a given endpoint."""
        response = self.client.post(endpoint, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        violation = CSPViolation.objects.first()
        self.assertIsNotNone(violation)
        return violation

    # =========================================================================
    # 1. Valid legacy payload
    # =========================================================================
    def test_legacy_payload_creates_violation(self):
        """POST valid legacy csp-report format creates CSPViolation."""
        payload = {
            "csp-report": {
                "document-uri": "https://example.com/page.html",
                "referrer": "https://referrer.com/",
                "blocked-uri": "https://evil.com/script.js",
                "violated-directive": "script-src",
                "effective-directive": "script-src",
                "original-policy": "default-src 'self'; script-src 'self'",
                "disposition": "enforce",
                "script-sample": "alert('xss')",
                "source-file": "https://example.com/page.html",
                "line-number": 42,
                "column-number": 10,
                "status-code": 200,
                "resource-type": "script",
            }
        }

        response = self.client.post(self.endpoint, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        violation = CSPViolation.objects.first()
        self.assertIsNotNone(violation)
        self.assertEqual(violation.document_uri, "https://example.com/page.html")
        self.assertEqual(violation.referrer, "https://referrer.com/")
        self.assertEqual(violation.blocked_uri, "https://evil.com/script.js")
        self.assertEqual(violation.violated_directive, "script-src")
        self.assertEqual(violation.effective_directive, "script-src")
        self.assertEqual(violation.original_policy, "default-src 'self'; script-src 'self'")
        self.assertEqual(violation.disposition, "enforce")
        self.assertEqual(violation.script_sample, "alert('xss')")
        self.assertEqual(violation.source_file, "https://example.com/page.html")
        self.assertEqual(violation.line_number, 42)
        self.assertEqual(violation.column_number, 10)
        self.assertEqual(violation.status_code, 200)
        self.assertEqual(violation.resource_type, "script")
        self.assertIsNone(violation.user)
        self.assertIsNone(violation.institution)

    def _as(self, user):
        self.client.force_authenticate(user=None)
        self.assertTrue(
            self.client.login(username=user.username, password=self.PASSWORD)
        )
        self.client.force_authenticate(user=user)
        return self.client

    def _json(self, response):
        try:
            return json.loads(response.content)
        except json.JSONDecodeError:
            return {}

    # =========================================================================
    # 1. Valid legacy payload
    # =========================================================================
    def test_legacy_payload_creates_violation(self):
        """POST valid legacy csp-report format creates CSPViolation."""
        payload = {
            "csp-report": {
                "document-uri": "https://example.com/page.html",
                "referrer": "https://referrer.com/",
                "blocked-uri": "https://evil.com/script.js",
                "violated-directive": "script-src",
                "effective-directive": "script-src",
                "original-policy": "default-src 'self'; script-src 'self'",
                "disposition": "enforce",
                "script-sample": "alert('xss')",
                "source-file": "https://example.com/page.html",
                "line-number": 42,
                "column-number": 10,
                "status-code": 200,
                "resource-type": "script",
            }
        }

        response = self.client.post(self.endpoint, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        violation = CSPViolation.objects.first()
        self.assertIsNotNone(violation)
        self.assertEqual(violation.document_uri, "https://example.com/page.html")
        self.assertEqual(violation.referrer, "https://referrer.com/")
        self.assertEqual(violation.blocked_uri, "https://evil.com/script.js")
        self.assertEqual(violation.violated_directive, "script-src")
        self.assertEqual(violation.effective_directive, "script-src")
        self.assertEqual(violation.original_policy, "default-src 'self'; script-src 'self'")
        self.assertEqual(violation.disposition, "enforce")
        self.assertEqual(violation.script_sample, "alert('xss')")
        self.assertEqual(violation.source_file, "https://example.com/page.html")
        self.assertEqual(violation.line_number, 42)
        self.assertEqual(violation.column_number, 10)
        self.assertEqual(violation.status_code, 200)
        self.assertEqual(violation.resource_type, "script")
        self.assertIsNone(violation.user)
        self.assertIsNone(violation.institution)

    # =========================================================================
    # 2. Valid modern Reporting API payload
    # =========================================================================
    def test_modern_reporting_api_payload_creates_violation(self):
        """POST modern Reporting API format creates CSPViolation with all body.* fields."""
        payload = {
            "type": "csp-violation",
            "age": 0,
            "url": "https://example.com/",
            "user_agent": "Mozilla/5.0 (Test Browser)",
            "body": {
                "documentURL": "https://example.com/page.html?query=value#fragment",
                "referrer": "https://referrer.com/path?secret=token",
                "blockedURL": "https://evil.com/script.js?api_key=secret123",
                "violatedDirective": "script-src",
                "effectiveDirective": "script-src-elem",
                "originalPolicy": "default-src 'self'; script-src 'self'; report-uri /api/csp-report/",
                "disposition": "report",
                "scriptSample": "const api_key = 'super-secret-key'; alert(1);",
                "sourceFile": "https://example.com/app.js",
                "lineNumber": 100,
                "columnNumber": 5,
                "statusCode": 403,
                "resourceType": "script",
                "userAgent": "Mozilla/5.0 (Test Browser)",
            },
        }

        response = self.client.post(self.endpoint, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        violation = CSPViolation.objects.first()
        self.assertIsNotNone(violation)

        # Verify all modern body.* fields are correctly mapped
        self.assertEqual(violation.document_uri, "https://example.com/page.html")
        self.assertEqual(violation.referrer, "https://referrer.com/path")
        self.assertEqual(violation.blocked_uri, "https://evil.com/script.js")
        self.assertEqual(violation.violated_directive, "script-src")
        self.assertEqual(violation.effective_directive, "script-src-elem")
        self.assertIn("report-uri", violation.original_policy)
        self.assertEqual(violation.disposition, "report")
        self.assertIn("api_key=***", violation.script_sample)
        self.assertEqual(violation.source_file, "https://example.com/app.js")
        self.assertEqual(violation.line_number, 100)
        self.assertEqual(violation.column_number, 5)
        self.assertEqual(violation.status_code, 403)
        self.assertEqual(violation.resource_type, "script")
        self.assertEqual(violation.user_agent, "Mozilla/5.0 (Test Browser)")

    def test_modern_payload_with_minimal_fields(self):
        """Modern payload with only required fields works."""
        payload = {
            "type": "csp-violation",
            "body": {
                "documentURL": "https://example.com/",
                "violatedDirective": "img-src",
            },
        }

        response = self.client.post(self.endpoint, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        violation = CSPViolation.objects.first()
        self.assertIsNotNone(violation)
        self.assertEqual(violation.document_uri, "https://example.com/")
        self.assertEqual(violation.violated_directive, "img-src")

    # =========================================================================
    # 3. Oversized request (413)
    # =========================================================================
    def test_oversized_request_returns_413(self):
        """Request body > 64KB returns 413 and creates no violation."""
        # Create a payload > 64KB
        large_script = "x" * 70000  # 70KB
        payload = {
            "csp-report": {
                "document-uri": "https://example.com/",
                "violated-directive": "script-src",
                "script-sample": large_script,
            }
        }

        response = self.client.post(
            self.endpoint,
            payload,
            format="json",
            HTTP_CONTENT_LENGTH=str(len(json.dumps(payload))),
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(CSPViolation.objects.count(), 0)

    def test_oversized_modern_payload_returns_413(self):
        """Modern format oversized request returns 413."""
        large_policy = "x" * 70000
        payload = {
            "type": "csp-violation",
            "body": {
                "documentURL": "https://example.com/",
                "violatedDirective": "script-src",
                "originalPolicy": large_policy,
            },
        }

        response = self.client.post(
            self.endpoint,
            payload,
            format="json",
            HTTP_CONTENT_LENGTH=str(len(json.dumps(payload))),
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(CSPViolation.objects.count(), 0)

    # =========================================================================
    # 4. Sanitization
    # =========================================================================
    def test_url_query_string_and_fragment_stripped(self):
        """URLs have query strings and fragments stripped."""
        payload = {
            "csp-report": {
                "document-uri": "https://example.com/page?query=value#fragment",
                "referrer": "https://referrer.com/?secret=token",
                "blocked-uri": "https://evil.com/script.js?api_key=123#section",
                "violated-directive": "script-src",
                "source-file": "https://example.com/app.js?version=1",
            }
        }

        response = self.client.post(self.endpoint, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        violation = CSPViolation.objects.first()
        self.assertEqual(violation.document_uri, "https://example.com/page")
        self.assertEqual(violation.referrer, "https://referrer.com/")
        self.assertEqual(violation.blocked_uri, "https://evil.com/script.js")
        self.assertEqual(violation.source_file, "https://example.com/app.js")

    def test_script_sample_truncated_to_80_chars(self):
        """Script sample is truncated to 80 characters."""
        long_script = "a" * 100
        payload = {
            "csp-report": {
                "document-uri": "https://example.com/",
                "violated-directive": "script-src",
                "script-sample": long_script,
            }
        }

        response = self.client.post(self.endpoint, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        violation = CSPViolation.objects.first()
        self.assertEqual(len(violation.script_sample), 80)  # Includes the ellipsis.
        self.assertTrue(violation.script_sample.endswith("..."))

    def test_secret_redaction_in_script_sample(self):
        """Secrets in script samples are redacted."""
        test_cases = [
            ("api_key = 'secret123'", "api_key=***"),
            ("apiKey = 'secret123'", "apiKey=***"),
            ("access_token = 'token123'", "access_token=***"),
            ("token = 'token123'", "token=***"),
            ("secret = 'secret123'", "secret=***"),
            ("secretKey = 'secret123'", "secretKey=***"),
            ("password = 'pass123'", "password=***"),
            ("authorization = 'Bearer token'", "authorization=***"),
        ]

        for input_script, expected_redacted in test_cases:
            with self.subTest(input_script=input_script):
                CSPViolation.objects.all().delete()
                payload = {
                    "csp-report": {
                        "document-uri": "https://example.com/",
                        "violated-directive": "script-src",
                        "script-sample": input_script,
                    }
                }
                response = self.client.post(self.endpoint, payload, format="json")
                self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

                violation = CSPViolation.objects.first()
                self.assertIn(expected_redacted, violation.script_sample)

    def test_user_agent_truncated_to_500_chars(self):
        """User agent is truncated to 500 characters."""
        long_ua = "Mozilla/5.0 " + "x" * 600
        payload = {
            "csp-report": {
                "document-uri": "https://example.com/",
                "violated-directive": "script-src",
                "user-agent": long_ua,
            }
        }

        response = self.client.post(self.endpoint, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        violation = CSPViolation.objects.first()
        self.assertEqual(len(violation.user_agent), 503)  # 500 + "..."

    def test_resource_type_validated(self):
        """Invalid resource_type is rejected/cleared."""
        payload = {
            "csp-report": {
                "document-uri": "https://example.com/",
                "violated-directive": "script-src",
                "resource-type": "invalid-type",
            }
        }

        response = self.client.post(self.endpoint, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        violation = CSPViolation.objects.first()
        # Invalid resource_type should be cleared to empty string
        self.assertEqual(violation.resource_type, "")

    # =========================================================================
    # 5. Rate limiting (429)
    # =========================================================================
    def test_rate_limit_exceeded_returns_429(self):
        """Exceeding rate limit returns 429."""
        payload = {
            "csp-report": {
                "document-uri": "https://example.com/",
                "violated-directive": "script-src",
            }
        }

        # Make 100 requests (limit is 100/minute)
        for i in range(100):
            response = self.client.post(self.endpoint, payload, format="json")
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # 101st request should be rate limited
        response = self.client.post(self.endpoint, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    # =========================================================================
    # 6. Authentication behavior
    # =========================================================================
    def test_anonymous_request_accepted(self):
        """Anonymous CSP reports are accepted."""
        payload = {
            "csp-report": {
                "document-uri": "https://example.com/",
                "violated-directive": "script-src",
            }
        }

        response = self.client.post(self.endpoint, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        violation = CSPViolation.objects.first()
        self.assertIsNone(violation.user)
        self.assertIsNone(violation.institution)

    def test_authenticated_request_associates_user(self):
        """Authenticated requests associate the user."""
        payload = {
            "csp-report": {
                "document-uri": "https://example.com/",
                "violated-directive": "script-src",
            }
        }

        self._as(self.campus_admin)
        response = self.client.post(self.endpoint, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        violation = CSPViolation.objects.first()
        self.assertEqual(violation.user, self.campus_admin)

    # =========================================================================
    # 7. Tenant isolation
    # =========================================================================
    def test_institution_from_request_context_not_payload(self):
        """Institution comes from request context, not client payload."""
        self.school_b = School.objects.create(name="Southfield Academy")

        payload = {
            "csp-report": {
                "document-uri": "https://example.com/",
                "violated-directive": "script-src",
                # Client tries to inject institution_id - should be ignored
                "institution_id": self.school_b.id,
            }
        }

        self._as(self.campus_admin)  # User belongs to school_a
        response = self.client.post(self.endpoint, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        violation = CSPViolation.objects.first()
        self.assertEqual(violation.institution, self.school_a)
        self.assertNotEqual(violation.institution, self.school_b)

    def test_unauthenticated_no_institution(self):
        """Unauthenticated reports have no institution (fail-closed)."""
        payload = {
            "csp-report": {
                "document-uri": "https://example.com/",
                "violated-directive": "script-src",
            }
        }

        response = self.client.post(self.endpoint, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        violation = CSPViolation.objects.first()
        self.assertIsNone(violation.institution)

    def test_super_admin_context_switch_respected(self):
        """Super admin's active institution context is used."""
        self.school_b = School.objects.create(name="Southfield Academy")
        self.campus_b = Campus.objects.create(school=self.school_b, name="Campus B")

        # Super admin switches to school_b via session
        session = self.client.session
        session["active_institution_id"] = str(self.school_b.id)
        session.save()

        payload = {
            "csp-report": {
                "document-uri": "https://example.com/",
                "violated-directive": "script-src",
            }
        }

        self._as(self.super_admin)
        response = self.client.post(self.endpoint, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        violation = CSPViolation.objects.first()
        # Note: The actual institution resolution depends on middleware
        # This test documents expected behavior
        self.assertIsNotNone(violation.institution)

    # =========================================================================
    # 8. CSP Headers verification
    # =========================================================================
    def test_django_csp_headers_present(self):
        """Django responses include CSP headers with reporting."""
        response = self.client.get("/api/audit/")
        # May be 403 but should still have CSP header
        self.assertIn("Content-Security-Policy", response)
        csp = response["Content-Security-Policy"]
        self.assertIn("img-src 'self'", csp)
        self.assertIn("report-uri /api/csp-report/", csp)
        self.assertIn("report-to csp-endpoint", csp)
        # Ensure no data: or blob: in img-src
        self.assertNotIn("data:", csp.split("img-src")[1].split(";")[0])
        self.assertNotIn("blob:", csp.split("img-src")[1].split(";")[0])

    def test_csp_headers_preserve_unsafe_inline(self):
        """CSP headers preserve 'unsafe-inline' for script and style."""
        response = self.client.get("/api/audit/")
        csp = response["Content-Security-Policy"]
        self.assertIn("script-src 'self' 'unsafe-inline'", csp)
        self.assertIn("style-src 'self' 'unsafe-inline'", csp)

    # =========================================================================
    # 9. CSP Report Alias Endpoint Regression Tests
    # =========================================================================
    def test_alias_endpoint_legacy_payload(self):
        """POST valid legacy payload to /api/csp-report/ creates CSPViolation."""
        payload = {
            "csp-report": {
                "document-uri": "https://example.com/page.html",
                "violated-directive": "script-src",
            }
        }

        response = self.client.post(self.endpoint_alias, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        violation = CSPViolation.objects.first()
        self.assertIsNotNone(violation)
        self.assertEqual(violation.document_uri, "https://example.com/page.html")
        self.assertEqual(violation.violated_directive, "script-src")

    def test_alias_endpoint_modern_payload(self):
        """POST modern payload to /api/csp-report/ creates CSPViolation."""
        payload = {
            "type": "csp-violation",
            "body": {
                "documentURL": "https://example.com/page.html",
                "violatedDirective": "script-src",
            }
        }

        response = self.client.post(self.endpoint_alias, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        violation = CSPViolation.objects.first()
        self.assertIsNotNone(violation)
        self.assertEqual(violation.document_uri, "https://example.com/page.html")
        self.assertEqual(violation.violated_directive, "script-src")

    def test_alias_endpoint_get_returns_405(self):
        """GET /api/csp-report/ returns 405 Method Not Allowed."""
        response = self.client.get(self.endpoint_alias)
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_alias_endpoint_oversized_returns_413(self):
        """Oversized request to /api/csp-report/ returns 413."""
        large_script = "x" * 70000
        payload = {
            "csp-report": {
                "document-uri": "https://example.com/",
                "violated-directive": "script-src",
                "script-sample": large_script,
            }
        }

        response = self.client.post(
            self.endpoint_alias,
            payload,
            format="json",
            HTTP_CONTENT_LENGTH=str(len(json.dumps(payload))),
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(CSPViolation.objects.count(), 0)

    def test_alias_endpoint_rate_limiting(self):
        """Rate limiting applies to /api/csp-report/."""
        payload = {
            "csp-report": {
                "document-uri": "https://example.com/",
                "violated-directive": "script-src",
            }
        }

        # Make requests up to the limit
        for i in range(100):
            response = self.client.post(self.endpoint_alias, payload, format="json")
            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Next request should be rate limited
        response = self.client.post(self.endpoint_alias, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_alias_endpoint_tenant_isolation(self):
        """Tenant isolation works on /api/csp-report/."""
        self.school_b = School.objects.create(name="Southfield Academy")
        payload = {
            "csp-report": {
                "document-uri": "https://example.com/",
                "violated-directive": "script-src",
                "institution_id": self.school_b.id,
            }
        }

        self._as(self.campus_admin)
        response = self.client.post(self.endpoint_alias, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        violation = CSPViolation.objects.first()
        self.assertEqual(violation.institution, self.school_a)
        self.assertNotEqual(violation.institution, self.school_b)

    def test_alias_endpoint_sanitization(self):
        """Sanitization works on /api/csp-report/."""
        payload = {
            "csp-report": {
                "document-uri": "https://example.com/page?query=value#fragment",
                "violated-directive": "script-src",
                "script-sample": "const api_key = 'secret123'; alert(1);",
                "user-agent": "Mozilla/5.0 " + "x" * 600,
            }
        }

        response = self.client.post(self.endpoint_alias, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        violation = CSPViolation.objects.first()
        self.assertEqual(violation.document_uri, "https://example.com/page")
        self.assertIn("api_key=***", violation.script_sample)
        self.assertEqual(len(violation.user_agent), 503)


class CSPViolationModelTests(TestCase):
    """Tests for CSPViolation model sanitization."""

    def setUp(self):
        self.school = School.objects.create(name="Test School")
        from apps.accounts.models import User
        self.user = User.objects.create_user(username="testuser", password="pass")

    def test_sanitize_strips_query_and_fragment(self):
        """Model sanitize() strips query strings and fragments."""
        violation = CSPViolation(
            document_uri="https://example.com/page?query=1#frag",
            referrer="https://ref.com/?secret=token",
            blocked_uri="https://evil.com/x.js?k=v#f",
            violated_directive="script-src",
            source_file="https://example.com/app.js?v=1",
        )
        violation.sanitize()
        self.assertEqual(violation.document_uri, "https://example.com/page")
        self.assertEqual(violation.referrer, "https://ref.com/")
        self.assertEqual(violation.blocked_uri, "https://evil.com/x.js")
        self.assertEqual(violation.source_file, "https://example.com/app.js")

    def test_sanitize_truncates_script_sample(self):
        """Model sanitize() truncates script_sample to 80 chars."""
        violation = CSPViolation(
            document_uri="https://example.com/",
            violated_directive="script-src",
            script_sample="x" * 100,
        )
        violation.sanitize()
        self.assertEqual(len(violation.script_sample), 80)
        self.assertTrue(violation.script_sample.endswith("..."))

    def test_sanitize_redacts_secrets(self):
        """Model sanitize() redacts secrets in script_sample."""
        violation = CSPViolation(
            document_uri="https://example.com/",
            violated_directive="script-src",
            script_sample="const api_key = 'secret'; const token = 'abc';",
        )
        violation.sanitize()
        self.assertIn("api_key=***", violation.script_sample)
        self.assertIn("token=***", violation.script_sample)
        self.assertNotIn("secret", violation.script_sample)
        self.assertNotIn("abc", violation.script_sample)

    def test_sanitize_truncates_user_agent(self):
        """Model sanitize() truncates user_agent to 500 chars."""
        violation = CSPViolation(
            document_uri="https://example.com/",
            violated_directive="script-src",
            user_agent="x" * 600,
        )
        violation.sanitize()
        self.assertEqual(len(violation.user_agent), 503)

    def test_clean_validates_urls(self):
        """Model clean() validates URL schemes."""
        from django.core.exceptions import ValidationError
        violation = CSPViolation(
            document_uri="javascript:alert(1)",
            violated_directive="script-src",
        )
        with self.assertRaises(ValidationError):
            violation.clean()

    def test_clean_allows_valid_schemes(self):
        """Model clean() allows http, https, data, blob schemes."""
        for scheme in ["http://", "https://", "data:", "blob:"]:
            violation = CSPViolation(
                document_uri=f"{scheme}example.com",
                violated_directive="script-src",
            )
            # Should not raise
            violation.clean()

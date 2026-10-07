"""Content Security Policy (CSP) middleware for Django.

This middleware adds a strict Content-Security-Policy header to all responses.
The policy is designed to be strict while allowing all legitimate application
functionality.

CSP Policy:
- default-src 'self'
- script-src 'self' 'unsafe-inline' (for inline theme script in index.html)
- style-src 'self' 'unsafe-inline' (for one inline style in App.jsx)
- img-src 'self' data: blob: (for icons, data: URLs, blob: downloads)
- font-src 'self' (system fonts only)
- connect-src 'self' (API calls share the public origin)
- object-src 'none' (no plugins)
- base-uri 'self'
- form-action 'self'
- frame-ancestors 'none'
- manifest-src 'self'
- worker-src 'self' (service worker)
"""

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin


class ContentSecurityPolicyMiddleware(MiddlewareMixin):
    """Middleware to add Content-Security-Policy header to responses."""

    # CSP policy for production
    CSP_POLICY = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self'; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'; "
        "manifest-src 'self'; "
        "worker-src 'self'; "
        "report-uri /api/csp-report/; "
        "report-to csp-endpoint"
    )

    # CSP policy for development (allows localhost API)
    CSP_POLICY_DEV = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self'; "
        "font-src 'self'; "
        "connect-src 'self' http://127.0.0.1:8000 http://localhost:8000; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'; "
        "manifest-src 'self'; "
        "worker-src 'self'; "
        "report-uri /api/csp-report/; "
        "report-to csp-endpoint"
    )

    def process_response(self, request, response):
        # Only add CSP to HTML responses and API responses
        content_type = response.get('Content-Type', '')
        
        # Skip for non-HTML/JSON responses (static files, media, etc.)
        if not (content_type.startswith('text/html') or content_type.startswith('application/json')):
            return response

        # Don't add CSP to admin panel (may have different requirements)
        if request.path.startswith('/admin/'):
            return response

        # Determine which CSP policy to use
        if settings.DEBUG:
            csp_policy = self.CSP_POLICY_DEV
        else:
            csp_policy = self.CSP_POLICY

        # Add CSP header
        response['Content-Security-Policy'] = csp_policy
        return response

"""API views for message templates."""

from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.access import get_institution
from apps.accounts.middleware import require_active_school
from apps.accounts.models import Role
from apps.accounts.permissions import IsAdminRole

from .models import MessageTemplate


def _get_templates_queryset(request, *, writable=False):
    """Return institution-scoped templates for the current user."""
    if request.user.is_superuser or request.user.has_role(Role.SUPER_ADMIN):
        return MessageTemplate.objects.all()
    institution = require_active_school(request)
    if institution is None:
        return MessageTemplate.objects.none()
    if writable:
        return MessageTemplate.objects.filter(institution=institution)
    return MessageTemplate.objects.filter(
        Q(institution=institution) | Q(institution__isnull=True)
    )


class MessageTemplateListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get(self, request):
        channel = request.query_params.get("channel", "")
        templates = _get_templates_queryset(request)
        if channel:
            templates = templates.filter(channel=channel)

        data = []
        for t in templates:
            data.append({
                "id": t.id,
                "name": t.name,
                "channel": t.channel,
                "channel_display": t.get_channel_display(),
                "subject": t.subject,
                "body": t.body,
                "variables": t.variables,
                "is_active": t.is_active,
                "created_at": t.created_at.isoformat(),
            })
        return Response(data)

    def post(self, request):
        name = request.data.get("name", "").strip()
        body = request.data.get("body", "").strip()

        if not name or not body:
            return Response(
                {"detail": "name and body are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        institution = get_institution(request)
        if require_active_school(request) is None:
            return Response({"detail": "Select a school before creating a template."}, status=400)
        template = MessageTemplate.objects.create(
            name=name,
            channel=request.data.get("channel", "sms"),
            subject=request.data.get("subject", ""),
            body=body,
            variables=request.data.get("variables", []),
            is_active=request.data.get("is_active", True),
            institution=institution,
            created_by=request.user,
        )

        return Response({
            "id": template.id,
            "name": template.name,
            "detail": "Template created.",
        }, status=status.HTTP_201_CREATED)


class MessageTemplateDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def get_object(self, request, pk):
        queryset = _get_templates_queryset(request, writable=request.method in ("PUT", "DELETE"))
        try:
            return queryset.get(pk=pk)
        except MessageTemplate.DoesNotExist:
            return None

    def get(self, request, pk):
        template = self.get_object(request, pk)
        if not template:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            "id": template.id,
            "name": template.name,
            "channel": template.channel,
            "channel_display": template.get_channel_display(),
            "subject": template.subject,
            "body": template.body,
            "variables": template.variables,
            "is_active": template.is_active,
            "created_at": template.created_at.isoformat(),
        })

    def put(self, request, pk):
        template = self.get_object(request, pk)
        if not template:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        template.name = request.data.get("name", template.name)
        template.channel = request.data.get("channel", template.channel)
        template.subject = request.data.get("subject", template.subject)
        template.body = request.data.get("body", template.body)
        template.variables = request.data.get("variables", template.variables)
        template.is_active = request.data.get("is_active", template.is_active)
        template.save()

        return Response({"detail": "Template updated."})

    def delete(self, request, pk):
        template = self.get_object(request, pk)
        if not template:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        template.delete()
        return Response({"detail": "Template deleted."})


class MessageTemplatePreviewView(APIView):
    permission_classes = [IsAuthenticated, IsAdminRole]

    def post(self, request, pk):
        template = _get_templates_queryset(request).filter(pk=pk).first()
        if not template:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        context = request.data.get("context", {})
        rendered = template.render(context)

        return Response({
            "subject": template.subject,
            "body": rendered,
            "channel": template.channel,
        })

from django.utils import timezone
from rest_framework import serializers

from apps.accounts.permissions import IsStaffRole

from .models import SupportTicket, TicketCategory, TicketMessage

MANAGE_ROLES = IsStaffRole.roles


class TicketCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketCategory
        fields = [
            "id",
            "name",
            "description",
            "sort_order",
            "status",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class TicketMessageSerializer(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = TicketMessage
        fields = [
            "id",
            "ticket",
            "author",
            "author_name",
            "body",
            "is_internal",
            "created_at",
        ]
        read_only_fields = ["id", "ticket", "author", "created_at"]

    def get_author_name(self, obj):
        if obj.author:
            return obj.author.get_full_name() or obj.author.username
        return "System"

    def validate_body(self, value):
        if not value.strip():
            raise serializers.ValidationError("Message cannot be empty.")
        return value


class SupportTicketSerializer(serializers.ModelSerializer):
    campus_name = serializers.CharField(source="campus.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    created_by_name = serializers.SerializerMethodField()
    assignee_name = serializers.SerializerMethodField()
    message_count = serializers.IntegerField(source="messages.count", read_only=True)
    can_edit = serializers.SerializerMethodField()
    messages = serializers.SerializerMethodField()

    class Meta:
        model = SupportTicket
        fields = [
            "id",
            "campus",
            "campus_name",
            "category",
            "category_name",
            "subject",
            "description",
            "priority",
            "status",
            "created_by",
            "created_by_name",
            "assignee",
            "assignee_name",
            "resolution_notes",
            "resolved_at",
            "message_count",
            "can_edit",
            "messages",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "created_by",
            "resolved_at",
            "created_at",
            "updated_at",
        ]

    def _request(self):
        return self.context.get("request")

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return "—"

    def get_assignee_name(self, obj):
        if obj.assignee:
            return obj.assignee.get_full_name() or obj.assignee.username
        return None

    def validate_description(self, value):
        if not value or not str(value).strip():
            raise serializers.ValidationError("Description is required.")
        return value.strip()

    def get_can_edit(self, obj):
        request = self._request()
        if not request or not request.user.is_authenticated:
            return False
        return request.user.has_any_role(MANAGE_ROLES)

    def get_messages(self, obj):
        request = self._request()
        show_internal = bool(
            request
            and request.user.is_authenticated
            and request.user.has_any_role(MANAGE_ROLES)
        )
        messages = obj.messages.all()
        if not show_internal:
            messages = messages.filter(is_internal=False)
        return TicketMessageSerializer(messages, many=True).data

    def update(self, instance, validated_data):
        new_status = validated_data.get("status", instance.status)

        if new_status in ("resolved", "closed") and instance.status not in (
            "resolved",
            "closed",
        ):
            instance.resolved_at = timezone.now()

        if new_status in ("open", "in_progress") and instance.resolved_at:
            instance.resolved_at = None

        return super().update(instance, validated_data)


class MyTicketSerializer(SupportTicketSerializer):
    """Public, self-service shape: report + public thread only."""

    class Meta(SupportTicketSerializer.Meta):
        fields = [
            "id",
            "campus",
            "campus_name",
            "category",
            "category_name",
            "subject",
            "description",
            "priority",
            "status",
            "resolution_notes",
            "created_at",
            "updated_at",
            "messages",
        ]
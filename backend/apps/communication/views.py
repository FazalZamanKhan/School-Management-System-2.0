from django.db.models import Q, TextField
from django.db.models.functions import Cast
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAnnouncementRole
from apps.accounts.access import apply_campus_scope, assert_campus_allowed, get_institution
from apps.accounts.scopes import (
    MANAGER_ROLES,
    get_guardian_profile,
    get_teacher_profile,
    is_manager,
    is_parent,
    is_student,
    is_teacher,
    parent_student_class_ids,
    parent_student_ids,
    student_class_ids,
    teacher_class_ids,
    teacher_student_ids,
)
from apps.audit.models import record_audit

from .models import Announcement, Message, Notification
from .serializers import (
    AnnouncementSerializer,
    MessageRecipientSerializer,
    MessageSerializer,
    NotificationSerializer,
)


def _message_recipient_users(user):
    """Users the current user is allowed to message, scoped by role."""
    from apps.accounts.models import User

    base = (
        User.objects
        .filter(is_active=True)
        .exclude(pk=user.pk)
    )
    institution_ids = user.memberships.filter(
        status="active"
    ).values_list("institution_id", flat=True)
    base = base.filter(
        memberships__institution_id__in=institution_ids,
        memberships__status="active",
    ).distinct()

    if is_manager(user):
        return base.order_by("first_name", "last_name")

    staff_roles = MANAGER_ROLES + [
        "hr",
        "accountant",
        "receptionist",
        "librarian",
    ]

    if is_teacher(user):
        student_ids = teacher_student_ids(user)

        guardian_ids = []

        if student_ids:
            from apps.students.models import Student

            guardian_ids = list(
                Student.objects
                .filter(pk__in=student_ids)
                .exclude(guardian_id=None)
                .values_list("guardian_id", flat=True)
            )

        q = (
            Q(memberships__role_assignments__role__in=staff_roles + ["teacher"])
            | Q(student_profile__id__in=student_ids)
        )

        if guardian_ids:
            q |= Q(guardian_profile__id__in=guardian_ids)

        return base.filter(q).distinct().order_by("first_name", "last_name")

    if is_parent(user):
        student_ids = parent_student_ids(user)

        class_ids = []

        if student_ids:
            from apps.students.models import Enrollment

            class_ids = list(
                Enrollment.objects
                .filter(
                    student_id__in=student_ids,
                    status="active",
                )
                .values_list("class_obj_id", flat=True)
            )

        teacher_ids = []

        if class_ids:
            from apps.teachers.models import TeacherAssignment

            teacher_ids = list(
                TeacherAssignment.objects
                .filter(
                    class_obj_id__in=class_ids,
                    status="active",
                )
                .values_list("teacher_id", flat=True)
            )

        q = Q(memberships__role_assignments__role__in=staff_roles)

        if teacher_ids:
            q |= Q(
                memberships__role_assignments__role="teacher",
                teacher_profile__id__in=teacher_ids,
            )

        return base.filter(q).distinct().order_by("first_name", "last_name")

    if is_student(user):
        class_ids = student_class_ids(user)

        teacher_ids = []

        if class_ids:
            from apps.teachers.models import TeacherAssignment

            teacher_ids = list(
                TeacherAssignment.objects
                .filter(
                    class_obj_id__in=class_ids,
                    status="active",
                )
                .values_list("teacher_id", flat=True)
            )

        q = Q(memberships__role_assignments__role__in=staff_roles)

        if teacher_ids:
            q |= Q(
                memberships__role_assignments__role="teacher",
                teacher_profile__id__in=teacher_ids,
            )

        return base.filter(q).distinct().order_by("first_name", "last_name")

    return (
        base
        .filter(memberships__role_assignments__role__in=staff_roles)
        .distinct()
        .order_by("first_name", "last_name")
    )


def scoped_announcement_queryset(request):
    queryset = Announcement.objects.select_related(
        "campus",
        "class_obj",
        "section",
    )
    user = request.user

    institution = getattr(request, "institution", None)
    queryset = queryset.filter(
        Q(campus__school=institution)
        | Q(class_obj__unit__campus__school=institution)
        | Q(campus__isnull=True, class_obj__isnull=True)
    )

    if is_manager(user):
        return apply_campus_scope(
            queryset, request, "campus_id", institution_field="institution"
        )

    queryset = queryset.filter(status="published")
    if is_teacher(user):
        role = "teacher"
        class_ids = teacher_class_ids(user)
    elif is_parent(user):
        role = "parent"
        class_ids = parent_student_class_ids(user)
    elif is_student(user):
        role = "student"
        class_ids = student_class_ids(user)
    elif user.has_role("accountant", institution=institution):
        role = "accountant"
        class_ids = []
    else:
        return queryset.none()

    # audience_roles is a JSON array of role slugs. An empty list means
    # "everyone" (unrestricted). Match both the empty array and the presence
    # of the current role WITHOUT the JSONField __contains lookup: that lookup
    # raises NotSupportedError on SQLite when the QuerySet is EVALUATED
    # (during DRF pagination/count, after this function returns) because
    # QuerySets are lazy. Instead cast the JSON to text and search for the
    # quoted role slug, which is portable across SQLite (TEXT) and
    # PostgreSQL (JSONB::text) and keeps the audience filter in SQL.
    if role is not None:
        queryset = queryset.annotate(
            _audience_roles_txt=Cast(
                "audience_roles", output_field=TextField()
            )
        ).filter(
            Q(audience_roles=[])
            | Q(_audience_roles_txt__icontains=f'"{role}"')
        )
    else:
        queryset = queryset.filter(
            Q(audience_roles=[])
        )
    queryset = queryset.filter(
        Q(class_obj__isnull=True) | Q(class_obj_id__in=class_ids)
    )
    return apply_campus_scope(
        queryset, request, "campus_id", institution_field="institution"
    )


class AnnouncementListView(generics.ListCreateAPIView):
    serializer_class = AnnouncementSerializer
    permission_classes = [IsAnnouncementRole]

    def get_queryset(self):
        queryset = scoped_announcement_queryset(self.request)

        status_filter = self.request.query_params.get("status")

        if status_filter:
            queryset = queryset.filter(status=status_filter)

        category = self.request.query_params.get("category")

        if category:
            queryset = queryset.filter(category=category)

        return queryset

    def perform_create(self, serializer):
        validated = serializer.validated_data
        campus = validated.get("campus")
        class_obj = validated.get("class_obj")
        institution = getattr(self.request, "institution", None)
        if campus and institution and campus.school_id != institution.id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Campus is outside the active institution.")
        if campus:
            assert_campus_allowed(self.request.user, campus.pk)
        if class_obj and institution and class_obj.unit.campus.school_id != institution.id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Class is outside the active institution.")
        if class_obj:
            assert_campus_allowed(self.request.user, class_obj.unit.campus_id)
        instance = serializer.save(institution=institution)

        record_audit(
            request=self.request,
            action="create",
            model_name="Announcement",
            object_id=str(instance.pk),
            object_repr=str(instance),
            details={"status": instance.status},
        )


class AnnouncementDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = AnnouncementSerializer
    permission_classes = [IsAnnouncementRole]

    def get_queryset(self):
        return scoped_announcement_queryset(self.request)

    def perform_update(self, serializer):
        validated = serializer.validated_data
        campus = validated.get("campus", serializer.instance.campus)
        class_obj = validated.get("class_obj", serializer.instance.class_obj)
        institution = getattr(self.request, "institution", None)
        if campus and institution and campus.school_id != institution.id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Campus is outside the active institution.")
        if campus:
            assert_campus_allowed(self.request.user, campus.pk)
        if class_obj and institution and class_obj.unit.campus.school_id != institution.id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Class is outside the active institution.")
        if class_obj:
            assert_campus_allowed(self.request.user, class_obj.unit.campus_id)
        instance = serializer.save(institution=institution)

        record_audit(
            request=self.request,
            action="update",
            model_name="Announcement",
            object_id=str(instance.pk),
            object_repr=str(instance),
            details={"status": instance.status},
        )

    def perform_destroy(self, instance):
        record_audit(
            request=self.request,
            action="delete",
            model_name="Announcement",
            object_id=str(instance.pk),
            object_repr=str(instance),
        )
        instance.delete()


class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        queryset = Notification.objects.filter(
            recipient=self.request.user
        )

        unread_only = self.request.query_params.get("unread_only")

        if unread_only in ("1", "true", "True"):
            queryset = queryset.filter(is_read=False)

        return queryset[:50]


class NotificationMarkReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        notification = (
            Notification.objects
            .filter(pk=pk, recipient=request.user)
            .first()
        )

        if notification is None:
            return Response(
                {"detail": "Not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        notification.is_read = True
        notification.save(update_fields=["is_read"])

        return Response(
            {"detail": "Notification marked as read."}
        )


class NotificationMarkAllReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        count = (
            Notification.objects
            .filter(recipient=request.user, is_read=False)
            .update(is_read=True)
        )

        return Response(
            {"detail": f"{count} notifications marked as read."}
        )


class MessageListView(generics.ListCreateAPIView):
    serializer_class = MessageSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        box = self.request.query_params.get("box", "inbox")
        unread_only = self.request.query_params.get(
            "unread_only"
        ) in ("1", "true", "True")
        q = self.request.query_params.get("q", "").strip()

        if box == "sent":
            queryset = Message.objects.filter(
                sender=user,
                sender_deleted=False,
            )
        elif box == "all":
            queryset = Message.objects.filter(
                Q(sender=user, sender_deleted=False)
                | Q(recipient=user, recipient_deleted=False)
            )
        else:
            queryset = Message.objects.filter(
                recipient=user,
                recipient_deleted=False,
            )

        if unread_only:
            queryset = queryset.filter(is_read=False)

        if q:
            queryset = queryset.filter(
                Q(subject__icontains=q) | Q(body__icontains=q)
            )

        return queryset.select_related(
            "sender",
            "recipient",
        ).order_by("-sent_at")

    def perform_create(self, serializer):
        recipient = serializer.validated_data["recipient"]
        if not _message_recipient_users(self.request.user).filter(
            pk=recipient.pk
        ).exists():
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("This recipient is not available to you.")
        institution = getattr(self.request, "institution", None)
        instance = serializer.save(institution=institution)

        record_audit(
            request=self.request,
            action="create",
            model_name="Message",
            object_id=str(instance.pk),
            object_repr=instance.subject,
            details={"recipient_id": instance.recipient_id},
        )


class MessageDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_message(self, request, pk):
        message = (
            Message.objects
            .filter(pk=pk)
            .select_related("sender", "recipient")
            .first()
        )

        if message is None:
            return None

        is_sender = message.sender_id == request.user.id
        is_recipient = message.recipient_id == request.user.id

        if not (is_sender or is_recipient):
            return None

        if is_sender and message.sender_deleted:
            return None

        if is_recipient and message.recipient_deleted:
            return None

        return message

    def get(self, request, pk):
        message = self.get_message(request, pk)

        if message is None:
            return Response(
                {"detail": "Not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if (
            message.recipient_id == request.user.id
            and not message.is_read
        ):
            message.is_read = True
            message.read_at = timezone.now()
            message.save(update_fields=["is_read", "read_at"])

        return Response(
            MessageSerializer(
                message,
                context={"request": request},
            ).data
        )

    def delete(self, request, pk):
        message = self.get_message(request, pk)

        if message is None:
            return Response(
                {"detail": "Not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if message.sender_id == request.user.id:
            message.sender_deleted = True

        if message.recipient_id == request.user.id:
            message.recipient_deleted = True

        if message.sender_deleted and message.recipient_deleted:
            message.delete()
        else:
            message.save(
                update_fields=[
                    "sender_deleted",
                    "recipient_deleted",
                ]
            )

        record_audit(
            request=request,
            action="delete",
            model_name="Message",
            object_id=str(pk),
            object_repr=message.subject,
        )

        return Response(status=status.HTTP_204_NO_CONTENT)


class MessageThreadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        user = request.user

        root = (
            Message.objects
            .filter(pk=pk)
            .select_related("sender", "recipient")
            .first()
        )

        if root is None:
            return Response(
                {"detail": "Not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        is_sender = root.sender_id == user.id
        is_recipient = root.recipient_id == user.id

        if not (is_sender or is_recipient):
            return Response(
                {"detail": "Not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if is_sender and root.sender_deleted:
            return Response(
                {"detail": "Not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if is_recipient and root.recipient_deleted:
            return Response(
                {"detail": "Not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        thread = [root] + list(
            root.replies
            .filter(
                Q(sender=user, sender_deleted=False)
                | Q(recipient=user, recipient_deleted=False)
            )
            .select_related("sender", "recipient")
        )

        unread_ids = [
            message.pk
            for message in thread
            if message.recipient_id == user.id
            and not message.is_read
        ]

        if unread_ids:
            Message.objects.filter(pk__in=unread_ids).update(
                is_read=True,
                read_at=timezone.now(),
            )

            for message in thread:
                if message.pk in unread_ids:
                    message.is_read = True
                    message.read_at = timezone.now()

        serializer = MessageSerializer(
            thread,
            context={"request": request},
            many=True,
        )

        return Response({"results": serializer.data})


class MessageUnreadCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = (
            Message.objects
            .filter(
                recipient=request.user,
                recipient_deleted=False,
                is_read=False,
            )
            .count()
        )

        return Response({"count": count})


class MessageRecipientsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query = request.query_params.get("q", "").strip()

        users = _message_recipient_users(request.user)

        if query:
            users = users.filter(
                Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(username__icontains=query)
                | Q(email__icontains=query)
            )

        results = [
            {
                "id": user.id,
                "name": user.get_full_name() or user.username,
                "role": user.primary_role or "user",
                "photo_url": user.photo.url if user.photo else None,
            }
            for user in users[:20]
        ]

        return Response({"results": results})

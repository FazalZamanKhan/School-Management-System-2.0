from django.db import transaction
from django.db.models import Q
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.access import apply_campus_scope
from apps.accounts.permissions import IsStaffRole
from apps.audit.models import record_audit
from apps.accounts.scopes import student_class_ids, teacher_class_ids, parent_student_class_ids

from .models import Event, EventAudience, EventRSVP
from .serializers import (
    EventRSVPSerializer,
    EventSerializer,
)


def visible_event_queryset(request):
    queryset = apply_campus_scope(
        Event.objects.select_related("school", "campus", "created_by").prefetch_related("audiences", "rsvps"),
        request, "campus_id", institution_field="school_id",
    )
    user = request.user
    institution = getattr(request, "institution", None)
    if user.is_superuser or user.has_any_role(["super_admin", "admin", "academic"], institution=institution):
        return queryset

    roles = set(user.get_roles(institution))
    audience = Q(audiences__isnull=True) | Q(audiences__audience_type="everyone")
    audience |= Q(audiences__audience_type="role", audiences__role__in=roles)
    if "student" in roles:
        audience |= Q(audiences__audience_type="students")
    if "teacher" in roles:
        audience |= Q(audiences__audience_type="teachers")
    if roles.intersection(IsStaffRole.roles):
        audience |= Q(audiences__audience_type="staff")

    classes = set()
    if "student" in roles:
        classes.update(student_class_ids(user))
    if "teacher" in roles:
        classes.update(teacher_class_ids(user))
    if "parent" in roles:
        classes.update(parent_student_class_ids(user))
    audience |= Q(audiences__audience_type="class", audiences__class_obj_id__in=classes)
    return queryset.filter(status="published").filter(audience).distinct()


class EventListCreateView(generics.ListCreateAPIView):
    serializer_class = EventSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_permissions(self):
        if self.request.method != "GET":
            self.permission_classes = [IsStaffRole]
        else:
            self.permission_classes = [IsAuthenticated]

        return super().get_permissions()

    def get_queryset(self):
        queryset = visible_event_queryset(self.request)

        status_param = self.request.query_params.get("status")

        if status_param:
            queryset = queryset.filter(status=status_param)

        return queryset

    def perform_create(self, serializer):
        school = self.request.user.primary_institution

        if school is None:
            raise ValueError(
                "The user has no active institution membership."
            )

        with transaction.atomic():
            event = serializer.save(
                school=school,
                created_by=self.request.user,
            )

            self._replace_audiences(event)

            record_audit(
                request=self.request,
                action="create",
                model_name="Event",
                object_id=event.id,
                object_repr=event.title,
            )

    def _replace_audiences(self, event):
        audiences = self.request.data.get("audiences")

        if audiences is None:
            return

        event.audiences.all().delete()

        for item in audiences:
            audience = EventAudience(
                event=event,
                audience_type=item.get("audience_type"),
                role=item.get("role", ""),
                class_obj_id=item.get("class_obj") or None,
            )

            audience.full_clean()

            audience.save()


class EventDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = EventSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method != "GET":
            self.permission_classes = [IsStaffRole]
        else:
            self.permission_classes = [IsAuthenticated]

        return super().get_permissions()

    def get_queryset(self):
        return visible_event_queryset(self.request)

    def perform_update(self, serializer):
        event = serializer.save()

        self._replace_audiences(event)

        record_audit(
            request=self.request,
            action="update",
            model_name="Event",
            object_id=event.id,
            object_repr=event.title,
        )

    def perform_destroy(self, instance):
        record_audit(
            request=self.request,
            action="delete",
            model_name="Event",
            object_id=instance.id,
            object_repr=instance.title,
        )
        instance.delete()

    def _replace_audiences(self, event):
        audiences = self.request.data.get("audiences")

        if audiences is None:
            return

        event.audiences.all().delete()

        for item in audiences:
            audience = EventAudience(
                event=event,
                audience_type=item.get("audience_type"),
                role=item.get("role", ""),
                class_obj_id=item.get("class_obj") or None,
            )

            audience.full_clean()

            audience.save()


class EventRSVPView(generics.CreateAPIView):
    serializer_class = EventRSVPSerializer
    permission_classes = [IsAuthenticated]

    def create(self, request, *args, **kwargs):
        event = visible_event_queryset(request).filter(pk=kwargs["pk"]).first()
        if event is None:
            return Response(
                {"detail": "Event not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        rsvp, _ = EventRSVP.objects.update_or_create(
            event=event,
            user=request.user,
            defaults={
                "response": request.data.get(
                    "response",
                    "yes",
                )
            },
        )

        serializer = self.get_serializer(rsvp)

        return Response(
            serializer.data,
            status=status.HTTP_200_OK,
        )

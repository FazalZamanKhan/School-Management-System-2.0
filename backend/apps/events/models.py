from django.conf import settings
from django.db import models

from apps.schools.models import Campus, Class, School


class Event(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("published", "Published"),
        ("cancelled", "Cancelled"),
    ]

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="events",
    )

    campus = models.ForeignKey(
        Campus,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )

    title = models.CharField(max_length=200)

    description = models.TextField(blank=True)

    location = models.CharField(
        max_length=200,
        blank=True,
    )

    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="draft",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_events",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_datetime"]

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.end_datetime <= self.start_datetime:
            raise ValidationError(
                "End datetime must be later than start datetime."
            )

        if self.campus_id and self.school_id:
            if self.campus.school_id != self.school_id:
                raise ValidationError(
                    "Campus must belong to the selected school."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class EventAudience(models.Model):
    AUDIENCE_TYPE_CHOICES = [
        ("everyone", "Everyone"),
        ("students", "Students"),
        ("teachers", "Teachers"),
        ("staff", "Staff"),
        ("class", "Class"),
        ("role", "Role"),
    ]

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="audiences",
    )

    audience_type = models.CharField(
        max_length=20,
        choices=AUDIENCE_TYPE_CHOICES,
    )

    role = models.CharField(
        max_length=30,
        blank=True,
        help_text="Used when audience_type is 'role'.",
    )

    class_obj = models.ForeignKey(
        Class,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="event_audiences",
        help_text="Used when audience_type is 'class'.",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["audience_type"]

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.audience_type == "role" and not self.role:
            raise ValidationError(
                {"role": "Role is required for a role audience."}
            )

        if self.audience_type == "class" and not self.class_obj:
            raise ValidationError(
                {
                    "class_obj": (
                        "Class is required for a class audience."
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        if self.audience_type == "role":
            return f"{self.event.title} -> {self.role}"

        if self.audience_type == "class":
            return f"{self.event.title} -> {self.class_obj}"

        return f"{self.event.title} -> {self.get_audience_type_display()}"


class EventRSVP(models.Model):
    RESPONSE_CHOICES = [
        ("yes", "Attending"),
        ("no", "Not Attending"),
        ("maybe", "Maybe"),
    ]

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="rsvps",
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="event_rsvps",
    )

    response = models.CharField(
        max_length=10,
        choices=RESPONSE_CHOICES,
        default="yes",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "user"],
                name="unique_rsvp_per_event_user",
            )
        ]

    def __str__(self):
        return f"{self.user.username} - {self.event.title}"

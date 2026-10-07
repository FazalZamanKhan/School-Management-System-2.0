from rest_framework import serializers

from .models import Event, EventAudience, EventRSVP


class EventAudienceSerializer(serializers.ModelSerializer):
    class_label = serializers.CharField(
        source="class_obj.name",
        read_only=True,
    )
    audience_type_label = serializers.CharField(
        source="get_audience_type_display",
        read_only=True,
    )

    class Meta:
        model = EventAudience
        fields = [
            "id",
            "event",
            "audience_type",
            "audience_type_label",
            "role",
            "class_obj",
            "class_label",
        ]


class EventRSVPSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = EventRSVP
        fields = [
            "id",
            "event",
            "user",
            "user_name",
            "response",
            "created_at",
        ]

    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.username


class EventSerializer(serializers.ModelSerializer):
    school_name = serializers.CharField(
        source="school.name",
        read_only=True,
    )
    campus_name = serializers.CharField(
        source="campus.name",
        read_only=True,
    )
    created_by_name = serializers.SerializerMethodField()
    status_label = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )
    audiences = EventAudienceSerializer(
        many=True,
        read_only=True,
    )
    rsvp_count = serializers.SerializerMethodField()
    my_rsvp = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            "id",
            "school",
            "school_name",
            "campus",
            "campus_name",
            "title",
            "description",
            "location",
            "start_datetime",
            "end_datetime",
            "status",
            "status_label",
            "created_by",
            "created_by_name",
            "created_at",
            "audiences",
            "rsvp_count",
            "my_rsvp",
        ]
        read_only_fields = [
            "school",
            "school_name",
            "campus_name",
            "status_label",
            "created_by",
            "created_by_name",
            "created_at",
            "audiences",
            "rsvp_count",
            "my_rsvp",
        ]

    def validate(self, attrs):
        start = attrs.get("start_datetime", getattr(self.instance, "start_datetime", None))
        end = attrs.get("end_datetime", getattr(self.instance, "end_datetime", None))
        if start is not None and end is not None and end <= start:
            raise serializers.ValidationError({
                "end_datetime": "End datetime must be later than start datetime."
            })
        return attrs

    def get_created_by_name(self, obj):
        if obj.created_by is None:
            return None

        return (
            obj.created_by.get_full_name()
            or obj.created_by.username
        )

    def get_rsvp_count(self, obj):
        return obj.rsvps.filter(response="yes").count()

    def get_my_rsvp(self, obj):
        request = self.context.get("request")

        if request is None or not request.user.is_authenticated:
            return None

        rsvp = obj.rsvps.filter(user=request.user).first()

        if rsvp is None:
            return None

        return rsvp.response

from rest_framework import serializers

from .models import Allocation, Hostel, Room


class RoomSerializer(serializers.ModelSerializer):
    occupied = serializers.IntegerField(read_only=True)
    is_full = serializers.BooleanField(read_only=True)

    class Meta:
        model = Room
        fields = [
            "id",
            "hostel",
            "room_number",
            "capacity",
            "occupied",
            "is_full",
            "notes",
        ]


class HostelSerializer(serializers.ModelSerializer):
    campus_name = serializers.CharField(
        source="campus.name", read_only=True
    )
    total_capacity = serializers.IntegerField(read_only=True)
    occupied = serializers.IntegerField(read_only=True)
    rooms = RoomSerializer(many=True, read_only=True)

    class Meta:
        model = Hostel
        fields = [
            "id",
            "campus",
            "campus_name",
            "name",
            "warden",
            "gender",
            "address",
            "total_capacity",
            "occupied",
            "rooms",
            "created_at",
        ]
        read_only_fields = ["created_at"]


class AllocationSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(
        source="student.full_name", read_only=True
    )
    admission_number = serializers.CharField(
        source="student.admission_number", read_only=True
    )
    room_label = serializers.CharField(
        source="room.__str__", read_only=True
    )

    class Meta:
        model = Allocation
        fields = [
            "id",
            "room",
            "room_label",
            "student",
            "student_name",
            "admission_number",
            "start_date",
            "end_date",
            "status",
            "created_at",
        ]
        read_only_fields = ["created_at"]

    def validate(self, attrs):
        room = attrs.get("room")
        status_val = attrs.get("status", "active")
        if room and status_val == "active" and room.is_full:
            raise serializers.ValidationError({"room": "This room is already full."})
        return attrs

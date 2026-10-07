from datetime import datetime, timedelta, timezone

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.events.models import Event
from apps.events.serializers import EventSerializer


class EventTimeValidationTests(SimpleTestCase):
    def setUp(self):
        self.start = datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)

    def test_serializer_requires_end_after_start(self):
        for end in (self.start, self.start - timedelta(minutes=1)):
            with self.subTest(end=end):
                serializer = EventSerializer(data={
                    "title": "Assembly",
                    "start_datetime": self.start.isoformat(),
                    "end_datetime": end.isoformat(),
                })
                self.assertFalse(serializer.is_valid())
                self.assertIn("end_datetime", serializer.errors)

        serializer = EventSerializer(data={
            "title": "Assembly",
            "start_datetime": self.start.isoformat(),
            "end_datetime": (self.start + timedelta(hours=1)).isoformat(),
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_partial_update_checks_existing_end(self):
        event = Event(
            title="Assembly",
            school_id=1,
            start_datetime=self.start,
            end_datetime=self.start + timedelta(hours=1),
        )
        serializer = EventSerializer(
            event,
            data={"start_datetime": (self.start + timedelta(hours=2)).isoformat()},
            partial=True,
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("end_datetime", serializer.errors)

    def test_model_rejects_equal_times(self):
        event = Event(
            title="Assembly",
            school_id=1,
            start_datetime=self.start,
            end_datetime=self.start,
        )
        with self.assertRaises(ValidationError):
            event.clean()

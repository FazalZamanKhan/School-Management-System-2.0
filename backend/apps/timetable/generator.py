"""Greedy timetable generator.

Builds a weekly timetable for every section of a campus from existing
TeacherAssignments and SubjectOfferings:

- Each subject assigned to a section gets ``lessons_per_subject``
  periods per week.
- A section can only be in one place at a time; a teacher cannot teach
  two sections at once. The database-level unique constraints mirror
  these rules, and the in-memory busy map is overlap-aware: a slot is
  free only if it does not overlap any already-booked period for that
  resource on the same day (periods may share wall-clock time).
- Subjects are interleaved and slot order is rotated per lesson so the
  schedule spreads instead of clustering.

Unplaceable lessons (e.g. a teacher overloaded beyond capacity) are
reported back rather than failing the whole run.

Optional class_id and section_id parameters allow generating for
specific classes/sections instead of the entire campus.
"""

import random

from django.db import transaction

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday"]


def generate_timetable(
    campus,
    academic_year,
    lessons_per_subject=5,
    days=None,
    replace=True,
    seed=None,
    class_id=None,
    section_id=None,
):
    """Generate entries for one campus + academic year.

    Returns a stats dict:
        {
          "sections": n,
          "requirements": n,
          "created": n,
          "unplaced": [{section, subject, reason}],
        }
    """
    from apps.schools.models import Section
    from apps.teachers.models import TeacherAssignment
    from .models import Period, TimetableEntry

    if days is None:
        days = DAYS

    rng = random.Random(seed)

    periods = list(
        Period.objects.filter(
            status="active",
            is_break=False,
        ).order_by("number")
    )

    if not periods:
        raise ValueError(
            "No teaching periods configured. Add active non-break periods "
            "before generating a timetable."
        )

    # Filter assignments by class/section if provided
    assignment_filters = {
        "campus": campus,
        "academic_year": academic_year,
        "status": "active",
    }

    if class_id:
        from apps.schools.models import Class
        class_obj = Class.objects.filter(pk=class_id).first()
        if not class_obj:
            raise ValueError(f"Class {class_id} not found.")
        assignment_filters["class_obj"] = class_obj

    if section_id:
        assignment_filters["section_id"] = section_id

    assignments = list(
        TeacherAssignment.objects
        .filter(**assignment_filters)
        .select_related("class_obj", "section", "subject", "teacher")
    )

    if not assignments:
        raise ValueError(
            "No active teacher assignments found for this campus "
            "and academic year. Assign teachers to subjects/classes before "
            "generating a timetable."
        )

    # Requirements per section.
    section_map = {}

    for assignment in assignments:
        key = assignment.section_id or assignment.class_obj_id
        entry = section_map.setdefault(
            key,
            {
                "class_obj": assignment.class_obj,
                "section": assignment.section,
                "items": [],
            },
        )
        entry["items"].append((assignment.subject, assignment.teacher))

    slots = [
        (day, period)
        for day in days
        for period in periods
    ]

    created = 0
    unplaced = []
    sections_covered = 0

    from .models import periods_overlap

    period_by_id = {p.id: p for p in periods}

    busy_teacher = {}
    busy_section = {}

    def _mark(teacher_id, section_key, slot):
        day, period = slot
        busy_teacher.setdefault((teacher_id, day), set()).add(period.id)
        busy_section.setdefault((section_key, day), set()).add(period.id)

    def _overlaps_any(period, booked_ids):
        return any(
            periods_overlap(period, period_by_id[pid])
            for pid in booked_ids
        )

    def _free(teacher_id, section_key, slot):
        day, period = slot
        if _overlaps_any(
            period, busy_teacher.get((teacher_id, day), ())
        ):
            return False
        if _overlaps_any(
            period, busy_section.get((section_key, day), ())
        ):
            return False
        return True

    with transaction.atomic():
        if replace:
            delete_filters = {
                "campus": campus,
                "academic_year": academic_year,
            }
            if class_id:
                from apps.schools.models import Class
                class_obj = Class.objects.filter(pk=class_id).first()
                if class_obj:
                    delete_filters["class_obj"] = class_obj

            if section_id:
                delete_filters["section_id"] = section_id

            TimetableEntry.objects.filter(**delete_filters).delete()

        for key in sorted(section_map):
            info = section_map[key]
            section_key = (
                info["section"].id if info["section"] else key
            )

            # Interleave subjects: [A,B,C,A,B,C...] not AAA BBB CCC.
            pool = []
            counters = {}

            for subject, teacher in info["items"]:
                for _ in range(lessons_per_subject):
                    index = counters.get(subject.id, 0)
                    pool.append((index, subject.id, subject, teacher))
                    counters[subject.id] = index + 1

            pool.sort(key=lambda item: (item[0], rng.random()))

            placed_any = False

            for _, _, subject, teacher in pool:
                order = list(slots)
                rng.shuffle(order)

                placed = False

                for slot in order:
                    if _free(teacher.id, section_key, slot):
                        day, period = slot

                        TimetableEntry.objects.create(
                            academic_year=academic_year,
                            campus=campus,
                            class_obj=info["class_obj"],
                            section=info["section"],
                            subject=subject,
                            teacher=teacher,
                            period=period,
                            day=day,
                        )

                        _mark(teacher.id, section_key, slot)
                        created += 1
                        placed = True
                        placed_any = True
                        break

                if not placed:
                    unplaced.append({
                        "section": (
                            info["section"].name
                            if info["section"]
                            else info["class_obj"].name
                        ),
                        "subject": subject.name,
                        "reason": f"No free slot for {teacher.full_name}",
                    })

            if placed_any:
                sections_covered += 1

    return {
        "sections": sections_covered,
        "sections_total": len(section_map),
        "requirements": sum(len(v["items"]) for v in section_map.values()),
        "created": created,
        "unplaced": unplaced[:50],
        "unplaced_count": len(unplaced),
    }

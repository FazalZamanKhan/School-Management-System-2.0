"""Manual student query diagnostic; safe to import during test discovery."""

import os


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
    import django
    django.setup()

    from django.db import connection, reset_queries
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIRequestFactory
    from rest_framework.request import Request
    from apps.students.views import StudentListCreateView

    user = get_user_model().objects.filter(username__in=["Flora", "admin"]).first()
    if user is None:
        print("Admin user not found")
        return 1
    request = Request(APIRequestFactory().get("/api/students/"))
    request.user = user
    request.institution = user.primary_institution
    reset_queries()
    view = StudentListCreateView()
    view.request = request
    list(view.get_queryset())
    print("Queries:", len(connection.queries))
    for query in connection.queries:
        print(f"{float(query['time']):.4f}s: {query['sql'][:200]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

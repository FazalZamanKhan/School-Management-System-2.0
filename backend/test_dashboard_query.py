"""Manual dashboard query diagnostic; safe to import during test discovery."""

import os
import time


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

    import django
    django.setup()

    from django.contrib.auth import get_user_model
    from django.db import connection, reset_queries
    from django.test import RequestFactory
    from apps.accounts.access import campus_access, get_institution
    from apps.dashboard.views import _institution_overview_counts

    admin_user = get_user_model().objects.filter(username="Flora").first()
    if not admin_user:
        print("Admin user not found")
        return 1

    print(f"Found admin user: {admin_user.username} (id={admin_user.id})")
    request = RequestFactory().get("/api/dashboard/overview/")
    request.user = admin_user
    print(f"Institution: {get_institution(request)}")
    print(f"Campus access: {campus_access(request)}")

    reset_queries()
    started = time.time()
    result = _institution_overview_counts(request)
    print(f"Result: {result}")
    print(f"Time: {time.time() - started:.3f}s")
    print(f"Queries executed: {len(connection.queries)}")
    for index, query in enumerate(connection.queries):
        print(f"\nQuery {index + 1} ({float(query['time']):.3f}s):")
        print(query["sql"][:500])
    print(f"\nTotal query time: {sum(float(q['time']) for q in connection.queries):.3f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

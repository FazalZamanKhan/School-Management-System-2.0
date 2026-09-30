from django.urls import path

from .branding_views import SchoolBrandingView
from .platform_views import (
    CurrentModulesView,
    TenantDetailView,
    TenantListCreateView,
)
from .tenant_views import PublicTenantConfigView
from .views import (
    AcademicUnitListView,
    AcademicYearActionView,
    AcademicYearDetailView,
    AcademicYearListView,
    CampusViewSet,
    ClassListView,
    SchoolViewSet,
    SectionDetailView,
    SectionListView,
    SubjectListView,
    SubjectOfferingListView,
    TermActionView,
    TermDetailView,
    TermListView,
)

urlpatterns = [
    path("", SchoolViewSet.as_view({"get": "list"}), name="school-list"),
    path("<int:pk>/pause/", SchoolViewSet.as_view({"post": "pause"}), name="school-pause"),
    path("<int:pk>/activate/", SchoolViewSet.as_view({"post": "activate"}), name="school-activate"),
    path("<int:pk>/archive/", SchoolViewSet.as_view({"post": "archive"}), name="school-archive"),
    path("<int:pk>/unarchive/", SchoolViewSet.as_view({"post": "unarchive"}), name="school-unarchive"),
    path("campuses/", CampusViewSet.as_view({"get": "list", "post": "create"}), name="campus-list"),
    path(
        "campuses/<int:pk>/",
        CampusViewSet.as_view({
            "get": "retrieve",
            "patch": "partial_update",
            "put": "update",
            "delete": "destroy",
        }),
        name="campus-detail",
    ),
    path(
        "campuses/<int:pk>/admin/",
        CampusViewSet.as_view({"get": "admin"}),
        name="campus-admin",
    ),
    path(
        "campuses/<int:pk>/assign_admin/",
        CampusViewSet.as_view({"post": "assign_admin"}),
        name="campus-assign-admin",
    ),
    path(
        "campuses/<int:pk>/remove_admin/",
        CampusViewSet.as_view({"post": "remove_admin"}),
        name="campus-remove-admin",
    ),
    path("units/", AcademicUnitListView.as_view(), name="academic-unit-list"),
    path("classes/", ClassListView.as_view(), name="class-list"),
    path("sections/", SectionListView.as_view(), name="section-list"),
    path("sections/<int:pk>/", SectionDetailView.as_view(), name="section-detail"),
    path("academic-years/", AcademicYearListView.as_view(), name="academic-year-list"),
    path("academic-years/<int:pk>/", AcademicYearDetailView.as_view(), name="academic-year-detail"),
    path("academic-years/<int:pk>/<str:action>/", AcademicYearActionView.as_view(), name="academic-year-action"),
    path("terms/", TermListView.as_view(), name="term-list"),
    path("terms/<int:pk>/", TermDetailView.as_view(), name="term-detail"),
    path("terms/<int:pk>/<str:action>/", TermActionView.as_view(), name="term-action"),
    path("subjects/", SubjectListView.as_view(), name="subject-list"),
    path("offerings/", SubjectOfferingListView.as_view(), name="subject-offering-list"),
    path("branding/", SchoolBrandingView.as_view(), name="school-branding"),
    path("tenant-config/", PublicTenantConfigView.as_view(), name="public-tenant-config"),
    path("modules/current/", CurrentModulesView.as_view(), name="current-modules"),
    path("tenants/", TenantListCreateView.as_view(), name="tenant-list"),
    path("tenants/<int:pk>/", TenantDetailView.as_view(), name="tenant-detail"),
    path(
        "tenants/<int:pk>/admins/",
        SchoolViewSet.as_view({"get": "admins"}),
        name="tenant-admins",
    ),
    path(
        "tenants/<int:pk>/assign_admin/",
        SchoolViewSet.as_view({"post": "assign_admin"}),
        name="tenant-assign-admin",
    ),
    path(
        "tenants/<int:pk>/remove_admin/",
        SchoolViewSet.as_view({"post": "remove_admin"}),
        name="tenant-remove-admin",
    ),
]

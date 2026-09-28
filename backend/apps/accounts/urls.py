from django.urls import path

from .google_sso import GoogleConfigView, GoogleLoginView
from .email_verify_views import (
    EmailVerificationConfirmView,
    EmailVerificationSendView,
)
from .twofa_views import (
    TwoFAActivateView,
    TwoFABackupCodesView,
    TwoFADisableView,
    TwoFASetupView,
    TwoFAStatusView,
    TwoFAVerifyBackupCodeView,
)
from .views import (
    AccountLockoutStatusView,
    ActiveCampusView,
    ActiveInstitutionView,
    AdminUnlockAccountView,
    AdminPasswordResetView,
    AdminUsernameChangeView,
    CurrentUserView,
    LoginFailedView,
    LoginView,
    LogoutView,
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    PermissionDetailView,
    PermissionListView,
    RoleListView,
    RolePermissionCreateView,
    RolePermissionDeleteView,
    RolePermissionListView,
    SessionListView,
    SessionRevokeAllView,
    SessionRevokeView,
    SuperAdminSchoolCreateView,
    SuperAdminSchoolListView,
    SuperAdminSchoolSwitchView,
    UserPermissionCreateView,
    UserPermissionDeleteView,
    UserPermissionListView,
    UserPermissionsSummaryView,
    UserProfileView,
    csrf_token,
)

urlpatterns = [
    path("csrf/", csrf_token, name="csrf-token"),
    path("login/", LoginView.as_view(), name="login"),
    path(
        "login/failed/",
        LoginFailedView.as_view(),
        name="login-failed",
    ),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("me/", CurrentUserView.as_view(), name="current-user"),
    path(
        "active-institution/",
        ActiveInstitutionView.as_view(),
        name="active-institution",
    ),
    path(
        "active-campus/",
        ActiveCampusView.as_view(),
        name="active-campus",
    ),
    path(
        "users/<int:pk>/",
        UserProfileView.as_view(),
        name="user-profile",
    ),
    path("roles/", RoleListView.as_view(), name="role-list"),
    path(
        "password-reset/",
        PasswordResetRequestView.as_view(),
        name="password-reset",
    ),
    path(
        "password-reset/confirm/",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    path(
        "password-change/",
        PasswordChangeView.as_view(),
        name="password-change",
    ),
    path(
        "lockout/status/",
        AccountLockoutStatusView.as_view(),
        name="lockout-status",
    ),
    path(
        "admin/unlock/<int:user_id>/",
        AdminUnlockAccountView.as_view(),
        name="admin-unlock-account",
    ),
    path(
        "users/<int:user_id>/reset-password/",
        AdminPasswordResetView.as_view(),
        name="admin-password-reset",
    ),
    path(
        "users/<int:user_id>/change-username/",
        AdminUsernameChangeView.as_view(),
        name="admin-change-username",
    ),
    path("sessions/", SessionListView.as_view(), name="session-list"),
    path("sessions/revoke-all/", SessionRevokeAllView.as_view(), name="session-revoke-all"),
    path("sessions/<int:session_id>/", SessionRevokeView.as_view(), name="session-revoke"),
    path("2fa/status/", TwoFAStatusView.as_view(), name="twofa-status"),
    path("2fa/setup/", TwoFASetupView.as_view(), name="twofa-setup"),
    path("2fa/activate/", TwoFAActivateView.as_view(), name="twofa-activate"),
    path("2fa/disable/", TwoFADisableView.as_view(), name="twofa-disable"),
    path("2fa/backup-codes/", TwoFABackupCodesView.as_view(), name="twofa-backup-codes"),
    path("2fa/verify-backup/", TwoFAVerifyBackupCodeView.as_view(), name="twofa-verify-backup"),
    
    # Permission Management
    path("permissions/", PermissionListView.as_view(), name="permission-list"),
    path("permissions/<int:pk>/", PermissionDetailView.as_view(), name="permission-detail"),
    path("role-permissions/", RolePermissionListView.as_view(), name="role-permission-list"),
    path("role-permissions/create/", RolePermissionCreateView.as_view(), name="role-permission-create"),
    path("role-permissions/<int:pk>/", RolePermissionDeleteView.as_view(), name="role-permission-delete"),
    path("user-permissions/", UserPermissionListView.as_view(), name="user-permission-list"),
    path("user-permissions/create/", UserPermissionCreateView.as_view(), name="user-permission-create"),
    path("user-permissions/<int:pk>/", UserPermissionDeleteView.as_view(), name="user-permission-delete"),
    path("user-permissions/summary/<int:user_id>/", UserPermissionsSummaryView.as_view(), name="user-permissions-summary"),
    
    path(
        "google/config/",
        GoogleConfigView.as_view(),
        name="google-config",
    ),
    path(
        "google/login/",
        GoogleLoginView.as_view(),
        name="google-login",
    ),

    # Email verification
    path(
        "email-verify/send/",
        EmailVerificationSendView.as_view(),
        name="email-verify-send",
    ),
    path(
        "email-verify/confirm/",
        EmailVerificationConfirmView.as_view(),
        name="email-verify-confirm",
    ),

    # Super Admin School Management
    path(
        "super-admin/schools/",
        SuperAdminSchoolListView.as_view(),
        name="super-admin-school-list",
    ),
    path(
        "super-admin/schools/create/",
        SuperAdminSchoolCreateView.as_view(),
        name="super-admin-school-create",
    ),
    path(
        "super-admin/switch/",
        SuperAdminSchoolSwitchView.as_view(),
        name="super-admin-switch",
    ),
]

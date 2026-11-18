from django.urls import path

from core import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("search/", views.search, name="search"),
    path("reports/", views.reports, name="reports"),
    path("settings/", views.settings_view, name="settings"),
    path("settings/appearance/", views.appearance, name="appearance"),
    path("settings/appearance/theme/", views.appearance_theme_save, name="appearance_theme_save"),
    path("settings/activity/", views.activity_log, name="activity_log"),
    path("settings/backup/", views.backup_restore, name="backup_restore"),
    path("settings/backup/now/", views.backup_now, name="backup_now"),
    path("accounts/login/", views.AppLoginView.as_view(), name="login"),
    path("accounts/logout/", views.AppLogoutView.as_view(), name="logout"),
    path("accounts/lock/", views.lock_session, name="lock"),
]

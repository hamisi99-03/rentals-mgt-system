from django.urls import path

from reports import views

urlpatterns = [
    path("reports/", views.reports_home, name="reports"),
    path("reports/arrears/", views.arrears, name="report_arrears"),
    path("reports/monthly/", views.monthly, name="report_monthly"),
    path("reports/occupancy/", views.occupancy, name="report_occupancy"),
    path("reports/statement/", views.statement, name="report_statement"),
    path("reports/tax/", views.tax, name="report_tax"),
    path("reports/reminders/", views.reminders, name="overdue_reminders"),
]

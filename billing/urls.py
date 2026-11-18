from django.urls import path

from billing import views

urlpatterns = [
    path("billing/", views.billing_run, name="billing"),
    path("billing/generate/", views.billing_generate, name="billing_generate"),
    path("billing/invoices/", views.invoices, name="invoices"),
    path("billing/invoices/pdf/", views.invoice_period_pdf, name="invoice_period_pdf"),
    path("billing/invoices/<int:pk>/", views.invoice_detail, name="invoice_detail"),
    path("billing/invoices/<int:pk>/pdf/", views.invoice_pdf, name="invoice_pdf"),
    path("billing/charge-types/", views.charge_types, name="charge_types"),
    path("billing/charge-types/<int:pk>/edit/", views.charge_type_edit, name="charge_type_edit"),
    path("billing/charge-types/<int:pk>/toggle/", views.charge_type_toggle, name="charge_type_toggle"),
    path("billing/leases/<int:lease_pk>/charges/", views.lease_charges, name="lease_charges"),
    path("billing/lease-charges/<int:pk>/edit/", views.lease_charge_edit, name="lease_charge_edit"),
    path("billing/lease-charges/<int:pk>/toggle/", views.lease_charge_toggle, name="lease_charge_toggle"),
    path("billing/utilities/", views.utility_types, name="utility_types"),
    path("billing/utilities/<int:pk>/edit/", views.utility_type_edit, name="utility_type_edit"),
    path("billing/utilities/<int:pk>/toggle/", views.utility_type_toggle, name="utility_type_toggle"),
    path("billing/meter-readings/", views.meter_readings, name="meter_readings"),
    path("billing/meter-readings/<int:pk>/edit/", views.meter_reading_edit, name="meter_reading_edit"),
    path("billing/meter-readings/<int:pk>/delete/", views.meter_reading_delete, name="meter_reading_delete"),
]

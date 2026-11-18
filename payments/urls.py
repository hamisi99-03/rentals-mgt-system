from django.urls import path

from payments import views

urlpatterns = [
    path("payments/", views.payments, name="payments"),
    path("payments/new/", views.payment_new, name="payment_new"),
    path("payments/preview/", views.allocation_preview, name="allocation_preview"),
    path("payments/<int:pk>/", views.payment_detail, name="payment_detail"),
    path("payments/<int:pk>/receipt/", views.payment_pdf, name="payment_pdf"),
    path("payments/<int:pk>/receipt/thermal/", views.payment_thermal, name="payment_thermal"),
    path("payments/<int:pk>/void/", views.payment_void, name="payment_void"),
    path("payments/<int:pk>/cheque/banked/", views.cheque_banked, name="cheque_banked"),
    path("payments/<int:pk>/cheque/bounced/", views.cheque_bounced, name="cheque_bounced"),
    path("payments/import/", views.statement_imports, name="statement_imports"),
    path("payments/import/<int:pk>/", views.statement_import_detail, name="statement_import_detail"),
    path("payments/import/rows/<int:pk>/confirm/", views.statement_row_confirm, name="statement_row_confirm"),
    path("payments/import/rows/<int:pk>/ignore/", views.statement_row_ignore, name="statement_row_ignore"),
]

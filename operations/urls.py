from django.urls import path

from operations import views

urlpatterns = [
    path("leases/<int:lease_pk>/deposits/", views.lease_deposits, name="lease_deposits"),
    path("move-outs/", views.move_outs, name="move_outs"),
    path("leases/<int:lease_pk>/move-out/", views.move_out_create, name="move_out_create"),
    path("move-outs/<int:pk>/", views.move_out_detail, name="move_out_detail"),
    path("move-outs/<int:pk>/settle/", views.move_out_settle, name="move_out_settle"),
    path("move-outs/<int:pk>/pdf/", views.move_out_pdf, name="move_out_pdf"),
    path("prospects/", views.prospects, name="prospects"),
    path("prospects/new/", views.prospect_create, name="prospect_create"),
    path("prospects/<int:pk>/edit/", views.prospect_edit, name="prospect_edit"),
    path("prospects/<int:pk>/convert/", views.prospect_convert, name="prospect_convert"),
    path("maintenance/", views.maintenance, name="maintenance"),
    path("maintenance/new/", views.maintenance_create, name="maintenance_create"),
    path("maintenance/<int:pk>/", views.maintenance_detail, name="maintenance_detail"),
    path("maintenance/<int:pk>/edit/", views.maintenance_edit, name="maintenance_edit"),
    path("expenses/", views.expenses, name="expenses"),
    path("expenses/new/", views.expense_create, name="expense_create"),
    path("expenses/categories/", views.expense_categories, name="expense_categories"),
    path("expenses/categories/<int:pk>/edit/", views.expense_category_edit, name="expense_category_edit"),
    path("expenses/categories/<int:pk>/toggle/", views.expense_category_toggle, name="expense_category_toggle"),
    path("expenses/<int:pk>/", views.expense_detail, name="expense_detail"),
    path("expenses/<int:pk>/edit/", views.expense_edit, name="expense_edit"),
    path("expenses/<int:pk>/receipts/upload/", views.expense_receipt_upload, name="expense_receipt_upload"),
    path("expenses/receipts/<int:pk>/delete/", views.expense_receipt_delete, name="expense_receipt_delete"),
]

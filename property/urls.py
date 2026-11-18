from django.urls import path

from property import views

urlpatterns = [
    path("units/", views.unit_list, name="units"),
    path("units/new/", views.unit_create, name="unit_create"),
    path("units/<int:pk>/", views.unit_detail, name="unit_detail"),
    path("units/<int:pk>/edit/", views.unit_edit, name="unit_edit"),
    path("units/<int:pk>/archive/", views.unit_toggle_active, name="unit_toggle_active"),
    path("buildings/", views.building_list, name="buildings"),
    path("buildings/<int:pk>/", views.building_detail, name="building_detail"),
    path("buildings/<int:pk>/edit/", views.building_edit, name="building_edit"),
    path("buildings/<int:pk>/delete/", views.building_delete, name="building_delete"),
    path("floors/<int:pk>/edit/", views.floor_edit, name="floor_edit"),
    path("floors/<int:pk>/delete/", views.floor_delete, name="floor_delete"),
    path("tenants/", views.tenant_list, name="tenants"),
    path("tenants/new/", views.tenant_create, name="tenant_create"),
    path("tenants/<int:pk>/", views.tenant_detail, name="tenant_detail"),
    path("tenants/<int:pk>/edit/", views.tenant_edit, name="tenant_edit"),
    path("tenants/<int:pk>/status/", views.tenant_toggle_status, name="tenant_toggle_status"),
    path("tenants/<int:pk>/contacts/add/", views.contact_create, name="contact_create"),
    path("contacts/<int:pk>/edit/", views.contact_edit, name="contact_edit"),
    path("contacts/<int:pk>/delete/", views.contact_delete, name="contact_delete"),
    path("documents/upload/", views.document_upload, name="document_upload"),
    path("documents/<int:pk>/delete/", views.document_delete, name="document_delete"),
    path("leases/", views.lease_list, name="leases"),
    path("leases/new/", views.lease_create, name="lease_create"),
    path("leases/<int:pk>/", views.lease_detail, name="lease_detail"),
    path("leases/<int:pk>/edit/", views.lease_edit, name="lease_edit"),
    path("leases/<int:pk>/terminate/", views.lease_terminate, name="lease_terminate"),
    path("import/", views.import_data, name="import_data"),
    path("import/template/", views.import_template, name="import_template"),
]

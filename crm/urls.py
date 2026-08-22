from django.urls import path

from crm import views


urlpatterns = [
    path("customers/", views.CustomerListView.as_view(), name="staff_customers"),
    path("customers/new/", views.CustomerCreateView.as_view(), name="staff_customer_create"),
    path("customers/<int:pk>/", views.CustomerDetailView.as_view(), name="staff_customer_detail"),
    path("customers/<int:pk>/edit/", views.CustomerUpdateView.as_view(), name="staff_customer_edit"),
]

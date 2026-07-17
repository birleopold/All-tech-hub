from django.urls import path

from loyalty import views

urlpatterns = [
    path(
        "unsubscribe/<uuid:token>/",
        views.unsubscribe_all,
        name="marketing_unsubscribe_all",
    ),
]

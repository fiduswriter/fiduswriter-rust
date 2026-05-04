from django.urls import path

from . import views

app_name = "rust"

urlpatterns = [
    path("check_access/", views.check_access, name="check_access"),
    path("init_session/", views.init_session, name="init_session"),
    path("save_doc/", views.save_doc, name="save_doc"),
    path("update_images/", views.update_images, name="update_images"),
]

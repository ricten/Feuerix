from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("passwort/", auth_views.PasswordChangeView.as_view(success_url="/"), name="password_change"),
    path("", include("apps.core.urls")),
    path("", include("apps.members.urls")),
    path("", include("apps.honors.urls")),
    path("", include("apps.finance.urls")),
    path("", include("apps.inventory.urls")),
    path("", include("apps.donations.urls")),
    path("", include("apps.allowances.urls")),
    path("", include("apps.events.urls")),
    path("", include("apps.documents.urls")),
    path("", include("apps.openslides.urls")),
    path("", include("apps.accounting.urls")),
]

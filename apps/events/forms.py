from django.contrib.auth import get_user_model

from apps.core.forms import TenantModelForm

from .models import Aufgabe


class AufgabeForm(TenantModelForm):
    class Meta:
        model = Aufgabe
        exclude = ("verein", "benachrichtigt_am", "beobachter")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.verein is not None:
            User = get_user_model()
            self.fields["zustaendig_benutzer"].queryset = (
                User.objects.filter(zugaenge__verein=self.verein, zugaenge__aktiv=True).distinct()
                .order_by("first_name", "last_name", "username"))

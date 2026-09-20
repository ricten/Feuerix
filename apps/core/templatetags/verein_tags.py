from django import template

register = template.Library()


@register.filter
def darf(rechte, schluessel):
    modul, aktion = schluessel.split(".")
    return rechte.darf(modul, aktion)

from django.contrib.auth.models import AbstractUser
from django.db import models

from nepal.validators import validate_nepali_phone
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    full_name_np = models.CharField(_("Full name"), max_length=150, blank=True)
    phone = models.CharField(max_length=20, blank=True, validators=[validate_nepali_phone])
    active_organization = models.ForeignKey(
        "orgs.Organization",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    def __str__(self):
        return self.full_name_np or self.get_full_name() or self.username

    @property
    def display_name(self):
        return self.full_name_np or self.get_full_name() or self.username

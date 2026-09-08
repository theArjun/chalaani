"""Tenancy. Every row a user can see hangs off exactly one Organization."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils.text import slugify

from nepal.validators import validate_nepali_phone, validate_pan
from django.utils.translation import gettext_lazy as _


class Organization(models.Model):
    name = models.CharField("Firm name", max_length=200)
    name_np = models.CharField(_("Firm name (Nepali)"), max_length=200, blank=True)
    slug = models.SlugField(max_length=60, unique=True)
    pan_no = models.CharField(
        "PAN/VAT", max_length=20, blank=True, validators=[validate_pan]
    )
    phone = models.CharField(
        max_length=20, blank=True, validators=[validate_nepali_phone]
    )
    address = models.CharField(_("Address"), max_length=200, blank=True)
    district = models.CharField(_("District"), max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name_np or self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name) or "firm"
            slug, n = base, 1
            while Organization.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                n += 1
                slug = f"{base}-{n}"
            self.slug = slug
        super().save(*args, **kwargs)


class Membership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", _("Owner")
        MANAGER = "manager", _("Manager")
        STAFF = "staff", _("Staff")

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="memberships"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships"
    )
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.STAFF)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user"], name="unique_org_membership"
            )
        ]
        ordering = ["organization__name"]

    def __str__(self):
        return f"{self.user} @ {self.organization} ({self.role})"

    @property
    def can_verify(self) -> bool:
        return self.role in {self.Role.OWNER, self.Role.MANAGER}


class OrgScopedQuerySet(models.QuerySet):
    def for_org(self, organization):
        if organization is None:
            return self.none()
        return self.filter(organization=organization)


class OrgScoped(models.Model):
    """Abstract base for every tenant-owned table."""

    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name="%(class)ss"
    )

    objects = OrgScopedQuerySet.as_manager()

    class Meta:
        abstract = True

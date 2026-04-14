import uuid
from django.db import models
from django.contrib.auth.models import User as Authuser
from django.utils import timezone


class Owner(models.Model):
    """Platform-level user - shop owners who create tenants (lives in public schema)."""
    user = models.OneToOneField(Authuser, on_delete=models.DO_NOTHING)

    def __str__(self):
        return self.user.email

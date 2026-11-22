from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower
import uuid
from datetime import timedelta
from django.utils import timezone


class User(AbstractUser):
    email = models.EmailField(unique=True)
    username = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        validators=[
            RegexValidator(
                regex=r"^[A-Za-z0-9_]{3,20}$",
                message="Use 3 to 20 letters, numbers or underscores.",
            )
        ],
    )
    google_id = models.CharField(max_length=255, unique=True, null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(Lower("username"), name="unique_username_ci"),
        ]

    def __str__(self):
        return self.username or self.email
    
def guest_expiry():
    return timezone.now() + timedelta(hours=24)


class GuestSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=guest_expiry)

    def is_expired(self):
        return timezone.now() >= self.expires_at

    def __str__(self):
        return f"Guest {self.id}"    
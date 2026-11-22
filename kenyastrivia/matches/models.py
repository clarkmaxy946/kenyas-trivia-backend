import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class MatchStatus(models.TextChoices):
    SETTING_UP = "setting_up", "Setting up"
    WAITING_FOR_CARDS = "waiting_for_cards", "Waiting for cards"
    IN_PROGRESS = "in_progress", "In progress"
    FINISHED = "finished", "Finished"
    SETUP_FAILED = "setup_failed", "Setup failed"
    ABANDONED = "abandoned", "Abandoned"


class TurnStatus(models.TextChoices):
    IN_PROGRESS = "in_progress", "In progress"
    SUBMITTED = "submitted", "Submitted"
    ABANDONED = "abandoned", "Abandoned"


ROUND_1, ROUND_2, TIEBREAKER = 1, 2, 3
ROUND_CHOICES = [(ROUND_1, "Round 1"), (ROUND_2, "Round 2"), (TIEBREAKER, "Tiebreaker")]


class Match(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.CASCADE, related_name="matches",
    )
    guest = models.ForeignKey(
        "users.GuestSession", null=True, blank=True,
        on_delete=models.CASCADE, related_name="matches",
    )
    status = models.CharField(
        max_length=20, choices=MatchStatus.choices, default=MatchStatus.SETTING_UP,
    )
    winner = models.ForeignKey(
        "Team", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
    )
    is_draw = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "matches"
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(user__isnull=False, guest__isnull=True)
                    | Q(user__isnull=True, guest__isnull=False)
                ),
                name="match_has_exactly_one_owner",
            ),
        ]

    def __str__(self):
        return f"Match {self.id} ({self.status})"


class Team(models.Model):
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="teams")
    # 1 = entered its name first, so it plays first in every round.
    position = models.PositiveSmallIntegerField()
    # The phone limits names to 8 characters; the database stays roomy on purpose.
    name = models.CharField(max_length=50)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(fields=["match", "position"], name="one_team_per_position"),
            models.CheckConstraint(condition=Q(position__in=[1, 2]), name="team_position_1_or_2"),
        ]

    def __str__(self):
        return self.name


class Turn(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="turns")
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="turns")
    round_number = models.PositiveSmallIntegerField(choices=ROUND_CHOICES)
    status = models.CharField(
        max_length=20, choices=TurnStatus.choices, default=TurnStatus.IN_PROGRESS,
    )
    started_at = models.DateTimeField()
    submitted_at = models.DateTimeField(null=True, blank=True)
    # One entry per card position: {"done": bool, "alias_used": bool}
    results = models.JSONField(default=list, blank=True)
    word_points = models.PositiveSmallIntegerField(default=0)
    bonus_points = models.PositiveSmallIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["match", "team", "round_number"], name="one_turn_per_team_per_round",
            ),
        ]

    @property
    def points(self):
        return self.word_points + self.bonus_points

    def __str__(self):
        return f"{self.team} round {self.round_number} ({self.status})"
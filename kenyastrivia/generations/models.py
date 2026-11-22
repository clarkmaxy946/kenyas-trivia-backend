from django.db import models


class JobStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"


class LogOutcome(models.TextChoices):
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"
    MODEL_ERROR = "model_error", "Model error"


class GenerationJob(models.Model):
    """One job produces the two cards (one per team) for one round of one match."""

    match_id = models.UUIDField(db_index=True)
    round_number = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=20, choices=JobStatus.choices, default=JobStatus.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["match_id", "round_number"], name="one_job_per_round"),
        ]

    def __str__(self):
        return f"Job {self.match_id} round {self.round_number} ({self.status})"


class GenerationLog(models.Model):
    """One row for every attempt at one card, so failures can be reviewed later."""

    job = models.ForeignKey(GenerationJob, on_delete=models.CASCADE, related_name="logs")
    position = models.PositiveSmallIntegerField()
    attempt = models.PositiveSmallIntegerField()
    outcome = models.CharField(max_length=20, choices=LogOutcome.choices)
    problems = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.job} card {self.position} attempt {self.attempt}: {self.outcome}"
from typing import Any

from django.conf import settings
from django.db import models
from django.utils import timezone


class CVAnalysis(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente"
        PROCESSING = "PROCESSING", "En cours"
        COMPLETED = "COMPLETED", "Terminee"
        FAILED = "FAILED", "Echouee"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cv_analyses",
    )
    cv_text = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    result = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["user", "-created_at"]),
        ]
        verbose_name = "analyse de CV"
        verbose_name_plural = "analyses de CV"

    def __str__(self) -> str:
        return f"Analyse CV #{self.pk} - {self.user} - {self.status}"

    def mark_processing(self) -> None:
        self.status = self.Status.PROCESSING
        self.error_message = ""
        self.save(update_fields=["status", "error_message", "updated_at"])

    def mark_completed(self, result: dict[str, Any]) -> None:
        self.status = self.Status.COMPLETED
        self.result = result
        self.error_message = ""
        self.completed_at = timezone.now()
        self.save(
            update_fields=[
                "status",
                "result",
                "error_message",
                "completed_at",
                "updated_at",
            ]
        )

    def mark_failed(self, message: str) -> None:
        self.status = self.Status.FAILED
        self.error_message = message
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "error_message", "completed_at", "updated_at"])

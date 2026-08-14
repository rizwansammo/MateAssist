"""Conversations and messages.

A conversation is tenant-owned and RLS-protected like everything else. The
transcript is the product's memory of a support interaction, and under A-008 it
is also what gets emailed to the customer's helpdesk on escalation - so what is
stored here leaves the system, and only what is needed is stored.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from apps.tenancy.managers import TenantScopedModel


class Conversation(TenantScopedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="conversations",
    )
    title = models.CharField(max_length=200, blank=True)
    resolved = models.BooleanField(
        default=False,
        help_text="Closed without escalation - the figure the AI-success metric counts.",
    )
    escalated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at",)
        indexes = [models.Index(fields=["tenant", "-updated_at"])]

    def __str__(self) -> str:
        return self.title or f"Conversation {self.pk}"


class Role(models.TextChoices):
    USER = "user", "User"
    ASSISTANT = "assistant", "Assistant"
    SYSTEM = "system", "System"


class Message(TenantScopedModel):
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    text = models.TextField(blank=True)

    # Citations are stored as resolved references, not raw chunk ids, so a
    # transcript stays readable after a document is re-indexed and its chunk
    # ordinals change.
    citations = models.JSONField(default=list, blank=True)

    # An attached screenshot never lands here as bytes. Gemini's description
    # does, and that description is the only thing the text engine ever sees
    # (D-042). The image itself lives in object storage.
    attachment_key = models.CharField(max_length=512, blank=True)
    attachment_description = models.TextField(blank=True)

    # Set when the model proposed escalate_via_email. It renders a button; the
    # user's click sends the email (D-126).
    proposed_escalation = models.JSONField(null=True, blank=True)

    prompt_tokens = models.PositiveIntegerField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("conversation", "created_at", "id")
        indexes = [models.Index(fields=["conversation", "created_at"])]

    def __str__(self) -> str:
        return f"{self.role}: {self.text[:40]}"


class MessageFeedback(TenantScopedModel):
    """The 'Was this helpful?' panel, persisted (D-089 retained item)."""

    message = models.OneToOneField(Message, on_delete=models.CASCADE, related_name="feedback")
    helpful = models.BooleanField()
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{'helpful' if self.helpful else 'not helpful'} on {self.message_id}"

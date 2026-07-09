"""Direct messaging (المراسلات).

A Conversation is a 1:1 thread between exactly two users; Message is a single
line in it. Real-time delivery reuses the existing Channels/Redis stack (see
apps/chat/consumers.py); this module owns persistence and the who-can-message
policy.
"""
from django.conf import settings
from django.db import models


class Conversation(models.Model):
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name="conversations"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # Bumped on every new message so inboxes can order by recent activity
    # without an aggregate query.
    last_message_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-last_message_at"]

    def other_participant(self, user):
        return self.participants.exclude(pk=user.pk).first()

    @classmethod
    def between(cls, user_a, user_b):
        """Return the existing 1:1 conversation between two users, or None.

        Matches a conversation whose participant set is exactly {a, b}.
        """
        candidates = cls.objects.filter(participants=user_a).filter(
            participants=user_b
        )
        for conv in candidates:
            if conv.participants.count() == 2:
                return conv
        return None

    @classmethod
    def get_or_create_between(cls, user_a, user_b):
        existing = cls.between(user_a, user_b)
        if existing:
            return existing, False
        conv = cls.objects.create()
        conv.participants.add(user_a, user_b)
        return conv, True


class Message(models.Model):
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sent_messages"
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["conversation", "created_at"]),
        ]

    def __str__(self):
        return f"{self.sender_id}: {self.body[:40]}"

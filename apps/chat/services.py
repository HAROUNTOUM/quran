"""Message persistence + realtime fan-out.

One place creates messages so the HTTP send view and the WebSocket consumer
stay consistent: persist, bump the conversation, push to the per-conversation
group, and nudge the recipient's notification socket for the unread badge.
"""
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone

from .models import Conversation, Message


def conversation_group(conversation_id):
    return f"chat_{conversation_id}"


def create_message(conversation, sender, body):
    body = (body or "").strip()
    if not body:
        return None

    message = Message.objects.create(
        conversation=conversation, sender=sender, body=body
    )
    Conversation.objects.filter(pk=conversation.pk).update(
        last_message_at=timezone.now()
    )
    _broadcast(conversation, message)
    return message


def _broadcast(conversation, message):
    layer = get_channel_layer()
    if layer is None:
        return

    payload = {
        "type": "chat.message",
        "id": message.id,
        "conversation_id": conversation.id,
        "sender_id": str(message.sender_id),
        "sender_name": message.sender.full_name_ar,
        "body": message.body,
        "created_at": message.created_at.isoformat(),
    }
    async_to_sync(layer.group_send)(conversation_group(conversation.id), payload)

    # Ping each other participant's notification socket so the header/sidebar
    # unread badge updates even when they don't have the thread open.
    for participant in conversation.participants.exclude(pk=message.sender_id):
        async_to_sync(layer.group_send)(
            f"notifications_{participant.id}",
            {"type": "unread_count_update",
             "unread_count": unread_count(participant)},
        )


def unread_count(user):
    return (
        Message.objects.filter(conversation__participants=user, is_read=False)
        .exclude(sender=user)
        .count()
    )


def mark_read(conversation, user):
    """Mark all messages in a conversation not sent by `user` as read."""
    Message.objects.filter(conversation=conversation, is_read=False).exclude(
        sender=user
    ).update(is_read=True)

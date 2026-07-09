"""Inbox (المراسلات): thread list + chat pane, matching the Admin Dashboard design.

The WebSocket consumer handles live delivery; these views cover the initial
render, the HTTP send fallback (no-JS / socket down), and starting a thread.
"""
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Max, Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from .models import Conversation, Message
from .permissions import can_message, messageable_users
from .services import create_message, mark_read


def _my_conversations(user):
    return (
        Conversation.objects.filter(participants=user)
        .prefetch_related("participants", "messages")
        .order_by("-last_message_at")
    )


@login_required
def inbox(request, conversation_id=None):
    conversations = list(_my_conversations(request.user))

    active = None
    if conversation_id is not None:
        active = get_object_or_404(
            Conversation, pk=conversation_id, participants=request.user
        )
    elif conversations:
        active = conversations[0]

    threads = []
    for conv in conversations:
        other = conv.other_participant(request.user)
        last = conv.messages.last()
        unread = sum(
            1 for m in conv.messages.all()
            if not m.is_read and m.sender_id != request.user.id
        )
        threads.append({
            "conversation": conv,
            "other": other,
            "last": last,
            "unread": unread,
            "is_active": active is not None and conv.pk == active.pk,
        })

    active_messages = []
    active_other = None
    if active is not None:
        mark_read(active, request.user)
        active_messages = list(active.messages.select_related("sender"))
        active_other = active.other_participant(request.user)

    return render(request, "dashboard/chat/inbox.html", {
        "threads": threads,
        "active": active,
        "active_other": active_other,
        "active_messages": active_messages,
        "contacts": messageable_users(request.user).order_by("full_name_ar"),
    })


@login_required
@require_POST
def send(request, conversation_id):
    conversation = get_object_or_404(
        Conversation, pk=conversation_id, participants=request.user
    )
    other = conversation.other_participant(request.user)
    if not can_message(request.user, other):
        return HttpResponseForbidden("لا يمكنك مراسلة هذا المستخدم")
    create_message(conversation, request.user, request.POST.get("body", ""))
    return redirect("chat:conversation", conversation_id=conversation.pk)


@login_required
@require_POST
def start(request):
    """Open (or reuse) a conversation with another user, then show it."""
    recipient = get_object_or_404(User, pk=request.POST.get("user_id"))
    if not can_message(request.user, recipient):
        return HttpResponseForbidden("لا يمكنك مراسلة هذا المستخدم")
    conversation, _ = Conversation.get_or_create_between(request.user, recipient)
    return redirect("chat:conversation", conversation_id=conversation.pk)

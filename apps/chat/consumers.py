"""Realtime chat consumer for a single conversation.

Joins the per-conversation group after verifying the user is a participant,
persists inbound messages through the shared service, and relays the broadcast
back out. Reuses the AuthMiddlewareStack scope["user"] like the other consumers.
"""
import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from .models import Conversation
from .services import conversation_group, create_message


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close()
            return

        self.conversation_id = self.scope["url_route"]["kwargs"]["conversation_id"]
        self.conversation = await self._get_conversation(user, self.conversation_id)
        if self.conversation is None:
            await self.close()
            return

        self.group_name = conversation_group(self.conversation_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        group = getattr(self, "group_name", None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except (ValueError, TypeError):
            return
        body = data.get("body", "")
        if not body.strip():
            return
        await self._persist(body)

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event))

    # --- db helpers -----------------------------------------------------
    @database_sync_to_async
    def _get_conversation(self, user, conversation_id):
        return (
            Conversation.objects.filter(pk=conversation_id, participants=user)
            .first()
        )

    @database_sync_to_async
    def _persist(self, body):
        # create_message fans out over the channel layer, which delivers the
        # message back to this consumer's chat_message handler too.
        create_message(self.conversation, self.scope["user"], body)

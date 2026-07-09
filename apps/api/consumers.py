import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model

User = get_user_model()


class SessionProgressConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.session_id = self.scope["url_route"]["kwargs"]["session_id"]
        self.room_group_name = f"session_{self.session_id}_progress"

        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close()
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "user_connected",
                "user_id": str(user.id),
                "full_name": user.full_name_ar,
                "role": user.role,
            },
        )

    async def disconnect(self, close_code):
        user = self.scope.get("user")
        if user and user.is_authenticated:
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "user_disconnected",
                    "user_id": str(user.id),
                    "full_name": user.full_name_ar,
                    "role": user.role,
                },
            )
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        msg_type = data.get("type")

        if msg_type == "progress_update":
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "progress_update",
                    "student_id": data.get("student_id"),
                    "score": data.get("score"),
                    "surah": data.get("surah"),
                    "status": data.get("status"),
                    "timestamp": data.get("timestamp"),
                },
            )
        elif msg_type == "attendance_update":
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "attendance_update",
                    "student_id": data.get("student_id"),
                    "status": data.get("status"),
                },
            )

    async def progress_update(self, event):
        await self.send(text_data=json.dumps(event))

    async def attendance_update(self, event):
        await self.send(text_data=json.dumps(event))

    async def user_connected(self, event):
        await self.send(text_data=json.dumps(event))

    async def user_disconnected(self, event):
        await self.send(text_data=json.dumps(event))


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close()
            return

        self.user_id = str(user.id)
        self.room_group_name = f"notifications_{self.user_id}"

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        # connect() closes before setting room_group_name for anonymous users,
        # so a rejected connection must not crash on group_discard.
        group = getattr(self, "room_group_name", None)
        if group:
            await self.channel_layer.group_discard(group, self.channel_name)

    async def new_notification(self, event):
        await self.send(text_data=json.dumps({
            "type": "new_notification",
            "id": event.get("id"),
            "title": event.get("title"),
            "message": event.get("message"),
            "notification_type": event.get("notification_type"),
            "link": event.get("link", ""),
            "unread_count": event.get("unread_count", 0),
        }))

    async def unread_count_update(self, event):
        await self.send(text_data=json.dumps({
            "type": "unread_count_update",
            "unread_count": event.get("unread_count", 0),
        }))

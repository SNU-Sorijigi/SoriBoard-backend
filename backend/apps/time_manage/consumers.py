from channels.generic.websocket import AsyncWebsocketConsumer
import json


class TvDisplayConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.channel_layer.group_add("tv_display", self.channel_name)

        await self.accept()

    async def disconnect(self, close_code):
        pass

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json["message"]

        await self.channel_layer.group_send(
            "tv_display", {"type": "tv_display_message", "message": message}
        )

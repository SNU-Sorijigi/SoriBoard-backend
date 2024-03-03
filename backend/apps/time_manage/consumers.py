import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from ...settings.base import STREAM_SOCKET_GROUP_NAME
from .models import TimeMusic
from .serializers import TimeMusicSerializer


class TvDisplayConsumer(AsyncWebsocketConsumer):
    group_name = STREAM_SOCKET_GROUP_NAME

    async def connect(self):
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        _text_data_json = json.loads(text_data)
        _update_type = _text_data_json["update_type"]

        if _update_type == "music":
            _time_music_id = _text_data_json["time_music_id"]

            _tv_display_info = self.get_serialized_time_music(_time_music_id)

            await self.send(
                self.group_name,
                {
                    "type": "update_tv",
                    "update_type": "music",
                    "info": _tv_display_info,
                },
            )

        elif _update_type == "breaktime":
            _breaktime = _text_data_json["breaktime"]

            _tv_display_info = str(_breaktime)

            await self.send(
                self.group_name,
                {
                    "type": "update_tv",
                    "update_type": "breaktime",
                    "info": _tv_display_info,
                },
            )

    @sync_to_async
    def get_serialized_time_music(self, time_music_id):
        time_music = TimeMusic.objects.get(pk=time_music_id)
        serialized_time_music = TimeMusicSerializer(time_music).data
        return serialized_time_music

    async def update_tv(self, event):
        await self.send(text_data=json.dumps(event))

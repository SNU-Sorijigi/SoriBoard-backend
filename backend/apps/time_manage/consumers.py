import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async

from .models import TimeMusic
from .serializers import TimeMusicListSerializer


class TvDisplayConsumer(AsyncWebsocketConsumer):
    group_name = "tv_socket_group"

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

            _tv_display_info = await self.get_serialized_time_music(_time_music_id)

            await self.channel_layer.group_send(
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

            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "update_tv",
                    "update_type": "breaktime",
                    "info": _tv_display_info,
                },
            )

        elif _update_type == "size":
            _composer_font_size = _text_data_json["composerFontSize"]
            _title_font_size = _text_data_json["titleFontSize"]
            _orchestra_font_size = _text_data_json["orchestraFontSize"]
            _player_font_size = _text_data_json["playerFontSize"]
            _spacer_size1 = _text_data_json["spacerSize1"]
            _spacer_size2 = _text_data_json["spacerSize2"]
            _spacer_size3 = _text_data_json["spacerSize3"]
            _spacer_size4 = _text_data_json["spacerSize4"]

            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "update_tv",
                    "update_type": "font_size",
                    "info": {
                        "composerFontSize": _composer_font_size,
                        "titleFontSize": _title_font_size,
                        "orchestraFontSize": _orchestra_font_size,
                        "playerFontSize": _player_font_size,
                        "spacerSize1": _spacer_size1,
                        "spacerSize2": _spacer_size2,
                        "spacerSize3": _spacer_size3,
                        "spacerSize4": _spacer_size4,
                    },
                },
            )

    @sync_to_async
    def get_serialized_time_music(self, time_music_id):
        time_music = TimeMusic.objects.get(pk=time_music_id)
        serialized_time_music = TimeMusicListSerializer(time_music).data
        return serialized_time_music

    async def update_tv(self, event):
        await self.send(text_data=json.dumps(event))

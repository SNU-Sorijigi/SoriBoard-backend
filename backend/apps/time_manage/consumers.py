import json
from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async

from .models import TimeMusic
from .serializers import TimeMusicListSerializer, players_as_typed

# The TV applies every one of these, so a size update must carry them all.
SIZE_KEYS = (
    "composerFontSize",
    "titleFontSize",
    "orchestraFontSize",
    "playerFontSize",
    "infoNewsFontSize",
    "instagramFontSize",
    "spacerSize1",
    "spacerSize2",
    "spacerSize3",
    "spacerSize4",
    "spacerSize5",
)


class TvDisplayConsumer(AsyncWebsocketConsumer):
    group_name = "tv_socket_group"

    async def connect(self):
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        # A message the TV cannot use is dropped: raising here would close
        # the sender's socket, and later updates from it would be lost.
        try:
            _text_data_json = json.loads(text_data)
        except (TypeError, ValueError):  # a binary frame, or not JSON
            return
        if not isinstance(_text_data_json, dict):
            return
        _update_type = _text_data_json.get("update_type")

        if _update_type == "music":
            _time_music_id = _text_data_json.get("time_music_id")

            _tv_display_info = await self.get_serialized_time_music(_time_music_id)
            if _tv_display_info is None:
                return

            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "update_tv",
                    "update_type": "music",
                    "info": _tv_display_info,
                },
            )

        elif _update_type == "breaktime":
            if "breaktime" not in _text_data_json:
                return
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
            # The session page still sends the sizes from before the TV showed
            # news, without infoNewsFontSize, instagramFontSize and spacerSize5.
            if any(key not in _text_data_json for key in SIZE_KEYS):
                return

            await self.channel_layer.group_send(
                self.group_name,
                {
                    "type": "update_tv",
                    "update_type": "font_size",
                    "info": {key: _text_data_json[key] for key in SIZE_KEYS},
                },
            )

    @sync_to_async
    def get_serialized_time_music(self, time_music_id):
        try:
            # The names TimeMusicListSerializer shows come with the play: one
            # query, then one for its players (as typed), not one per name.
            time_music = (
                TimeMusic.objects.select_related(
                    "music__composer", "music_detail", "conductor", "orchestra"
                )
                .prefetch_related(players_as_typed())
                .get(pk=time_music_id)
            )
        except (TimeMusic.DoesNotExist, TypeError, ValueError, OverflowError):
            # No such play, or an id the database cannot look up.
            return None
        serialized_time_music = TimeMusicListSerializer(time_music).data
        return serialized_time_music

    async def update_tv(self, event):
        await self.send(text_data=json.dumps(event))

import datetime
import json

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from django.test import TestCase

from apps.time_manage.consumers import TvDisplayConsumer
from apps.time_manage.models import (
    Composer,
    Conductor,
    Music,
    MusicDetail,
    Orchestra,
    Player,
    TimeInfo,
    TimeMusic,
)

# What the display settings (tv.svelte) send: every size the TV applies.
DISPLAY_SIZES = {
    "update_type": "size",
    "composerFontSize": 3,
    "titleFontSize": 2,
    "orchestraFontSize": 1.25,
    "playerFontSize": 1.25,
    "infoNewsFontSize": 1,
    "instagramFontSize": 1,
    "spacerSize1": 2.25,
    "spacerSize2": 1.6875,
    "spacerSize3": 0.28125,
    "spacerSize4": 0.28125,
    "spacerSize5": 0.5,
}
# What the session page (musicinfo.svelte) sends after each "show on TV":
# the sizes from before the TV showed news.
SESSION_PAGE_SIZES = {
    key: value
    for key, value in DISPLAY_SIZES.items()
    if key not in ("infoNewsFontSize", "instagramFontSize", "spacerSize5")
}
BREAK = {"update_type": "breaktime", "breaktime": "~15:20"}
BREAK_SHOWN = {"type": "update_tv", "update_type": "breaktime", "info": "~15:20"}


class TvDisplayTests(TestCase):
    """ws/tv_display/: the session page and the display settings send updates,
    and every open socket, the TV among them, receives them."""

    def setUp(self):
        session = TimeInfo.objects.create(
            date=datetime.date(2026, 9, 7), time=2, arrival_time="11:20:00"
        )
        brahms = Composer.objects.create(name="요하네스 브람스")
        symphony = Music.objects.create(composer=brahms, title="교향곡 제4번 Op. 98")
        self.play = TimeMusic.objects.create(
            time=session,
            order=1,
            source="CD",
            cd_id="DG-4471",
            music=symphony,
            music_detail=MusicDetail.objects.create(music=symphony, semi_title="2악장"),
            conductor=Conductor.objects.create(name="카를로스 클라이버"),
            orchestra=Orchestra.objects.create(name="빈 필하모닉"),
        )
        self.play.players.add(
            Player.objects.create(instrument="바이올린", name="정경화")
        )
        deleted = TimeMusic.objects.create(time=session, order=2, source="LP")
        self.deleted_id = deleted.id
        deleted.delete()
        # The in-memory channel layer outlives a test: start the next one empty.
        self.addCleanup(async_to_sync(get_channel_layer().flush))

    async def connect(self):
        socket = WebsocketCommunicator(TvDisplayConsumer.as_asgi(), "/ws/tv_display/")
        connected, _ = await socket.connect()
        self.assertTrue(connected)
        return socket

    def show(self, play_id):
        return {"time_music_id": play_id, "update_type": "music"}

    async def test_a_play_shown_on_tv_reaches_every_open_socket(self):
        tv = await self.connect()
        session_page = await self.connect()
        await session_page.send_json_to(self.show(self.play.id))
        shown = {
            "type": "update_tv",
            "update_type": "music",
            "info": {
                "id": self.play.id,
                "order": 1,
                "is_requested": False,
                "source": "CD",
                "cd_id": "DG-4471",
                "music_title": "교향곡 제4번 Op. 98",
                "music_semi_title": "2악장",
                "composer_name": "요하네스 브람스",
                "conductor_name": "카를로스 클라이버",
                "orchestra_name": "빈 필하모닉",
                "player_names": ["바이올린: 정경화"],
            },
        }
        self.assertEqual(await tv.receive_json_from(), shown)
        self.assertEqual(await session_page.receive_json_from(), shown)
        await tv.disconnect()
        await session_page.disconnect()

    def test_a_play_is_read_for_the_tv_in_two_queries(self):
        # The play with its music, composer, semi-title, conductor and
        # orchestra, then its players: not one query for each of them.
        consumer = TvDisplayConsumer()

        @async_to_sync
        async def read(play_id):
            return await consumer.get_serialized_time_music(play_id)

        with self.assertNumQueries(2):
            info = read(self.play.id)
        self.assertEqual(info["composer_name"], "요하네스 브람스")
        self.assertEqual(info["player_names"], ["바이올린: 정경화"])

        # A play with only a source is still shown; DRF leaves out the names
        # it has no music, conductor or orchestra for.
        bare = TimeMusic.objects.create(time=self.play.time, order=3, source="LP")
        self.assertEqual(
            read(bare.id),
            {
                "id": bare.id,
                "order": 3,
                "is_requested": False,
                "source": "LP",
                "cd_id": None,
                "player_names": [],
            },
        )

        # Every player is shown, still in the one query for the players.
        cello = Player.objects.create(instrument="첼로", name="장한나")
        piano = Player.objects.create(instrument="피아노", name="조성진")
        self.play.players.add(piano, cello)
        with self.assertNumQueries(2):
            info = read(self.play.id)
        self.assertCountEqual(
            info["player_names"],
            ["바이올린: 정경화", "첼로: 장한나", "피아노: 조성진"],
        )

    async def test_break_time_and_display_sizes_reach_the_tv(self):
        tv = await self.connect()
        settings = await self.connect()
        await settings.send_json_to(BREAK)
        self.assertEqual(await tv.receive_json_from(), BREAK_SHOWN)

        await settings.send_json_to(DISPLAY_SIZES)
        sizes = {k: v for k, v in DISPLAY_SIZES.items() if k != "update_type"}
        self.assertEqual(
            await tv.receive_json_from(),
            {"type": "update_tv", "update_type": "font_size", "info": sizes},
        )
        # An update type the TV does not know is ignored.
        await settings.send_json_to({"update_type": "volume", "volume": 3})
        self.assertTrue(await tv.receive_nothing())
        await tv.disconnect()
        await settings.disconnect()

    async def test_show_on_tv_works_again_after_the_session_pages_size_update(self):
        tv = await self.connect()
        # Each play row on the session page opens its own socket.
        row = await self.connect()
        for _ in range(2):
            await row.send_json_to(self.show(self.play.id))
            await row.send_json_to(SESSION_PAGE_SIZES)
            self.assertEqual((await tv.receive_json_from())["info"]["id"], self.play.id)
            self.assertEqual((await row.receive_json_from())["update_type"], "music")
            # The TV applies every size it gets, so an incomplete update is dropped.
            self.assertTrue(await tv.receive_nothing())
        await tv.disconnect()
        await row.disconnect()

    async def test_a_message_the_tv_cannot_use_is_dropped_and_the_socket_stays_open(
        self,
    ):
        messages = {
            "no update type": {"breaktime": "~15:20"},
            "no play id": {"update_type": "music"},
            "a deleted play": self.show(self.deleted_id),
            "a malformed play id": self.show("abc"),
            "a play id past 2**63": self.show(2**64),
            "no break time": {"update_type": "breaktime"},
            "a size update without every size": SESSION_PAGE_SIZES,
        }
        frames = {
            **{name: {"text_data": json.dumps(m)} for name, m in messages.items()},
            "not JSON": {"text_data": "music"},
            "not a JSON object": {"text_data": '["music"]'},
            "a binary frame": {"bytes_data": b'{"update_type": "music"}'},
        }
        tv = await self.connect()
        for name, frame in frames.items():
            with self.subTest(name):
                sender = await self.connect()
                await sender.send_to(**frame)
                self.assertTrue(await tv.receive_nothing())
                # The sender's socket still works.
                await sender.send_json_to(BREAK)
                self.assertEqual(await tv.receive_json_from(), BREAK_SHOWN)
                self.assertEqual(await sender.receive_json_from(), BREAK_SHOWN)
                await sender.disconnect()
        await tv.disconnect()

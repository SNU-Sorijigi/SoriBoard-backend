import datetime
from unittest import mock

from django.db import DatabaseError
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.time_manage import serializers
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


class TimeMusicWriteTests(APITestCase):
    """POST timemusic/ adds a play to a session; PUT timemusic/<id>/ edits it."""

    def setUp(self):
        self.session = TimeInfo.objects.create(
            date=datetime.date(2026, 9, 7), time=1, arrival_time="09:30:00"
        )
        composer = Composer.objects.create(name="루트비히 판 베토벤")
        music = Music.objects.create(composer=composer, title="교향곡 제7번 Op. 92")
        self.play = TimeMusic.objects.create(
            time=self.session, music=music, order=1, source="ROON"
        )
        self.play.players.add(Player.objects.create(instrument="피아노", name="조성진"))

    def add(self, **fields):
        body = {
            "time": self.session.id,
            "order": 2,
            "source": "CD",
            "title": "피아노 소나타 제23번 Op. 57",
            "composer_name": "루트비히 판 베토벤",
            "player_names": [],
            **fields,
        }
        return self.client.post(reverse("timemusic-list"), body, format="json")

    def edit(self, **fields):
        """PUT what the edit form (musicinfo.svelte) sends; None leaves a field out."""
        body = {
            "is_requested": False,
            "source": "CD",
            "cd_id": "",
            "title": "교향곡 제5번 Op. 67",
            "semi_title": "",
            "composer_name": "루트비히 판 베토벤",
            "conductor_name": "",
            "orchestra_name": "",
            "player_names": ["바이올린: 정경화"],
            **fields,
        }
        body = {name: value for name, value in body.items() if value is not None}
        return self.client.put(
            reverse("timemusic-detail", args=[self.play.id]), body, format="json"
        )

    def players(self, play):
        return sorted(f"{p.instrument}: {p.name}" for p in play.players.all())

    def snapshot(self):
        play = TimeMusic.objects.get(pk=self.play.pk)
        return play.music.title, play.source, play.order, self.players(play)

    def counts(self):
        models = (TimeMusic, Music, Composer, Conductor, Player)
        return [m.objects.count() for m in models]

    def test_add_trims_player_rows_and_skips_blank_ones(self):
        response = self.add(
            player_names=[" 첼로: 요요 마 ", "", "   ", "피아노: 조성진"]
        )
        self.assertEqual(response.status_code, 201)
        play = TimeMusic.objects.get(pk=response.json()["id"])
        self.assertEqual(play.music.title, "피아노 소나타 제23번 Op. 57")
        self.assertEqual(self.players(play), ["첼로: 요요 마", "피아노: 조성진"])
        self.assertEqual(Player.objects.count(), 2)

    def test_edit_replaces_the_play_and_its_players(self):
        response = self.edit(
            semi_title="운명",
            conductor_name="지휘: 카를로스 클라이버",
            orchestra_name="빈 필하모닉",
            player_names=["바이올린: 정경화", "첼로: 정명화"],
        )
        self.assertEqual(response.status_code, 200)
        play = TimeMusic.objects.get(pk=self.play.pk)
        self.assertEqual(
            self.snapshot(),
            ("교향곡 제5번 Op. 67", "CD", 1, ["바이올린: 정경화", "첼로: 정명화"]),
        )
        self.assertEqual(play.music_detail.semi_title, "운명")
        self.assertEqual(play.conductor.name, "카를로스 클라이버")
        self.assertEqual(play.orchestra.name, "빈 필하모닉")
        self.assertEqual(play.time, self.session)

    def test_edit_without_players_clears_them(self):
        for player_names in [[], None]:
            with self.subTest(player_names=player_names):
                self.play.players.add(Player.objects.get(name="조성진"))
                response = self.edit(player_names=player_names)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.snapshot()[3], [])

    def test_edit_without_title_or_composer_is_400_and_changes_nothing(self):
        before = self.snapshot(), self.counts()
        for missing in ["title", "composer_name"]:
            with self.subTest(missing=missing):
                response = self.edit(**{missing: None})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(list(response.json()), [missing])

        response = self.client.put(
            reverse("timemusic-detail", args=[self.play.id]),
            {"order": 3},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(sorted(response.json()), ["composer_name", "title"])
        self.assertEqual((self.snapshot(), self.counts()), before)

    def test_edit_skips_blank_player_rows(self):
        # The edit form's "+" adds a blank row and sends it as is.
        for player_names, expected in [
            (["", "바이올린: 정경화"], ["바이올린: 정경화"]),
            (["바이올린: 정경화", ""], ["바이올린: 정경화"]),
            (["   ", "피아노: 조성진"], ["피아노: 조성진"]),
            ([""], []),
        ]:
            with self.subTest(player_names=player_names):
                response = self.edit(player_names=player_names)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.snapshot()[3], expected)

    def test_malformed_player_rows_are_400_and_save_nothing(self):
        before = self.snapshot(), self.counts()
        for row in ["피아노:조성진", "조성진", "피아노: 조성진: 협연"]:
            player_names = ["첼로: 요요 마", row]
            for request in [self.add, self.edit]:
                with self.subTest(row=row, request=request.__name__):
                    response = request(player_names=player_names)
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(
                        response.json(),
                        {"player_names": [f'"{row}" is not "instrument: name".']},
                    )
                    self.assertEqual((self.snapshot(), self.counts()), before)

    def test_an_order_past_sqlites_integers_is_400_and_saves_nothing(self):
        # Past SQLite's 64-bit INTEGER the save raised OverflowError (500).
        before = self.snapshot(), self.counts()
        for order in [2**63, -(2**63) - 1, 10**30]:
            for request in [self.add, self.edit]:
                with self.subTest(order=order, request=request.__name__):
                    response = request(order=order)
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(list(response.json()), ["order"])
                    self.assertEqual((self.snapshot(), self.counts()), before)

    def test_the_largest_orders_are_saved(self):
        for order in [2**63 - 1, -(2**63)]:
            with self.subTest(order=order):
                response = self.add(order=order)
                self.assertEqual(response.status_code, 201)
                play = TimeMusic.objects.get(pk=response.json()["id"])
                self.assertEqual(play.order, order)
                response = self.edit(order=order)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.snapshot()[2], order)

    def test_add_takes_the_conductor_name_as_it_is(self):
        response = self.add(conductor_name="카를로스 클라이버")
        self.assertEqual(response.status_code, 201)
        play = TimeMusic.objects.get(pk=response.json()["id"])
        self.assertEqual(play.conductor.name, "카를로스 클라이버")

    def test_edit_conductor_without_a_role_is_400_and_saves_nothing(self):
        # The edit form shows "지휘: " + the name, or nothing when there is no
        # conductor; a name typed into the empty field has no "지휘: ".
        before = self.snapshot(), self.counts()
        for conductor, shown in [
            ("카를로스 클라이버", "카를로스 클라이버"),
            ("지휘:카를로스 클라이버", "지휘:카를로스 클라이버"),
            ("지휘: 카를로스 클라이버: 빈", "지휘: 카를로스 클라이버: 빈"),
            ("지휘: ", "지휘:"),  # the name cleared; DRF trims the space
        ]:
            with self.subTest(conductor=conductor):
                # A new composer: it was saved before the edit failed.
                response = self.edit(
                    composer_name="새 작곡가", conductor_name=conductor
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json(),
                    {"conductor_name": [f'"{shown}" is not "role: name".']},
                )
                self.assertEqual((self.snapshot(), self.counts()), before)
                self.assertIsNone(TimeMusic.objects.get(pk=self.play.pk).conductor)

    def test_a_write_that_fails_halfway_saves_nothing(self):
        # The player's row fails after the play itself was written.
        first_or_create = serializers.first_or_create

        def failing_for_players(model, **fields):
            if model is Player:
                raise DatabaseError("player row failed")
            return first_or_create(model, **fields)

        before = self.snapshot(), self.counts()
        for request in [self.add, self.edit]:
            with self.subTest(request=request.__name__), mock.patch.object(
                serializers, "first_or_create", failing_for_players
            ):
                with self.assertRaises(DatabaseError):
                    request(
                        composer_name="새 작곡가",
                        conductor_name="지휘: 카를로스 클라이버",
                        player_names=["첼로: 요요 마"],
                    )
                self.assertEqual((self.snapshot(), self.counts()), before)

    def test_a_name_on_two_rows_is_read_as_the_oldest(self):
        # Names are not unique: the admin can add a second composer, music,
        # conductor, orchestra or player of the same name. get_or_create then
        # raised MultipleObjectsReturned (500) for every play naming it.
        composer = self.play.music.composer
        Composer.objects.create(name=composer.name)
        music = Music.objects.create(composer=composer, title="교향곡 제5번 Op. 67")
        Music.objects.create(composer=composer, title=music.title)
        detail = MusicDetail.objects.create(music=music, semi_title="운명")
        MusicDetail.objects.create(music=music, semi_title="운명")
        rows = {}
        for model, fields in [
            (Conductor, {"name": "카를로스 클라이버"}),
            (Orchestra, {"name": "빈 필하모닉"}),
            (Player, {"instrument": "첼로", "name": "요요 마"}),
        ]:
            rows[model] = model.objects.create(**fields)
            model.objects.create(**fields)
        models = (Composer, Music, MusicDetail, Conductor, Orchestra, Player)
        before = [m.objects.count() for m in models]

        body = {
            "title": music.title,
            "semi_title": "운명",
            "orchestra_name": "빈 필하모닉",
            "player_names": ["첼로: 요요 마"],
        }
        for request, conductor, status in [
            (self.add, "카를로스 클라이버", 201),
            (self.edit, "지휘: 카를로스 클라이버", 200),
        ]:
            with self.subTest(request=request.__name__):
                response = request(conductor_name=conductor, **body)
                self.assertEqual(response.status_code, status)
                play = TimeMusic.objects.get(pk=response.json()["id"])
                self.assertEqual(
                    (play.music, play.music.composer, play.music_detail),
                    (music, composer, detail),
                )
                self.assertEqual(play.conductor, rows[Conductor])
                self.assertEqual(play.orchestra, rows[Orchestra])
                self.assertEqual(list(play.players.all()), [rows[Player]])
                self.assertEqual([m.objects.count() for m in models], before)

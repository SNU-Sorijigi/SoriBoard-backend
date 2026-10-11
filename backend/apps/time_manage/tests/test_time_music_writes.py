import datetime

from django.urls import reverse
from rest_framework.test import APITestCase

from apps.time_manage.models import Composer, Music, Player, TimeInfo, TimeMusic


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
        return [m.objects.count() for m in (TimeMusic, Music, Composer, Player)]

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

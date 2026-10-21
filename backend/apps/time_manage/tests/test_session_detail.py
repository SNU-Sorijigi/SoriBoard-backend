import datetime

from django.urls import reverse
from rest_framework.test import APITestCase

from apps.time_manage.models import (
    Composer,
    Conductor,
    Music,
    MusicDetail,
    Orchestra,
    Player,
    TimeInfo,
    TimeMusic,
    User,
)


class SessionDetailTests(APITestCase):
    """GET timeinfo/<id>/ is what the session page shows: the session and its plays."""

    def setUp(self):
        self.jigi = User.objects.create(
            name="김지기", major="음악학과", year_id="22", join_year=2022
        )
        self.senior = User.objects.create(
            name="이선배", major="물리학과", year_id="21", join_year=2021
        )
        self.mentee = User.objects.create(
            name="박견습", major="경제학부", year_id="25", join_year=2025
        )
        self.session = TimeInfo.objects.create(
            date=datetime.date(2026, 9, 7), time=2, arrival_time="11:20:00"
        )
        self.session.users.set([self.senior, self.jigi])
        self.session.mentees.set([self.mentee])

        beethoven = Composer.objects.create(name="루트비히 판 베토벤")
        brahms = Composer.objects.create(name="요하네스 브람스")
        symphony = Music.objects.create(composer=beethoven, title="교향곡 제7번 Op. 92")
        # Created out of order: the playlist is sorted by `order`.
        self.concerto = TimeMusic.objects.create(
            time=self.session,
            order=3,
            source="CD",
            cd_id="DG-4471",
            music=Music.objects.create(composer=brahms, title="이중 협주곡 Op. 102"),
            conductor=Conductor.objects.create(name="클라우디오 아바도"),
            orchestra=Orchestra.objects.create(name="베를린 필하모닉"),
        )
        self.concerto.players.add(
            Player.objects.create(instrument="바이올린", name="정경화"),
            Player.objects.create(instrument="첼로", name="장한나"),
        )
        self.sonata = TimeMusic.objects.create(
            time=self.session,
            order=1,
            source="ROON",
            is_requested=True,
            music=Music.objects.create(
                composer=beethoven, title="피아노 소나타 제23번 Op. 57"
            ),
        )
        self.sonata.players.add(
            Player.objects.create(instrument="피아노", name="조성진")
        )
        self.movement = TimeMusic.objects.create(
            time=self.session,
            order=2,
            source="LP",
            music=symphony,
            music_detail=MusicDetail.objects.create(music=symphony, semi_title="2악장"),
            conductor=Conductor.objects.create(name="카를로스 클라이버"),
            orchestra=Orchestra.objects.create(name="빈 필하모닉"),
        )

    def get(self):
        return self.client.get(reverse("timeinfo-detail", args=[self.session.id]))

    def test_returns_the_session_with_its_plays_in_order(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "id": self.session.id,
                "time": 2,
                "date": "2026-09-07",
                "users": [self.jigi.id, self.senior.id],
                "arrival_time": "11:20:00",
                "mentees": [self.mentee.id],
                "mentee_arrival_time": None,
                "time_comment_music": "",
                "time_comment_gigi": "",
                "time_comment_etc": "",
                "user": self.jigi.id,
                "mentee": self.mentee.id,
                "jigi_info": ["김지기 음악학과 22", "이선배 물리학과 21"],
                "mentee_info": ["박견습 경제학부 25"],
                "time_music": [
                    {
                        "id": self.sonata.id,
                        "order": 1,
                        "is_requested": True,
                        "source": "ROON",
                        "cd_id": None,
                        "music_title": "피아노 소나타 제23번 Op. 57",
                        "composer_name": "루트비히 판 베토벤",
                        "player_names": ["피아노: 조성진"],
                    },
                    {
                        "id": self.movement.id,
                        "order": 2,
                        "is_requested": False,
                        "source": "LP",
                        "cd_id": None,
                        "music_title": "교향곡 제7번 Op. 92",
                        "music_semi_title": "2악장",
                        "composer_name": "루트비히 판 베토벤",
                        "conductor_name": "카를로스 클라이버",
                        "orchestra_name": "빈 필하모닉",
                        "player_names": [],
                    },
                    {
                        "id": self.concerto.id,
                        "order": 3,
                        "is_requested": False,
                        "source": "CD",
                        "cd_id": "DG-4471",
                        "music_title": "이중 협주곡 Op. 102",
                        "composer_name": "요하네스 브람스",
                        "conductor_name": "클라우디오 아바도",
                        "orchestra_name": "베를린 필하모닉",
                        "player_names": ["바이올린: 정경화", "첼로: 장한나"],
                    },
                ],
            },
        )

    def test_a_session_without_people_or_plays(self):
        empty = TimeInfo.objects.create(
            date=datetime.date(2026, 9, 7), time=3, arrival_time="13:10:00"
        )
        response = self.client.get(reverse("timeinfo-detail", args=[empty.id]))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            [body[key] for key in ["users", "mentees", "user", "mentee"]],
            [[], [], None, None],
        )
        self.assertEqual([body["jigi_info"], body["mentee_info"]], [[], []])
        self.assertEqual(body["time_music"], [])

    def test_reads_the_session_in_five_queries_however_many_plays(self):
        # The session, its 지기, its 견습, the plays with what they name, players.
        with self.assertNumQueries(5):
            self.assertEqual(self.get().status_code, 200)

        conductor = Conductor.objects.create(name="정명훈")
        for order in range(4, 24):
            play = TimeMusic.objects.create(
                time=self.session,
                order=order,
                source="CD",
                music=self.movement.music,
                music_detail=self.movement.music_detail,
                conductor=conductor,
                orchestra=self.movement.orchestra,
            )
            play.players.add(*Player.objects.all())
        with self.assertNumQueries(5):
            response = self.get()
        self.assertEqual(len(response.json()["time_music"]), 23)

    def test_lists_a_plays_players_in_the_order_they_were_typed(self):
        # 장한나 and 조성진 are saved already, with lower ids than 김봄소리:
        # listed by id, they came first whatever was typed.
        typed = ["바이올린: 김봄소리", "첼로: 장한나"]
        response = self.client.post(
            reverse("timemusic-list"),
            {
                "time": self.session.id,
                "order": 4,
                "source": "CD",
                "title": "이중 협주곡 Op. 102",
                "composer_name": "요하네스 브람스",
                "player_names": typed,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        play_id = response.json()["id"]
        self.assertEqual(self.get().json()["time_music"][3]["player_names"], typed)

        # An edit lists them as typed in the edit.
        typed = ["바이올린: 김봄소리", "피아노: 조성진", "첼로: 장한나"]
        response = self.client.put(
            reverse("timemusic-detail", args=[play_id]),
            {
                "title": "이중 협주곡 Op. 102",
                "composer_name": "요하네스 브람스",
                "player_names": typed,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.get().json()["time_music"][3]["player_names"], typed)

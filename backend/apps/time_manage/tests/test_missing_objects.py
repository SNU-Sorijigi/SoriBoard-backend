import datetime

from django.urls import reverse
from rest_framework.test import APITestCase

from apps.time_manage.models import (
    Composer,
    Music,
    News,
    Semester,
    Timetable,
    TimetableUnit,
    TimeInfo,
    TimeMusic,
    User,
)

# Ids SQLite cannot store: the driver raised OverflowError (500) on them.
TOO_LARGE_IDS = [2**63, 2**64, -(2**63) - 1]


class MissingObjectTests(APITestCase):
    """Editing or deleting an id that is gone answers 404, not 500."""

    def setUp(self):
        self.semester = Semester.objects.create(
            year=2026, semester_num=2, start_time="09:30:00", end_time="17:40:00"
        )
        self.session = TimeInfo.objects.create(
            date=datetime.date(2026, 9, 7), time=1, arrival_time="09:30:00"
        )
        composer = Composer.objects.create(name="루트비히 판 베토벤")
        music = Music.objects.create(composer=composer, title="교향곡 제7번 Op. 92")
        self.play = TimeMusic.objects.create(
            time=self.session, music=music, order=1, source="ROON"
        )
        self.models = {
            "semester": Semester,
            "timeinfo": TimeInfo,
            "timemusic": TimeMusic,
        }

    def counts(self):
        return {name: model.objects.count() for name, model in self.models.items()}

    def test_put_and_delete_of_a_missing_or_malformed_id_are_404(self):
        before = self.counts()
        for name, model in self.models.items():
            missing = model.objects.order_by("-id").first().id + 1
            for pk in [missing, "abc"]:
                url = reverse(f"{name}-detail", args=[pk])
                for method in ["put", "delete"]:
                    with self.subTest(url=url, method=method):
                        response = getattr(self.client, method)(url, {}, format="json")
                        self.assertEqual(response.status_code, 404)
                        self.assertIn("detail", response.json())
        self.assertEqual(self.counts(), before)

    def test_get_of_a_malformed_id_is_404(self):
        for name in ["semester", "timeinfo"]:
            with self.subTest(name=name):
                response = self.client.get(reverse(f"{name}-detail", args=["abc"]))
                self.assertEqual(response.status_code, 404)

    def test_existing_session_and_play_still_update_and_delete(self):
        response = self.client.put(
            reverse("timeinfo-detail", args=[self.session.id]),
            {"time_comment_music": "앙코르 요청"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.session.refresh_from_db()
        self.assertEqual(self.session.time_comment_music, "앙코르 요청")

        response = self.client.put(
            reverse("timemusic-detail", args=[self.play.id]),
            {
                "title": "교향곡 제5번 Op. 67",
                "composer_name": "루트비히 판 베토벤",
                "player_names": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.play.refresh_from_db()
        self.assertEqual(self.play.music.title, "교향곡 제5번 Op. 67")

        response = self.client.delete(reverse("timemusic-detail", args=[self.play.id]))
        self.assertEqual(response.status_code, 204)
        response = self.client.delete(
            reverse("timeinfo-detail", args=[self.session.id])
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(TimeMusic.objects.exists())
        self.assertFalse(TimeInfo.objects.exists())


class TooLargeIdTests(APITestCase):
    """An id in the URL past SQLite's 64-bit INTEGER answers like a missing one."""

    def setUp(self):
        self.semester = Semester.objects.create(
            year=2026, semester_num=2, start_time="09:30:00", end_time="17:40:00"
        )
        self.session = TimeInfo.objects.create(
            date=datetime.date(2026, 9, 7), time=1, arrival_time="09:30:00"
        )
        self.composer = Composer.objects.create(name="루트비히 판 베토벤")
        self.music = Music.objects.create(
            composer=self.composer, title="교향곡 제7번 Op. 92"
        )
        self.play = TimeMusic.objects.create(
            time=self.session, music=self.music, order=1, source="ROON"
        )
        self.other_play = TimeMusic.objects.create(
            time=self.session, music=self.music, order=2, source="ROON"
        )
        User.objects.create(name="김지기")
        News.objects.create(content="정기 감상회 3/24 19:00")
        self.models = [
            Semester,
            Timetable,
            TimetableUnit,
            TimeInfo,
            TimeMusic,
            Composer,
            Music,
            User,
            News,
        ]

    def counts(self):
        return {model.__name__: model.objects.count() for model in self.models}

    def test_detail_routes_answer_404(self):
        routes = {
            "semester-detail": ["get", "put", "delete"],
            "timeinfo-detail": ["get", "put", "delete"],
            "timemusic-detail": ["put", "delete"],
            "user-detail": ["get", "put", "patch", "delete"],
            "timetable-detail": ["get", "put", "patch", "delete"],
            "timetableunit-detail": ["get", "put", "patch", "delete"],
            "information-detail": ["get", "put", "patch", "delete"],
            "composerlist-detail": ["get"],
            "musiclist-detail": ["get"],
        }
        before = self.counts()
        # 2**63 - 1 is the largest id SQLite stores: it was a plain 404 already.
        for pk in TOO_LARGE_IDS + [2**63 - 1]:
            for name, methods in routes.items():
                url = reverse(name, args=[pk])
                for method in methods:
                    with self.subTest(url=url, method=method):
                        response = getattr(self.client, method)(url, {}, format="json")
                        self.assertEqual(response.status_code, 404)
                        self.assertEqual(response.json(), {"detail": "Not found."})
        self.assertEqual(self.counts(), before)

    def test_musics_by_a_composer_past_the_range_are_none(self):
        for composer_id in [2**63, 2**64, 10**30]:
            with self.subTest(composer_id=composer_id):
                url = reverse("music-by-composer-list", args=[composer_id])
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), [])
                url = reverse(
                    "music-by-composer-detail", args=[composer_id, self.music.id]
                )
                self.assertEqual(self.client.get(url).status_code, 404)
        for music_id in TOO_LARGE_IDS:
            with self.subTest(music_id=music_id):
                url = reverse(
                    "music-by-composer-detail", args=[self.composer.id, music_id]
                )
                self.assertEqual(self.client.get(url).status_code, 404)
        # The largest storable composer id is still looked up.
        url = reverse("music-by-composer-list", args=[2**63 - 1])
        self.assertEqual(self.client.get(url).json(), [])

    def test_swapping_with_a_play_past_the_range_changes_nothing(self):
        # swaporder/ takes <int:> ids, which cannot be negative.
        for pk in [2**63, 2**64]:
            for pair in [(self.play.id, pk), (pk, self.other_play.id), (pk, pk)]:
                with self.subTest(pair=pair):
                    response = self.client.post(reverse("swaporder", args=pair))
                    self.assertEqual(response.status_code, 404)
                    self.assertIn("error", response.json())
        self.play.refresh_from_db()
        self.other_play.refresh_from_db()
        self.assertEqual((self.play.order, self.other_play.order), (1, 2))
        # The swap still works afterwards.
        response = self.client.post(
            reverse("swaporder", args=[self.play.id, self.other_play.id])
        )
        self.assertEqual(response.status_code, 200)
        self.play.refresh_from_db()
        self.assertEqual(self.play.order, 2)


class TooLargeBodyIdTests(APITestCase):
    """An id in the body past SQLite's 64-bit INTEGER is refused like a missing one."""

    def setUp(self):
        self.semester = Semester.objects.create(
            year=2026, semester_num=2, start_time="09:30:00", end_time="17:40:00"
        )
        self.timetable = self.semester.timetable
        # The semester comes with every cell: free one for the POSTs below.
        self.cell = self.timetable.units.get(day=0, time=1)
        self.timetable.units.filter(day=1).delete()
        self.session = TimeInfo.objects.create(
            date=datetime.date(2026, 9, 7), time=1, arrival_time="09:30:00"
        )
        self.play = TimeMusic.objects.create(time=self.session, order=1, source="ROON")
        self.user = User.objects.create(name="김지기", major="음악", year_id="24")
        self.models = [Timetable, TimetableUnit, TimeInfo, TimeMusic, User]

    def counts(self):
        return {model.__name__: model.objects.count() for model in self.models}

    def requests(self, pk):
        """(method, url, body, the field the error names) for each relation."""
        new_session = {"time": 2, "date": "2026-09-07", "arrival_time": "09:30"}
        play = {"source": "ROON", "title": "교향곡 제7번", "composer_name": "베토벤"}
        cell = {"timetable": self.timetable.id, "day": 1, "time": 1}
        user_url = reverse("user-detail", args=[self.user.id])
        session_url = reverse("timeinfo-detail", args=[self.session.id])
        play_url = reverse("timemusic-detail", args=[self.play.id])
        cell_url = reverse("timetableunit-detail", args=[self.cell.id])
        return [
            (
                "post",
                reverse("user-list"),
                {"name": "a", "major": "b", "year_id": "25", "sabu_id": pk},
                "sabu_id",
            ),  # fmt: skip
            ("patch", user_url, {"sabu_id": pk}, "sabu_id"),
            ("post", reverse("timeinfo-list"), {**new_session, "users": [pk]}, "users"),
            (
                "post",
                reverse("timeinfo-list"),
                {**new_session, "mentees": [pk]},
                "mentees",
            ),  # fmt: skip
            # The legacy single fields are read as one-item lists.
            ("post", reverse("timeinfo-list"), {**new_session, "user": pk}, "users"),
            ("put", session_url, {"users": [self.user.id, pk]}, "users"),
            ("put", session_url, {"mentee": pk}, "mentees"),
            (
                "post",
                reverse("timemusic-list"),
                {**play, "time": pk, "order": 2},
                "time",
            ),  # fmt: skip
            ("put", play_url, {**play, "time": pk}, "time"),
            (
                "post",
                reverse("timetableunit-list"),
                {**cell, "timetable": pk},
                "timetable",
            ),  # fmt: skip
            ("post", reverse("timetableunit-list"), {**cell, "users": [pk]}, "users"),
            ("patch", cell_url, {"mentees": [pk]}, "mentees"),
            ("post", reverse("timetable-list"), {"semester": pk}, "semester"),
        ]

    def test_writes_with_an_id_past_the_range_are_400(self):
        before = self.counts()
        # ±2**63 edges are storable: they were a 400 "does not exist" already.
        for pk in TOO_LARGE_IDS + [10**30, str(2**63), 2**63 - 1, -(2**63)]:
            for method, url, body, field in self.requests(pk):
                with self.subTest(method=method, url=url, body=body):
                    response = getattr(self.client, method)(url, body, format="json")
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(
                        response.json()[field],
                        [f'Invalid pk "{pk}" - object does not exist.'],
                    )
        self.assertEqual(self.counts(), before)
        self.user.refresh_from_db()
        self.assertIsNone(self.user.sabu_id)
        self.assertFalse(self.session.users.exists())
        self.assertFalse(self.cell.mentees.exists())
        self.play.refresh_from_db()
        self.assertEqual(self.play.time, self.session)

    def test_the_same_writes_with_a_real_id_still_save(self):
        other = User.objects.create(name="박지기", major="음악", year_id="23")
        before = self.counts()
        for method, url, body, field in self.requests(other.id):
            if field in ("time", "timetable", "semester"):
                continue  # these need a session, timetable or semester id
            with self.subTest(method=method, url=url, body=body):
                response = getattr(self.client, method)(url, body, format="json")
                self.assertIn(response.status_code, (200, 201), response.content)
            # Drop what a POST created, so the next one is not a duplicate.
            TimeInfo.objects.filter(time=2).delete()
            TimetableUnit.objects.filter(day=1).delete()
            User.objects.filter(name="a").delete()
        self.assertEqual(self.counts(), before)
        self.user.refresh_from_db()
        self.assertEqual(self.user.sabu_id, other)
        self.assertEqual(list(self.session.mentees.all()), [other])
        self.assertEqual(list(self.cell.mentees.all()), [other])


class TimeInfoLookupTests(APITestCase):
    """GET timeinfo/?date=YYYY-MM-DD&time=N returns the session id or null."""

    def setUp(self):
        self.session = TimeInfo.objects.create(
            date=datetime.date(2026, 9, 7), time=2, arrival_time="09:30:00"
        )

    def lookup(self, **params):
        return self.client.get(reverse("timeinfo-list"), params)

    def test_finds_the_session_or_returns_null(self):
        for date, time, expected in [
            ("2026-09-07", "2", self.session.id),
            ("2026-9-7", "2", self.session.id),
            ("2026-09-07", " 2", self.session.id),
            ("2026-09-07", "3", None),
            ("2026-09-08", "2", None),
        ]:
            with self.subTest(date=date, time=time):
                response = self.lookup(date=date, time=time)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"id": expected})

    def test_missing_or_blank_parameters_are_400_naming_them(self):
        required = ["This field is required."]
        for params, missing in [
            ({}, ["date", "time"]),
            ({"date": "2026-09-07"}, ["time"]),
            ({"time": "2"}, ["date"]),
            ({"date": "", "time": "2"}, ["date"]),
            ({"date": "2026-09-07", "time": ""}, ["time"]),
            ({"date": "", "time": ""}, ["date", "time"]),
        ]:
            with self.subTest(params=params):
                response = self.lookup(**params)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {name: required for name in missing})

    def test_malformed_parameters_are_400_naming_the_parameter(self):
        for date, time, field in [
            ("garbage", "2", "date"),
            ("2026-13-01", "2", "date"),
            ("2026-02-30", "2", "date"),
            ("2026-09-07", "abc", "time"),
            ("2026-09-07", "2.5", "time"),
            ("2026-09-07", str(2**63), "time"),
        ]:
            with self.subTest(date=date, time=time):
                response = self.lookup(date=date, time=time)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(list(response.json()), [field])

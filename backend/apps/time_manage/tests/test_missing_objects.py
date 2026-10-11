import datetime

from django.urls import reverse
from rest_framework.test import APITestCase

from apps.time_manage.models import Composer, Music, Semester, TimeInfo, TimeMusic


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

    def test_missing_or_blank_parameters_are_400(self):
        for params in [{}, {"date": "2026-09-07"}, {"time": "2"}, {"date": ""}]:
            with self.subTest(params=params):
                self.assertEqual(self.lookup(**params).status_code, 400)

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

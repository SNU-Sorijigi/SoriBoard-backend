import datetime

from django.urls import reverse
from rest_framework.test import APITestCase

from apps.time_manage.models import TimeInfo, User

OMIT = object()  # leave the field out of the request body


class TimeInfoWriteTests(APITestCase):
    """POST timeinfo/ creates a session (타임 생성); PUT timeinfo/<id>/ edits it."""

    def setUp(self):
        self.jigi = User.objects.create(name="김지기", major="음악학과", year_id="22")
        self.senior = User.objects.create(name="이선배", major="물리학과", year_id="21")
        self.mentee = User.objects.create(name="박견습", major="경제학부", year_id="25")
        self.session = TimeInfo.objects.create(
            date=datetime.date(2026, 9, 7),
            time=2,
            arrival_time="11:20:00",
            mentee_arrival_time="11:25:00",
            time_comment_music="앙코르 요청",
        )
        self.session.users.set([self.jigi])
        self.session.mentees.set([self.mentee])

    def send(self, method, url, body, fields):
        body = {**body, **fields}
        body = {name: value for name, value in body.items() if value is not OMIT}
        return getattr(self.client, method)(url, body, format="json")

    def create(self, **fields):
        """POST what 타임 생성 (time_manage/+page.svelte) sends."""
        body = {
            "date": "2026-09-08",
            "time": 1,
            "users": [self.jigi.id, self.senior.id],
            "mentees": [self.mentee.id],
            "arrival_time": "09:30",
            "mentee_arrival_time": "09:40",
        }
        return self.send("post", reverse("timeinfo-list"), body, fields)

    def edit(self, **fields):
        """PUT what 타임 정보 수정 (time_manage/[id]/+page.svelte) sends."""
        body = {
            "date": "2026-09-07",
            "time": 2,
            "users": [self.jigi.id],
            "mentees": [self.mentee.id],
            "arrival_time": "11:20:00",
            "mentee_arrival_time": "11:25:00",
        }
        url = reverse("timeinfo-detail", args=[self.session.id])
        return self.send("put", url, body, fields)

    def saved(self, pk):
        session = TimeInfo.objects.get(pk=pk)
        return {
            "date": session.date,
            "time": session.time,
            "users": sorted(user.id for user in session.users.all()),
            "mentees": sorted(user.id for user in session.mentees.all()),
            "arrival_time": session.arrival_time,
            "mentee_arrival_time": session.mentee_arrival_time,
            "time_comment_music": session.time_comment_music,
        }

    def test_create_saves_the_session_and_answers_its_id(self):
        response = self.create()
        self.assertEqual(response.status_code, 201)
        created = TimeInfo.objects.get(date=datetime.date(2026, 9, 8), time=1)
        self.assertEqual(response.json(), {"id": created.id})
        self.assertEqual(
            self.saved(created.id),
            {
                "date": datetime.date(2026, 9, 8),
                "time": 1,
                "users": [self.jigi.id, self.senior.id],
                "mentees": [self.mentee.id],
                "arrival_time": datetime.time(9, 30),
                "mentee_arrival_time": datetime.time(9, 40),
                "time_comment_music": "",
            },
        )

    def test_create_without_a_mentee_arrival_time(self):
        for time, value in enumerate([None, OMIT], start=1):
            with self.subTest(value=value):
                response = self.create(time=time, mentees=[], mentee_arrival_time=value)
                self.assertEqual(response.status_code, 201)
                saved = self.saved(response.json()["id"])
                self.assertEqual(saved["mentees"], [])
                self.assertIsNone(saved["mentee_arrival_time"])

    def test_create_accepts_the_legacy_single_user_and_mentee(self):
        response = self.create(
            users=OMIT, mentees=OMIT, user=self.senior.id, mentee=self.mentee.id
        )
        self.assertEqual(response.status_code, 201)
        saved = self.saved(response.json()["id"])
        self.assertEqual(saved["users"], [self.senior.id])
        self.assertEqual(saved["mentees"], [self.mentee.id])

    def test_edit_answers_the_saved_session(self):
        response = self.edit(
            users=[self.jigi.id, self.senior.id],
            mentees=[],
            arrival_time="11:15",
            mentee_arrival_time="11:30",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "id": self.session.id,
                "time": 2,
                "date": "2026-09-07",
                "users": [self.jigi.id, self.senior.id],
                "arrival_time": "11:15:00",
                "mentees": [],
                "mentee_arrival_time": "11:30:00",
                "time_comment_music": "앙코르 요청",
                "time_comment_gigi": "",
                "time_comment_etc": "",
                "user": self.jigi.id,
                "mentee": None,
                "jigi_info": ["김지기 음악학과 22", "이선배 물리학과 21"],
                "mentee_info": [],
            },
        )
        self.assertEqual(
            self.saved(self.session.id),
            {
                "date": datetime.date(2026, 9, 7),
                "time": 2,
                "users": [self.jigi.id, self.senior.id],
                "mentees": [],
                "arrival_time": datetime.time(11, 15),
                "mentee_arrival_time": datetime.time(11, 30),
                "time_comment_music": "앙코르 요청",
            },
        )

    def test_edit_with_null_clears_the_mentee_arrival_time(self):
        response = self.edit(mentees=[], mentee_arrival_time=None)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["mentee_arrival_time"])
        self.assertIsNone(self.saved(self.session.id)["mentee_arrival_time"])

    def test_malformed_times_are_400_and_save_nothing(self):
        before = self.saved(self.session.id)
        cases = [
            ("arrival_time", ""),
            ("arrival_time", None),
            ("arrival_time", "abc"),
            ("mentee_arrival_time", "abc"),
            ("mentee_arrival_time", "25:00"),
        ]
        for field, value in cases:
            for send in [self.create, self.edit]:
                with self.subTest(field=field, value=value, send=send.__name__):
                    response = send(**{field: value, "users": [self.senior.id]})
                    self.assertEqual(response.status_code, 400)
                    self.assertIn(field, response.json())
        self.assertEqual(TimeInfo.objects.count(), 1)
        self.assertEqual(self.saved(self.session.id), before)

import datetime
from unittest import mock

from django.db import OperationalError
from django.urls import reverse
from rest_framework.test import APITestCase

from apps.time_manage.models import Semester, TimeInfo, TimetableUnit, User


class UserReadTests(APITestCase):
    """GET user/ feeds every 지기 picker in the frontend, with each 사부 spelled out."""

    def setUp(self):
        self.sabu = User.objects.create(
            name="이사부",
            major="물리학과",
            year_id="20",
            is_ob=True,
            join_year=2020,
            join_semester=1,
        )
        self.jeja = User.objects.create(
            name="김제자",
            major="음악학과",
            year_id="22",
            join_year=2022,
            join_semester=2,
            sabu_id=self.sabu,
        )
        self.newcomer = User.objects.create(
            name="박신입", major="경제학부", year_id="25", join_year=2025
        )
        self.alumnus = User.objects.create(name="최동문", major="국문과", year_id="98")

    def body(self, user, sabu_info=""):
        return {
            "id": user.id,
            "sabu_info": sabu_info,
            "name": user.name,
            "major": user.major,
            "year_id": user.year_id,
            "is_ob": user.is_ob,
            "join_year": user.join_year,
            "join_semester": user.join_semester,
            "sabu_id": user.sabu_id_id,
        }

    def test_lists_everyone_newest_first_with_their_sabu(self):
        response = self.client.get(reverse("user-list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                self.body(self.newcomer),
                self.body(self.jeja, sabu_info="이사부 물리학과 20"),
                self.body(self.sabu),
                self.body(self.alumnus),
            ],
        )

    def test_detail_shows_the_sabu(self):
        response = self.client.get(reverse("user-detail", args=[self.jeja.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.body(self.jeja, "이사부 물리학과 20"))

    def test_changing_or_clearing_the_sabu_shows_the_new_one(self):
        url = reverse("user-detail", args=[self.jeja.id])
        response = self.client.patch(url, {"sabu_id": self.newcomer.id}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sabu_info"], "박신입 경제학부 25")

        response = self.client.patch(url, {"sabu_id": None}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sabu_info"], "")
        self.jeja.refresh_from_db()
        self.assertIsNone(self.jeja.sabu_id)

    def test_an_edit_that_keeps_the_sabu_still_shows_it(self):
        response = self.client.put(
            reverse("user-detail", args=[self.jeja.id]),
            {"name": "김제자", "major": "작곡과", "year_id": "22"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["major"], "작곡과")
        self.assertEqual(response.json()["sabu_info"], "이사부 물리학과 20")

    def test_reads_users_in_one_query_however_many_have_a_sabu(self):
        for i in range(20):
            User.objects.create(
                name=f"제자{i}",
                major="음악학과",
                year_id="24",
                join_year=2024,
                sabu_id=[self.sabu, self.jeja, self.newcomer][i % 3],
            )
        with self.assertNumQueries(1):
            response = self.client.get(reverse("user-list"))
        self.assertEqual(len(response.json()), 24)

        with self.assertNumQueries(1):
            response = self.client.get(reverse("user-detail", args=[self.jeja.id]))
        self.assertEqual(response.json()["sabu_info"], "이사부 물리학과 20")
        # Read the 지기 with the 사부, then save; the answer needs no third.
        with self.assertNumQueries(2):
            response = self.client.patch(
                reverse("user-detail", args=[self.jeja.id]),
                {"major": "작곡과"},
                format="json",
            )
        self.assertEqual(response.json()["sabu_info"], "이사부 물리학과 20")


class UserWriteTests(APITestCase):
    """지기 설정 adds a 지기 with POST user/ and edits one with PUT user/<id>/.

    입부 년도 and 학기 are free-text inputs that send "" when left empty.
    """

    def setUp(self):
        self.jigi = User.objects.create(
            name="김지기",
            major="음악학과",
            year_id="22",
            join_year=2022,
            join_semester=2,
        )

    def form(self, **fields):
        # What the add and edit forms send.
        body = {
            "name": "박신입",
            "major": "경제학부",
            "year_id": "26",
            "is_ob": False,
            "sabu_id": None,
            "join_year": 2026,
            "join_semester": 1,
        }
        body.update(fields)
        return body

    def add(self, **fields):
        url = reverse("user-list")
        return self.client.post(url, self.form(**fields), format="json")

    def edit(self, **fields):
        url = reverse("user-detail", args=[self.jigi.id])
        return self.client.put(url, self.form(**fields), format="json")

    def joined(self, user):
        user.refresh_from_db()
        return user.join_year, user.join_semester

    def test_an_empty_join_year_or_semester_is_saved_as_none(self):
        response = self.add(join_year="")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["join_year"], None)
        self.assertEqual(self.joined(User.objects.get(name="박신입")), (None, 1))

        response = self.edit(join_year="", join_semester="")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["join_semester"], None)
        self.assertEqual(self.joined(self.jigi), (None, None))
        self.assertEqual(self.jigi.name, "박신입")

    def test_a_join_year_or_semester_is_saved_as_sent(self):
        self.assertEqual(self.edit(join_year="2025").status_code, 200)
        self.assertEqual(self.joined(self.jigi), (2025, 1))
        self.assertEqual(self.edit(join_year=None, join_semester=2).status_code, 200)
        self.assertEqual(self.joined(self.jigi), (None, 2))
        for largest in (2**63 - 1, -(2**63)):
            self.assertEqual(self.edit(join_year=largest).status_code, 200)
            self.assertEqual(self.joined(self.jigi), (largest, 1))

    def test_a_join_year_or_semester_past_sqlites_integers_is_a_400(self):
        # Past SQLite's 64-bit INTEGER the save raised OverflowError (500).
        for field in ("join_year", "join_semester"):
            for value in (2**63, -(2**63) - 1, 10**30, "abc", "  "):
                with self.subTest(field=field, value=value):
                    response = self.add(**{field: value})
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(list(response.json()), [field])
                    response = self.edit(**{field: value})
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(list(response.json()), [field])
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(self.joined(self.jigi), (2022, 2))
        self.assertEqual(self.jigi.name, "김지기")


class UserDeleteTests(APITestCase):
    """지기 설정 deletes a 지기 with one confirm, then DELETE user/<id>/."""

    def setUp(self):
        self.ob = User.objects.create(
            name="정선배", major="국문과", year_id="16", is_ob=True, join_year=2016
        )
        self.sabu = User.objects.create(
            name="이사부",
            major="물리학과",
            year_id="20",
            join_year=2020,
            sabu_id=self.ob,
        )
        self.jeja = User.objects.create(
            name="김제자",
            major="음악학과",
            year_id="22",
            join_year=2022,
            sabu_id=self.sabu,
        )
        self.grandjeja = User.objects.create(
            name="한손제",
            major="작곡과",
            year_id="24",
            join_year=2024,
            sabu_id=self.jeja,
        )
        self.loner = User.objects.create(
            name="최동문", major="경제학부", year_id="23", join_year=2023
        )
        self.session = TimeInfo.objects.create(
            time=2, date=datetime.date(2026, 3, 4), arrival_time="11:00:00"
        )
        self.session.users.set([self.sabu, self.jeja])
        self.session.mentees.set([self.grandjeja])
        semester = Semester.objects.create(
            year=2026,
            semester_num=1,
            total_time=4,
            start_time="09:30:00",
            end_time="17:40:00",
        )
        self.cell = TimetableUnit.objects.get(
            timetable=semester.timetable, day=2, time=2
        )
        self.cell.users.set([self.jeja])
        self.cell.mentees.set([self.grandjeja])

    def delete(self, user):
        return self.client.delete(reverse("user-detail", args=[user.id]))

    def sabus(self):
        """Each remaining 지기's name → their 사부's name (None without one)."""
        return {
            user.name: user.sabu_id.name if user.sabu_id else None
            for user in User.objects.select_related("sabu_id")
        }

    def names(self, users):
        return sorted(users.values_list("name", flat=True))

    def test_deleting_a_jigi_without_jeja_deletes_only_them(self):
        response = self.delete(self.grandjeja)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(
            self.sabus(),
            {"정선배": None, "이사부": "정선배", "김제자": "이사부", "최동문": None},
        )
        # They leave the sessions and cells they were in; the others stay.
        self.assertEqual(self.names(self.session.users), ["김제자", "이사부"])
        self.assertEqual(self.names(self.session.mentees), [])
        self.assertEqual(self.names(self.cell.users), ["김제자"])
        self.assertEqual(self.names(self.cell.mentees), [])

    def test_deleting_a_missing_jigi_is_a_404(self):
        response = self.client.delete(reverse("user-detail", args=[999999]))
        self.assertEqual(response.status_code, 404)
        self.assertEqual(User.objects.count(), 5)

    def test_a_jigi_who_is_their_own_sabu_can_be_deleted(self):
        # The 사부 picker of the edit form lists every 지기, the one edited too.
        self.loner.sabu_id = self.loner
        self.loner.save()
        response = self.delete(self.loner)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(
            self.sabus(),
            {
                "정선배": None,
                "이사부": "정선배",
                "김제자": "이사부",
                "한손제": "김제자",
            },
        )

    def test_deleting_a_sabu_keeps_their_jeja_without_a_sabu(self):
        response = self.delete(self.sabu)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(
            self.sabus(),
            {"정선배": None, "김제자": None, "한손제": "김제자", "최동문": None},
        )
        # The 제자 keep their sessions and timetable cells.
        self.assertEqual(self.names(self.session.users), ["김제자"])
        self.assertEqual(self.names(self.session.mentees), ["한손제"])
        self.assertEqual(self.names(self.cell.users), ["김제자"])
        self.assertEqual(self.names(self.cell.mentees), ["한손제"])
        response = self.client.get(reverse("user-detail", args=[self.jeja.id]))
        self.assertEqual(response.json()["sabu_id"], None)
        self.assertEqual(response.json()["sabu_info"], "")

    def test_deleting_one_of_two_jigis_who_are_each_others_sabu(self):
        self.ob.sabu_id = self.sabu
        self.ob.save()
        response = self.delete(self.ob)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(
            self.sabus(),
            {"이사부": None, "김제자": "이사부", "한손제": "김제자", "최동문": None},
        )

    def test_a_failed_delete_keeps_every_sabu(self):
        locked = OperationalError("database is locked")
        with mock.patch.object(User, "delete", side_effect=locked):
            with self.assertRaises(OperationalError):
                self.delete(self.sabu)
        self.assertEqual(
            self.sabus(),
            {
                "정선배": None,
                "이사부": "정선배",
                "김제자": "이사부",
                "한손제": "김제자",
                "최동문": None,
            },
        )

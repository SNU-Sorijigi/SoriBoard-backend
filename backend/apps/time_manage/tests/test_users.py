from django.urls import reverse
from rest_framework.test import APITestCase

from apps.time_manage.models import User


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

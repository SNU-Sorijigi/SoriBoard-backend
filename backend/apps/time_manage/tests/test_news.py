from django.urls import reverse
from rest_framework.test import APITestCase

from apps.time_manage.models import News


class NewsTests(APITestCase):
    """information/ holds the news 뉴스 설정 edits and the TV shows."""

    def setUp(self):
        # Created out of alphabetical order, so id order is not content order.
        self.concert = News.objects.create(content="정기 감상회 3/24 19:00")
        self.closed = News.objects.create(content="동아리방 공사로 3/10 휴관")
        self.recruit = News.objects.create(content="신입 지기 모집 중")

    def detail(self, news_id):
        return reverse("information-detail", args=[news_id])

    def body(self, news):
        return {"id": news.id, "content": news.content}

    def test_lists_the_news_oldest_first(self):
        # The TV shows the first entry; editing a news keeps its place.
        response = self.client.put(
            self.detail(self.concert.id),
            {"content": "정기 감상회 3/31로 연기"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.concert.refresh_from_db()

        with self.assertNumQueries(1):
            response = self.client.get(reverse("information-list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [self.body(self.concert), self.body(self.closed), self.body(self.recruit)],
        )

        News.objects.all().delete()
        self.assertEqual(self.client.get(reverse("information-list")).json(), [])

    def test_creates_a_news(self):
        response = self.client.post(
            reverse("information-list"),
            {"content": "  기말고사 기간 단축 운영  ", "id": self.closed.id},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        news = News.objects.get(pk=response.json()["id"])
        # Spaces around the content are trimmed, and an id in the body is ignored.
        self.assertEqual(news.content, "기말고사 기간 단축 운영")
        self.assertNotEqual(news.id, self.closed.id)
        self.assertEqual(response.json(), self.body(news))

        response = self.client.post(
            reverse("information-list"), {"content": "가" * 100}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(News.objects.get(pk=response.json()["id"]).content, "가" * 100)

    def test_shows_and_edits_one_news(self):
        url = self.detail(self.recruit.id)
        self.assertEqual(self.client.get(url).json(), self.body(self.recruit))

        response = self.client.put(
            url, {"content": "신입 지기 모집 마감"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.recruit.refresh_from_db()
        self.assertEqual(self.recruit.content, "신입 지기 모집 마감")
        self.assertEqual(response.json(), self.body(self.recruit))

        response = self.client.patch(url, {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.body(self.recruit))

    def test_refuses_a_blank_missing_or_too_long_content(self):
        bad_bodies = [
            ({"content": ""}, "This field may not be blank."),
            ({"content": "   "}, "This field may not be blank."),
            ({"content": None}, "This field may not be null."),
            ({}, "This field is required."),
            (
                {"content": "가" * 101},
                "Ensure this field has no more than 100 characters.",
            ),
        ]
        for body, message in bad_bodies:
            with self.subTest(method="POST", body=body):
                response = self.client.post(
                    reverse("information-list"), body, format="json"
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {"content": [message]})
            with self.subTest(method="PUT", body=body):
                response = self.client.put(
                    self.detail(self.recruit.id), body, format="json"
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {"content": [message]})
        self.assertEqual(News.objects.count(), 3)
        self.recruit.refresh_from_db()
        self.assertEqual(self.recruit.content, "신입 지기 모집 중")

    def test_deletes_a_news(self):
        url = self.detail(self.recruit.id)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(News.objects.filter(pk=self.recruit.id).exists())
        self.assertEqual(self.client.delete(url).status_code, 404)
        self.assertEqual(
            self.client.get(reverse("information-list")).json(),
            [self.body(self.concert), self.body(self.closed)],
        )

    def test_a_missing_or_malformed_id_is_not_found(self):
        for url in (self.detail(9999), "/time_manage/information/abc/"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)
                response = self.client.put(url, {"content": "x"}, format="json")
                self.assertEqual(response.status_code, 404)
                self.assertEqual(self.client.delete(url).status_code, 404)
        self.assertEqual(News.objects.count(), 3)

import datetime

from django.urls import reverse
from rest_framework.test import APITestCase

from apps.time_manage.models import Composer, Music, TimeInfo, TimeMusic


class SwapOrderTests(APITestCase):
    """POST swaporder/<id>/<id>/ is the session page's ↑/↓: it swaps two plays'
    places in the playlist. ↓ sends the play and the next one, ↑ the play and
    the one before it."""

    def setUp(self):
        self.session = TimeInfo.objects.create(
            date=datetime.date(2026, 9, 7), time=2, arrival_time="11:20:00"
        )
        self.music = Music.objects.create(
            composer=Composer.objects.create(name="루트비히 판 베토벤"),
            title="교향곡 제7번 Op. 92",
        )
        self.first = self.add_play(1)
        self.second = self.add_play(2)
        self.third = self.add_play(3)

    def add_play(self, order):
        return TimeMusic.objects.create(
            time=self.session, order=order, source="CD", music=self.music
        )

    def swap(self, play, other):
        return self.client.post(reverse("swaporder", args=[play.id, other.id]))

    def listed(self):
        """The plays as the session page lists them."""
        response = self.client.get(reverse("timeinfo-detail", args=[self.session.id]))
        return [play["id"] for play in response.json()["time_music"]]

    def orders(self):
        return list(TimeMusic.objects.order_by("id").values_list("order", flat=True))

    def test_down_swaps_a_play_with_the_next(self):
        response = self.swap(self.first, self.second)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Order swapped successfully."})
        self.assertEqual(self.listed(), [self.second.id, self.first.id, self.third.id])
        self.assertEqual(self.orders(), [2, 1, 3])

    def test_up_swaps_a_play_with_the_one_before(self):
        self.assertEqual(self.swap(self.third, self.second).status_code, 200)
        self.assertEqual(self.listed(), [self.first.id, self.third.id, self.second.id])

    def test_a_missing_play_changes_nothing(self):
        missing = TimeMusic(id=self.third.id + 1)
        for pair in [(self.first, missing), (missing, self.first)]:
            response = self.swap(*pair)
            self.assertEqual(response.status_code, 404)
            self.assertEqual(
                response.json(),
                {
                    "error": "One or both of the specified TimeMusic instances do not exist."
                },
            )
        self.assertEqual(self.listed(), [self.first.id, self.second.id, self.third.id])
        self.assertEqual(self.orders(), [1, 2, 3])

    def test_plays_with_the_same_order_are_listed_by_id(self):
        # A double-clicked 추가 sends the same order twice.
        again = self.add_play(2)
        third_again = self.add_play(3)
        self.assertEqual(
            self.listed(),
            [self.first.id, self.second.id, again.id, self.third.id, third_again.id],
        )

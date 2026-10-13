import datetime
from unittest.mock import patch

from django.db import OperationalError
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

    def test_plays_from_two_sessions_are_not_swapped(self):
        # A tie, so a refused swap must not renumber this session either.
        again = self.add_play(3)
        other_session = TimeInfo.objects.create(
            date=datetime.date(2026, 9, 7), time=3, arrival_time="13:20:00"
        )
        elsewhere = TimeMusic.objects.create(
            time=other_session, order=7, source="CD", music=self.music
        )
        for pair in [(self.first, elsewhere), (elsewhere, again)]:
            response = self.swap(*pair)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(
                response.json(), {"error": "The two plays are in different sessions."}
            )
        self.assertEqual(self.orders(), [1, 2, 3, 3, 7])
        self.assertEqual(
            self.listed(), [self.first.id, self.second.id, self.third.id, again.id]
        )

    def test_plays_with_the_same_order_are_listed_by_id(self):
        # A double-clicked 추가 sends the same order twice.
        again = self.add_play(2)
        third_again = self.add_play(3)
        self.assertEqual(
            self.listed(),
            [self.first.id, self.second.id, again.id, self.third.id, third_again.id],
        )

    def test_a_play_moves_past_one_with_the_same_order(self):
        again = self.add_play(2)
        self.assertEqual(self.swap(self.second, again).status_code, 200)
        self.assertEqual(
            self.listed(), [self.first.id, again.id, self.second.id, self.third.id]
        )
        # ↑ takes it back.
        self.assertEqual(self.swap(self.second, again).status_code, 200)
        self.assertEqual(
            self.listed(), [self.first.id, self.second.id, again.id, self.third.id]
        )

    def test_a_tie_above_does_not_misplace_the_move(self):
        early, late = self.add_play(1), self.add_play(1)
        # Listed first, early, late, second, third: ↑ on second.
        self.assertEqual(self.swap(self.second, late).status_code, 200)
        self.assertEqual(
            self.listed(),
            [self.first.id, early.id, self.second.id, late.id, self.third.id],
        )

    def test_a_failed_swap_changes_neither_play(self):
        save = TimeMusic.save
        saved = []

        def fail_the_second_save(play, *args, **kwargs):
            if saved:
                raise OperationalError("database is locked")
            saved.append(play.id)
            save(play, *args, **kwargs)

        with patch.object(TimeMusic, "save", fail_the_second_save):
            with self.assertRaises(OperationalError):
                self.swap(self.first, self.second)
        self.assertEqual(saved, [self.first.id])
        self.assertEqual(self.orders(), [1, 2, 3])

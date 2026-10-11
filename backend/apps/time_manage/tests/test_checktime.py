import datetime

from django.urls import reverse
from rest_framework.test import APITestCase

from apps.time_manage.models import TimeInfo


class CheckTimeTests(APITestCase):
    def session(self, date, time):
        return TimeInfo.objects.create(date=date, time=time, arrival_time="09:30:00").id

    def grid(self, start, end):
        response = self.client.get(
            reverse(
                "checktime",
                args=[start.year, start.month, start.day, end.year, end.month, end.day],
            )
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_one_row_per_day_with_each_session_id_in_its_slot(self):
        monday = datetime.date(2026, 9, 7)
        wednesday = monday + datetime.timedelta(days=2)
        first = self.session(monday, 1)
        third = self.session(wednesday, 3)
        last = self.session(wednesday, 5)
        self.assertEqual(
            self.grid(monday, wednesday),
            [
                [first, None, None, None, None],
                [None, None, None, None, None],
                [None, None, third, None, last],
            ],
        )

    def test_sessions_outside_the_range_or_slots_one_to_five_are_left_out(self):
        day = datetime.date(2026, 9, 7)
        self.session(day - datetime.timedelta(days=1), 1)
        self.session(day + datetime.timedelta(days=1), 1)
        self.session(day, 0)
        self.session(day, 6)
        kept = self.session(day, 2)
        self.assertEqual(self.grid(day, day), [[None, kept, None, None, None]])

    def test_range_runs_across_years_and_leap_days(self):
        new_year = self.session(datetime.date(2026, 1, 1), 1)
        leap_day = self.session(datetime.date(2024, 2, 29), 4)
        self.assertEqual(
            self.grid(datetime.date(2025, 12, 31), datetime.date(2026, 1, 1)),
            [[None] * 5, [new_year, None, None, None, None]],
        )
        self.assertEqual(
            self.grid(datetime.date(2024, 2, 28), datetime.date(2024, 3, 1)),
            [[None] * 5, [None, None, None, leap_day, None], [None] * 5],
        )

    def test_zero_padded_path_from_the_frontend_works(self):
        day = self.session(datetime.date(2026, 9, 7), 1)
        response = self.client.get("/time_manage/checktime/2026/09/07/2026/09/07/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [[day, None, None, None, None]])

    def test_impossible_or_reversed_dates_get_400(self):
        cases = {
            (2026, 2, 30, 2026, 3, 1): "Invalid date format",
            (2026, 9, 8, 2026, 9, 7): "Start date must be before end date",
        }
        for args, error in cases.items():
            with self.subTest(args=args):
                response = self.client.get(reverse("checktime", args=args))
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json(), {"error": error})

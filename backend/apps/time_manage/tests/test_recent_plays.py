import datetime
from unittest.mock import patch

from django.urls import reverse
from rest_framework.test import APITestCase

from apps.time_manage.models import Composer, Music, TimeInfo, TimeMusic


class RecentPlaysTests(APITestCase):
    reference_date = datetime.date(2026, 9, 5)

    def setUp(self):
        self.session = TimeInfo.objects.create(
            date=self.reference_date, time=1, arrival_time="09:30:00"
        )

    def play(self, composer_name, title, days_ago=0, session=1, order=1):
        composer, _ = Composer.objects.get_or_create(name=composer_name)
        music, _ = Music.objects.get_or_create(composer=composer, title=title)
        time, _ = TimeInfo.objects.get_or_create(
            date=self.reference_date - datetime.timedelta(days=days_ago),
            time=session,
            defaults={"arrival_time": "09:30:00"},
        )
        return TimeMusic.objects.create(
            music=music, time=time, order=order, source="ROON"
        )

    def lookup(self, composer_name, title=""):
        response = self.client.get(
            reverse("recent-plays"),
            {
                "time_id": self.session.id,
                "composer_name": composer_name,
                "title": title,
            },
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_empty_composer_only_reads_the_session_date(self):
        self.play("세르게이 라흐마니노프", "교향곡 제3번")
        with self.assertNumQueries(1):
            self.assertEqual(
                self.lookup("   ", "교향곡"),
                {"reference_date": "2026-09-05", "composers": [], "works": []},
            )

    def test_prefix_returns_only_composers_played_within_30_days(self):
        self.play("세르게이 라흐마니노프", "교향곡 제3번")
        self.play("세르게이 프로코피예프", "교향곡 제7번", days_ago=20)
        self.play("세르게이 옛기록", "옛 곡", days_ago=30)
        self.play("세르게이 미래기록", "예정 곡", days_ago=-1)
        self.play("드미트리 쇼스타코비치", "교향곡 제5번")
        Composer.objects.create(name="세르게이 미선곡")

        with self.assertNumQueries(2):
            result = self.lookup(" 세르게이 ")
        self.assertEqual(
            [item["name"] for item in result["composers"]],
            ["세르게이 라흐마니노프", "세르게이 프로코피예프"],
        )
        self.assertEqual(result["composers"][1]["count_7d"], 0)
        self.assertEqual(result["composers"][1]["count_30d"], 1)
        self.assertEqual(result["works"], [])
        self.assertEqual(self.lookup("라흐마니노프")["composers"], [])

    def test_calendar_windows_and_latest_three_use_session_and_playlist_order(self):
        name = "세르게이 라흐마니노프"
        self.play(name, "오전 선곡", session=1, order=10)
        self.play(name, "첫 번째 선곡", session=2, order=1)
        self.play(name, "두 번째 선곡", session=2, order=2)
        self.play(name, "어제 선곡", days_ago=1)
        self.play(name, "7일 범위 안", days_ago=6)
        self.play(name, "7일 범위 밖", days_ago=7)
        self.play(name, "30일 범위 안", days_ago=29)
        self.play(name, "30일 범위 밖", days_ago=30)
        self.play(name, "미래 선곡", days_ago=-1)

        composer = self.lookup(name)["composers"][0]
        self.assertEqual(composer["count_1d"], 3)
        self.assertEqual(composer["count_7d"], 5)
        self.assertEqual(composer["count_30d"], 7)
        self.assertEqual(
            composer["recent_titles"], ["두 번째 선곡", "첫 번째 선곡", "오전 선곡"]
        )

    def test_title_prefix_counts_repeats_and_reports_latest_date(self):
        name = "세르게이 라흐마니노프"
        for days_ago in (3, 5, 12, 29, 30):
            self.play(name, "교향곡 제3번", days_ago=days_ago)
        self.play(name, "피아노 소나타 제2번")
        self.play("세르게이 프로코피예프", "교향곡 제3번", days_ago=1)

        result = self.lookup(name, " 교향곡 제3 ")
        self.assertEqual(result["composers"][0]["count_30d"], 5)
        self.assertEqual(
            result["works"],
            [
                {
                    "composer_name": name,
                    "title": "교향곡 제3번",
                    "count_30d": 4,
                    "last_played": "2026-09-02",
                    "days_since_last_played": 3,
                }
            ],
        )
        self.assertEqual(self.lookup(name, "제3번")["works"], [])

    def test_same_title_by_different_composers_stays_separate(self):
        for name in ("세르게이 라흐마니노프", "세르게이 프로코피예프"):
            self.play(name, "교향곡 제3번")
        result = self.lookup("세르게이", "교향곡")
        self.assertEqual(len(result["works"]), 2)
        self.assertTrue(all(work["count_30d"] == 1 for work in result["works"]))
        self.assertTrue(
            all(work["days_since_last_played"] == 0 for work in result["works"])
        )

    def test_matching_is_case_insensitive_and_wildcards_are_literal(self):
        self.play("Sergei Rachmaninoff", "Symphony No. 3")
        self.play("Sergei%Test", "Piano Concerto")
        self.play("Sergei_Test", "Piano Sonata")
        result = self.lookup("sergei r", "sYmPhOnY")
        self.assertEqual(result["works"][0]["title"], "Symphony No. 3")
        self.assertEqual(
            [item["name"] for item in self.lookup("Sergei%")["composers"]],
            ["Sergei%Test"],
        )
        self.assertEqual(
            [item["name"] for item in self.lookup("Sergei_")["composers"]],
            ["Sergei_Test"],
        )

    def test_unmatched_input_has_no_results(self):
        self.assertEqual(
            self.lookup("없는 작곡가"),
            {"reference_date": "2026-09-05", "composers": [], "works": []},
        )

    def test_existing_catalog_duplicate_warning_is_still_available(self):
        name = "세르게이 라흐마니노프"
        self.play(name, "피아노 협주곡 제2번 Op. 18", days_ago=3)
        response = self.client.get(
            reverse("check-duplicate"),
            {
                "time_id": self.session.id,
                "composer_name": name,
                "title": "Piano Concerto Op.18",
                "days": 7,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["duplicates"]), 1)

    def test_june_session_uses_may_june_history_even_when_today_is_september(self):
        self.reference_date = datetime.date(2026, 6, 25)
        self.session.date = self.reference_date
        self.session.save(update_fields=["date"])
        name = "세르게이 라흐마니노프"
        self.play(name, "타임 당일 작품")
        for days_ago in (3, 6, 7, 29, 30, -1, -72):
            self.play(name, "교향곡 제3번", days_ago=days_ago)
        self.play("세르게이 5월 기록", "경계 안 작품", days_ago=29)
        self.play("세르게이 오래된 기록", "경계 밖 작품", days_ago=30)
        self.play("세르게이 이후 기록", "다음 날 작품", days_ago=-1)
        self.play("세르게이 9월 기록", "9월 작품", days_ago=-72)

        with patch(
            "django.utils.timezone.localdate",
            return_value=datetime.date(2026, 9, 5),
        ):
            result = self.lookup("세르게이", "교향곡")

        self.assertEqual(result["reference_date"], "2026-06-25")
        self.assertEqual(
            [item["name"] for item in result["composers"]],
            [name, "세르게이 5월 기록"],
        )
        composer = result["composers"][0]
        self.assertEqual(composer["count_1d"], 1)
        self.assertEqual(composer["count_7d"], 3)
        self.assertEqual(composer["count_30d"], 5)
        self.assertEqual(
            composer["recent_titles"],
            ["타임 당일 작품", "교향곡 제3번", "교향곡 제3번"],
        )
        self.assertEqual(len(result["works"]), 1)
        self.assertEqual(result["works"][0]["count_30d"], 4)
        self.assertEqual(result["works"][0]["last_played"], "2026-06-22")
        self.assertEqual(result["works"][0]["days_since_last_played"], 3)

    def test_duplicate_warning_uses_the_same_session_date_and_seven_day_window(self):
        self.reference_date = datetime.date(2026, 6, 25)
        self.session.date = self.reference_date
        self.session.save(update_fields=["date"])
        name = "세르게이 라흐마니노프"
        for days_ago in (0, 3, 6, 7, -1, -72):
            self.play(name, "피아노 협주곡 제2번 Op. 18", days_ago=days_ago)

        response = self.client.get(
            reverse("check-duplicate"),
            {
                "time_id": self.session.id,
                "composer_name": name,
                "title": "Piano Concerto Op.18",
                "days": 7,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertCountEqual(
            [item["date"] for item in response.json()["duplicates"]],
            ["2026-06-25", "2026-06-22", "2026-06-19"],
        )

    def test_saved_session_date_is_read_again_after_it_changes(self):
        name = "세르게이 라흐마니노프"
        self.play(name, "교향곡 제3번", days_ago=3)
        self.assertEqual(self.lookup(name)["composers"][0]["count_30d"], 1)
        self.session.date = datetime.date(2026, 6, 25)
        self.session.save(update_fields=["date"])
        self.assertEqual(
            self.lookup(name),
            {"reference_date": "2026-06-25", "composers": [], "works": []},
        )

    def test_future_session_uses_its_own_date_too(self):
        self.reference_date = datetime.date(2027, 1, 10)
        self.session.date = self.reference_date
        self.session.save(update_fields=["date"])
        name = "세르게이 라흐마니노프"
        self.play(name, "교향곡 제3번", days_ago=3)
        result = self.lookup(name, "교향곡")
        self.assertEqual(result["reference_date"], "2027-01-10")
        self.assertEqual(result["works"][0]["last_played"], "2027-01-07")
        self.assertEqual(result["works"][0]["days_since_last_played"], 3)

    def test_missing_invalid_or_unknown_session_never_falls_back_to_today(self):
        for endpoint in ("recent-plays", "check-duplicate"):
            for time_id, expected_status in (
                (None, 400),
                ("", 400),
                ("not-a-session", 400),
                (0, 400),
                (999999, 404),
            ):
                with self.subTest(endpoint=endpoint, time_id=time_id):
                    params = {"composer_name": "세르게이", "title": "교향곡"}
                    if time_id is not None:
                        params["time_id"] = time_id
                    response = self.client.get(reverse(endpoint), params)
                    self.assertEqual(response.status_code, expected_status)

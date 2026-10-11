import datetime

from django.urls import reverse
from rest_framework.test import APITestCase

from apps.time_manage.models import (
    Composer,
    Conductor,
    Music,
    Orchestra,
    Player,
    Semester,
    TimeInfo,
    TimeMusic,
    User,
)

GENRES = ["교향곡", "협주곡", "실내악곡", "독주곡", "기타"]


class StatsRequests:
    def get(self, name, **params):
        response = self.client.get(reverse(f"stats-{name}"), params)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def counts(self, result):
        return dict(zip(result["labels"], result["values"]))

    def assert_no_plays(self, **params):
        summary = self.get("summary", **params)
        for key in ("total_plays", "composers", "works", "conductors", "orchestras"):
            self.assertEqual(summary[key], 0)
        self.assertIsNone(summary["date_start"])
        self.assertIsNone(summary["date_end"])

        for name in ("composers", "eras", "genres"):
            with self.subTest(endpoint=name):
                result = self.get(name, **params)
                self.assertEqual(result["total_plays"], 0)
                self.assertEqual(result["labels"], [])
                self.assertEqual(result["values"], [])
                self.assertEqual(result["items"], [])
        self.assertEqual(self.get("eras", **params)["unknown_share"], 0)

        diversity = self.get("diversity", **params)
        self.assertEqual(diversity["total_plays"], 0)
        no_spread = {"entropy": 0.0, "evenness": 0.0}
        self.assertEqual(
            diversity["summary"],
            {
                "distinct_works": 0,
                "distinct_composers": 0,
                "era": {"labels": [], "values": [], "unknown_share": 0, **no_spread},
                "genre": {"labels": [], "values": [], **no_spread},
            },
        )
        self.assertEqual(
            diversity["timeline"],
            {
                "bucket": "week",
                "labels": [],
                "plays": [],
                "distinct_works": [],
                "era_evenness": [],
                "genre_evenness": [],
            },
        )


class EmptyStatsTests(StatsRequests, APITestCase):
    def test_no_plays_gives_zero_counts_and_empty_charts(self):
        self.assert_no_plays()


class StatsTests(StatsRequests, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.member = User.objects.create(name="지기", major="음악학과", year_id="20")
        partner = User.objects.create(name="동료 지기", major="음악학과", year_id="21")
        cls.mentee = User.objects.create(
            name="견습 지기", major="물리학과", year_id="24"
        )
        other_mentee = User.objects.create(
            name="다른 견습", major="화학과", year_id="24"
        )

        bach = Composer.objects.create(name="바흐", birth_year=1685)
        mozart = Composer.objects.create(name="모차르트", birth_year=1756)
        brahms = Composer.objects.create(name="브람스", birth_year=1833)
        # 1770 is 낭만 by birth year; the manual override keeps him 고전.
        beethoven = Composer.objects.create(
            name="베토벤", birth_year=1770, era_override="고전"
        )
        anonymous = Composer.objects.create(name="작자 미상")
        cls.mozart = mozart

        suite = Music.objects.create(composer=bach, title="무반주 첼로 모음곡 제1번")
        symphony = Music.objects.create(composer=mozart, title="교향곡 제40번")
        concerto = Music.objects.create(composer=brahms, title="피아노 협주곡 제2번")
        quartet = Music.objects.create(composer=beethoven, title="현악 사중주 제14번")
        chant = Music.objects.create(composer=anonymous, title="그레고리오 성가")

        karajan = Conductor.objects.create(name="카라얀")
        bernstein = Conductor.objects.create(name="번스타인")
        berlin = Orchestra.objects.create(name="베를린 필하모닉")
        vienna = Orchestra.objects.create(name="빈 필하모닉")

        def player(name, instrument):
            return Player.objects.create(name=name, instrument=instrument)

        def session(date, time=1, users=(), mentees=()):
            info = TimeInfo.objects.create(
                date=date, time=time, arrival_time="09:30:00"
            )
            info.users.set(users)
            info.mentees.set(mentees)
            return info

        def play(info, order, music, conductor=None, orchestra=None, players=()):
            tm = TimeMusic.objects.create(
                time=info,
                order=order,
                source="CD",
                music=music,
                conductor=conductor,
                orchestra=orchestra,
            )
            tm.players.set(players)

        # Six plays: a leap day, then two March weeks (Mondays 3/4 and 3/11).
        leap_day = session(datetime.date(2024, 2, 29), users=[cls.member])
        play(leap_day, 1, suite, players=[player("첼리스트", "첼로")])

        shared = session(
            datetime.date(2024, 3, 4),
            users=[cls.member, partner],
            mentees=[cls.mentee, other_mentee],
        )
        play(shared, 1, symphony, karajan, berlin)
        play(shared, 2, concerto, karajan, berlin, [player("피아니스트", "피아노")])

        mentored = session(
            datetime.date(2024, 3, 6), time=2, users=[partner], mentees=[cls.mentee]
        )
        play(mentored, 1, symphony, bernstein, vienna)

        promoted = session(datetime.date(2024, 3, 12), users=[cls.mentee])
        quartet_players = [
            player("제1바이올린", "바이올린"),
            player("제2바이올린", "바이올린"),
            player("비올리스트", "비올라"),
            player("사중주 첼리스트", "첼로"),
        ]
        play(promoted, 1, quartet, players=quartet_players)
        play(promoted, 2, chant)

        def semester(year, num):
            return Semester.objects.create(
                year=year, semester_num=num, start_time="09:30", end_time="17:40"
            )

        cls.fall_2023 = semester(2023, 2)
        cls.spring_2024 = semester(2024, 1)
        cls.fall_2024 = semester(2024, 2)

    def test_summary_counts_plays_catalogue_and_date_span(self):
        self.assertEqual(
            self.get("summary"),
            {
                "filters": {"scope": "all"},
                "total_plays": 6,
                "composers": 5,
                "works": 5,
                "conductors": 2,
                "orchestras": 2,
                "date_start": "2024-02-29",
                "date_end": "2024-03-12",
            },
        )

    def test_composers_are_ranked_by_plays_and_limited(self):
        result = self.get("composers")
        self.assertEqual(result["total_plays"], 6)
        self.assertEqual(
            result["items"][0], {"id": self.mozart.id, "name": "모차르트", "count": 2}
        )
        self.assertEqual(
            self.counts(result),
            {"모차르트": 2, "바흐": 1, "브람스": 1, "베토벤": 1, "작자 미상": 1},
        )
        self.assertEqual(result["labels"], [item["name"] for item in result["items"]])
        self.assertEqual(result["values"], [item["count"] for item in result["items"]])

        self.assertEqual(self.get("composers", limit=2)["labels"][0], "모차르트")
        self.assertEqual(len(self.get("composers", limit=2)["items"]), 2)
        self.assertEqual(len(self.get("composers", limit=0)["items"]), 1)
        self.assertEqual(len(self.get("composers", limit="many")["items"]), 5)

    def test_eras_use_birth_year_override_and_report_unknown_share(self):
        result = self.get("eras")
        self.assertEqual(result["total_plays"], 6)
        self.assertEqual(result["labels"], ["바로크", "고전", "낭만", "미상"])
        self.assertEqual(result["values"], [1, 3, 1, 1])
        self.assertEqual(result["items"][1], {"id": "고전", "name": "고전", "count": 3})
        self.assertEqual(result["unknown_share"], 0.1667)

    def test_genres_follow_title_and_line_up(self):
        result = self.get("genres")
        self.assertEqual(result["total_plays"], 6)
        self.assertEqual(result["labels"], GENRES)
        self.assertEqual(result["values"], [2, 1, 1, 1, 1])
        self.assertEqual(
            result["items"][0], {"id": "교향곡", "name": "교향곡", "count": 2}
        )

    def test_diversity_summary_and_weekly_timeline(self):
        result = self.get("diversity")
        self.assertEqual(result["filters"], {"scope": "all", "bucket": "week"})
        self.assertEqual(result["total_plays"], 6)
        self.assertEqual(
            result["summary"],
            {
                "distinct_works": 5,
                "distinct_composers": 5,
                "era": {
                    "labels": ["바로크", "고전", "낭만"],
                    "values": [1, 3, 1],
                    "unknown_share": 0.1667,
                    "entropy": 0.9503,
                    "evenness": 0.5904,
                },
                "genre": {
                    "labels": GENRES,
                    "values": [2, 1, 1, 1, 1],
                    "entropy": 1.5607,
                    "evenness": 0.871,
                },
            },
        )
        self.assertEqual(
            result["timeline"],
            {
                "bucket": "week",
                "labels": ["2024-02-26", "2024-03-04", "2024-03-11"],
                "plays": [1, 3, 2],
                "distinct_works": [1, 2, 2],
                "era_evenness": [0.0, 0.3955, 0.0],
                "genre_evenness": [0.0, 0.3552, 0.3869],
            },
        )

    def test_diversity_monthly_timeline_and_unknown_bucket_falls_back_to_week(self):
        timeline = self.get("diversity", bucket="month")["timeline"]
        self.assertEqual(
            timeline,
            {
                "bucket": "month",
                "labels": ["2024-02", "2024-03"],
                "plays": [1, 5],
                "distinct_works": [1, 4],
                "era_evenness": [0.0, 0.3494],
                "genre_evenness": [0.0, 0.7435],
            },
        )
        result = self.get("diversity", bucket="year")
        self.assertEqual(result["filters"]["bucket"], "week")
        self.assertEqual(result["timeline"]["bucket"], "week")

    def test_start_and_end_are_inclusive(self):
        result = self.get("summary", start="2024-03-04", end="2024-03-06")
        self.assertEqual(
            result["filters"],
            {"scope": "all", "start": "2024-03-04", "end": "2024-03-06"},
        )
        self.assertEqual(result["total_plays"], 3)
        self.assertEqual(result["date_start"], "2024-03-04")
        self.assertEqual(result["date_end"], "2024-03-06")
        self.assertEqual(self.get("summary", start="2024-03-06")["total_plays"], 3)
        self.assertEqual(self.get("summary", end="2024-02-29")["total_plays"], 1)

        composers = self.get("composers", start="2024-03-04", end="2024-03-06")
        self.assertEqual(self.counts(composers), {"모차르트": 2, "브람스": 1})
        eras = self.get("eras", start="2024-03-04", end="2024-03-06")
        self.assertEqual(self.counts(eras), {"고전": 2, "낭만": 1})
        self.assertEqual(eras["unknown_share"], 0)
        genres = self.get("genres", start="2024-03-04", end="2024-03-06")
        self.assertEqual(self.counts(genres), {"교향곡": 2, "협주곡": 1})

    def test_period_without_plays_gives_zero_counts_and_empty_charts(self):
        self.assert_no_plays(start="2025-01-01", end="2025-01-31")

    def test_semester_maps_to_its_months_and_overrides_start_and_end(self):
        result = self.get(
            "summary",
            semester_id=self.spring_2024.id,
            start="2024-02-29",
            end="2024-02-29",
        )
        self.assertEqual(result["filters"]["start"], "2024-03-01")
        self.assertEqual(result["filters"]["end"], "2024-08-31")
        self.assertEqual(result["total_plays"], 5)

        result = self.get("summary", semester_id=self.fall_2024.id)
        self.assertEqual(result["filters"]["start"], "2024-09-01")
        self.assertEqual(result["filters"]["end"], "2025-02-28")
        self.assertEqual(result["total_plays"], 0)

    def test_user_scope_counts_only_their_sessions(self):
        result = self.get("summary", user_id=self.member.id)
        self.assertEqual(
            result["filters"],
            {
                "scope": "individual",
                "user_id": self.member.id,
                "include_mentees": False,
            },
        )
        self.assertEqual(result["total_plays"], 3)
        self.assertEqual(self.get("summary", user_id=self.mentee.id)["total_plays"], 2)

        result = self.get("summary", user_id=self.mentee.id, include_mentees="true")
        self.assertTrue(result["filters"]["include_mentees"])
        self.assertEqual(result["total_plays"], 5)

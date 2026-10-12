import datetime

from django.db import connection
from django.test.utils import CaptureQueriesContext
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
ENDPOINTS = [
    "summary",
    "composers",
    "works",
    "soloists",
    "conductors",
    "orchestras",
    "timeline",
    "eras",
    "genres",
    "diversity",
]


class StatsRequests:
    def get(self, name, **params):
        response = self.client.get(reverse(f"stats-{name}"), params)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def get_error(self, name, **params):
        response = self.client.get(reverse(f"stats-{name}"), params)
        self.assertEqual(response.status_code, 400)
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
        cls.symphony = symphony

        karajan = Conductor.objects.create(name="카라얀")
        bernstein = Conductor.objects.create(name="번스타인")
        berlin = Orchestra.objects.create(name="베를린 필하모닉")
        vienna = Orchestra.objects.create(name="빈 필하모닉")
        cls.karajan, cls.bernstein = karajan, bernstein
        cls.berlin, cls.vienna = berlin, vienna

        def player(name, instrument):
            return Player.objects.create(name=name, instrument=instrument)

        # The cellist plays twice: the Bach suite and the quartet.
        cls.cellist = player("첼리스트", "첼로")

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
        play(leap_day, 1, suite, players=[cls.cellist])

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
            cls.cellist,
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

    def add_play(self, date, time=1, users=(), mentees=(), players=(), **fields):
        info = TimeInfo.objects.create(date=date, time=time, arrival_time="09:30:00")
        info.users.set(users)
        info.mentees.set(mentees)
        play = TimeMusic.objects.create(time=info, order=1, source="CD", **fields)
        play.players.set(players)
        return play

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

    def test_soloists_rank_players_by_plays_with_instrument_labels(self):
        result = self.get("soloists")
        self.assertEqual(result["total_plays"], 6)
        self.assertEqual(
            result["items"][0],
            {"id": self.cellist.id, "name": "첼리스트 (첼로)", "count": 2},
        )
        self.assertEqual(
            self.counts(result),
            {
                "첼리스트 (첼로)": 2,
                "피아니스트 (피아노)": 1,
                "제1바이올린 (바이올린)": 1,
                "제2바이올린 (바이올린)": 1,
                "비올리스트 (비올라)": 1,
            },
        )
        self.assertEqual(result["labels"], [item["name"] for item in result["items"]])
        self.assertEqual(result["values"], [item["count"] for item in result["items"]])
        self.assertEqual(self.get("soloists", limit=1)["labels"], ["첼리스트 (첼로)"])

        # A player row ": 낭독자" saves no instrument: the label is the name alone.
        reader = Player.objects.create(name="낭독자", instrument="")
        self.add_play(datetime.date(2025, 1, 6), players=[reader], music=self.symphony)
        result = self.get("soloists", start="2025-01-01")
        self.assertEqual(
            result["items"], [{"id": reader.id, "name": "낭독자", "count": 1}]
        )

    def test_conductors_orchestras_and_works_rank_by_plays(self):
        # Plays without a conductor or orchestra still count in total_plays.
        conductors = self.get("conductors")
        self.assertEqual(conductors["total_plays"], 6)
        self.assertEqual(
            conductors["items"],
            [
                {"id": self.karajan.id, "name": "카라얀", "count": 2},
                {"id": self.bernstein.id, "name": "번스타인", "count": 1},
            ],
        )
        self.assertEqual(conductors["labels"], ["카라얀", "번스타인"])
        self.assertEqual(conductors["values"], [2, 1])

        orchestras = self.get("orchestras")
        self.assertEqual(orchestras["total_plays"], 6)
        self.assertEqual(
            orchestras["items"],
            [
                {"id": self.berlin.id, "name": "베를린 필하모닉", "count": 2},
                {"id": self.vienna.id, "name": "빈 필하모닉", "count": 1},
            ],
        )
        self.assertEqual(orchestras["labels"], ["베를린 필하모닉", "빈 필하모닉"])
        self.assertEqual(orchestras["values"], [2, 1])

        works = self.get("works")
        self.assertEqual(works["total_plays"], 6)
        self.assertEqual(
            works["items"][0],
            {"id": self.symphony.id, "name": "모차르트 - 교향곡 제40번", "count": 2},
        )
        self.assertEqual(
            self.counts(works),
            {
                "모차르트 - 교향곡 제40번": 2,
                "바흐 - 무반주 첼로 모음곡 제1번": 1,
                "브람스 - 피아노 협주곡 제2번": 1,
                "베토벤 - 현악 사중주 제14번": 1,
                "작자 미상 - 그레고리오 성가": 1,
            },
        )
        self.assertEqual(works["labels"], [item["name"] for item in works["items"]])
        self.assertEqual(works["values"], [item["count"] for item in works["items"]])

        for name, top in (
            ("conductors", "카라얀"),
            ("orchestras", "베를린 필하모닉"),
            ("works", "모차르트 - 교향곡 제40번"),
        ):
            with self.subTest(endpoint=name):
                self.assertEqual(self.get(name, limit=1)["labels"], [top])

        # From 3/5 only the 3/6 symphony has a conductor and an orchestra.
        later = {"start": "2024-03-05"}
        self.assertEqual(self.counts(self.get("conductors", **later)), {"번스타인": 1})
        self.assertEqual(
            self.counts(self.get("orchestras", **later)), {"빈 필하모닉": 1}
        )

    def test_eras_use_birth_year_override_and_report_unknown_share(self):
        result = self.get("eras")
        self.assertEqual(result["total_plays"], 6)
        self.assertEqual(result["labels"], ["바로크", "고전", "낭만", "미상"])
        self.assertEqual(result["values"], [1, 3, 1, 1])
        self.assertEqual(result["items"][1], {"id": "고전", "name": "고전", "count": 3})
        self.assertEqual(result["unknown_share"], 0.1667)

    def test_an_override_that_is_not_an_era_falls_back_to_birth_year(self):
        # era_override is free text in the admin. A label the charts do not
        # know dropped the play from them, though total_plays still counted it.
        modern = Composer.objects.create(
            name="히나스테라", birth_year=1916, era_override="20세기"
        )
        undated = Composer.objects.create(name="무명", era_override="르네상스")
        # A known label still wins over the birth year (1872 is 낭만).
        scriabin = Composer.objects.create(
            name="스크랴빈", birth_year=1872, era_override="근현대"
        )
        week = [datetime.date(2024, 4, 1) + datetime.timedelta(days=n) for n in (0, 1)]
        self.add_play(week[0], music=Music.objects.create(composer=modern, title="A"))
        self.add_play(week[1], music=Music.objects.create(composer=undated, title="B"))
        self.add_play(week[1], time=2, music=self.symphony)
        self.add_play(
            week[1], time=3, music=Music.objects.create(composer=scriabin, title="C")
        )
        params = {"start": "2024-04-01", "end": "2024-04-07"}

        eras = self.get("eras", **params)
        self.assertEqual(eras["total_plays"], 4)
        self.assertEqual(self.counts(eras), {"고전": 1, "근현대": 2, "미상": 1})
        self.assertEqual(eras["unknown_share"], 0.25)

        diversity = self.get("diversity", **params)
        self.assertEqual(
            diversity["summary"]["era"],
            {
                "labels": ["고전", "근현대"],
                "values": [1, 2],
                "unknown_share": 0.25,
                "entropy": 0.6365,
                "evenness": 0.3955,
            },
        )
        self.assertEqual(diversity["timeline"]["era_evenness"], [0.3955])

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

    def test_timeline_buckets_by_month_week_or_semester(self):
        self.assertEqual(
            self.get("timeline"),
            {
                "filters": {"scope": "all", "bucket": "month"},
                "total_plays": 6,
                "labels": ["2024-02", "2024-03"],
                "values": [1, 5],
                "items": [],
            },
        )

        week = self.get("timeline", bucket="week")
        self.assertEqual(week["filters"], {"scope": "all", "bucket": "week"})
        self.assertEqual(week["labels"], ["2024-02-26", "2024-03-04", "2024-03-11"])
        self.assertEqual(week["values"], [1, 3, 2])

        # 2/29 falls in 2023's 2nd semester (September to February).
        semester = self.get("timeline", bucket="semester")
        self.assertEqual(semester["filters"], {"scope": "all", "bucket": "semester"})
        self.assertEqual(semester["labels"], ["2023-2", "2024-1"])
        self.assertEqual(semester["values"], [1, 5])

        # Any other bucket is by month, and says so.
        for bucket in ("year", "", "WEEK"):
            with self.subTest(bucket=bucket):
                other = self.get("timeline", bucket=bucket)
                self.assertEqual(other["filters"], {"scope": "all", "bucket": "month"})
                self.assertEqual(other["labels"], ["2024-02", "2024-03"])
                self.assertEqual(other["values"], [1, 5])

    def test_timeline_semesters_run_september_to_february(self):
        for date in ("2024-08-31", "2024-09-02", "2025-01-02"):
            self.add_play(datetime.date.fromisoformat(date), music=self.symphony)

        result = self.get("timeline", bucket="semester", start="2024-03-01")
        self.assertEqual(result["labels"], ["2024-1", "2024-2"])
        self.assertEqual(result["values"], [6, 2])

        # The bucket agrees with the semester filter's dates.
        result = self.get("timeline", bucket="semester", semester_id=self.fall_2024.id)
        self.assertEqual(result["labels"], ["2024-2"])
        self.assertEqual(result["values"], [2])

        # 2025-01-02 is a Thursday: its week starts on Monday 2024-12-30.
        result = self.get("timeline", bucket="week", start="2024-12-01")
        self.assertEqual(result["labels"], ["2024-12-30"])
        self.assertEqual(result["values"], [1])

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
        self.assertEqual(result["filters"]["semester_id"], str(self.spring_2024.id))
        self.assertEqual(result["filters"]["start"], "2024-03-01")
        self.assertEqual(result["filters"]["end"], "2024-08-31")
        self.assertEqual(result["total_plays"], 5)

        result = self.get("summary", semester_id=self.fall_2024.id)
        self.assertEqual(result["filters"]["start"], "2024-09-01")
        self.assertEqual(result["filters"]["end"], "2025-02-28")
        self.assertEqual(result["total_plays"], 0)

    def test_malformed_filters_get_400_naming_the_parameter(self):
        malformed = [
            ("start", "garbage"),
            ("start", "2024-13-01"),
            ("end", "2024-02-30"),
            ("semester_id", "abc"),
            ("semester_id", "9" * 20),
            ("user_id", "abc"),
            ("user_id", "1.5"),
            ("user_id", "-" + "9" * 20),
        ]
        for name in ENDPOINTS:
            for param, value in malformed:
                with self.subTest(endpoint=name, param=param, value=value):
                    error = self.get_error(name, **{param: value})
                    self.assertEqual(list(error), [param])
                    self.assertTrue(error[param])
        self.assertIn("YYYY-MM-DD", self.get_error("summary", start="3/4")["start"][0])

    def test_blank_and_unpadded_filters_still_work(self):
        result = self.get("summary", start="", end="", semester_id="", user_id="")
        self.assertEqual(result["filters"], {"scope": "all"})
        self.assertEqual(result["total_plays"], 6)
        result = self.get("summary", start="2024-3-4", end="2024-3-6")
        self.assertEqual(result["total_plays"], 3)

    def test_second_semester_runs_to_february_29_in_leap_years(self):
        result = self.get("summary", semester_id=self.fall_2023.id)
        self.assertEqual(result["filters"]["start"], "2023-09-01")
        self.assertEqual(result["filters"]["end"], "2024-02-29")
        self.assertEqual(result["total_plays"], 1)
        self.assertEqual(result["date_start"], "2024-02-29")

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

    def test_including_mentee_sessions_counts_each_play_once(self):
        # The 3/4 session has two members and two mentees, so the OR across both
        # M2M joins returns each of its plays on more than one row.
        params = {"user_id": self.mentee.id, "include_mentees": "true"}
        expected = {
            "composers": {"모차르트": 2, "브람스": 1, "베토벤": 1, "작자 미상": 1},
            "works": {
                "모차르트 - 교향곡 제40번": 2,
                "브람스 - 피아노 협주곡 제2번": 1,
                "베토벤 - 현악 사중주 제14번": 1,
                "작자 미상 - 그레고리오 성가": 1,
            },
            "soloists": {
                "피아니스트 (피아노)": 1,
                "제1바이올린 (바이올린)": 1,
                "제2바이올린 (바이올린)": 1,
                "비올리스트 (비올라)": 1,
                "첼리스트 (첼로)": 1,
            },
            "conductors": {"카라얀": 2, "번스타인": 1},
            "orchestras": {"베를린 필하모닉": 2, "빈 필하모닉": 1},
            "timeline": {"2024-03": 5},
            "eras": {"고전": 3, "낭만": 1, "미상": 1},
            "genres": {"교향곡": 2, "협주곡": 1, "실내악곡": 1, "기타": 1},
        }
        for name, counts in expected.items():
            with self.subTest(endpoint=name):
                result = self.get(name, **params)
                self.assertEqual(result["total_plays"], 5)
                self.assertEqual(self.counts(result), counts)
        self.assertEqual(self.get("eras", **params)["unknown_share"], 0.2)
        self.assertEqual(self.get("diversity", **params)["total_plays"], 5)

    def test_query_count_does_not_grow_with_plays(self):
        scopes = [{}, {"user_id": self.mentee.id, "include_mentees": "true"}]

        def query_counts():
            counts = {}
            for params in scopes:
                for name in ENDPOINTS:
                    with CaptureQueriesContext(connection) as queries:
                        self.get(name, **params)
                    counts[name, tuple(params)] = len(queries)
            return counts

        before = query_counts()
        brahms = Composer.objects.get(name="브람스")
        for day in range(20):
            self.add_play(
                datetime.date(2024, 3, 13) + datetime.timedelta(days=day),
                users=[self.member, self.mentee],
                mentees=[self.mentee],
                players=[
                    Player.objects.create(name=f"연주자 {day}-{n}", instrument="피아노")
                    for n in range(2)
                ],
                music=Music.objects.create(composer=brahms, title=f"소품 {day}"),
                conductor=Conductor.objects.create(name=f"지휘자 {day}"),
                orchestra=Orchestra.objects.create(name=f"오케스트라 {day}"),
            )
        self.assertEqual(self.get("summary")["total_plays"], 26)
        self.assertEqual(query_counts(), before)

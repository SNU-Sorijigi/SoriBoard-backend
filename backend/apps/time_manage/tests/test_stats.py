import datetime
from unittest import mock

from django.db import connection
from django.db.models import Model
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
    "firsts",
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
        for key in (
            "total_plays",
            "sessions",
            "requested",
            "composers",
            "works",
            "conductors",
            "orchestras",
        ):
            self.assertEqual(summary[key], 0)
        self.assertIsNone(summary["date_start"])
        self.assertIsNone(summary["date_end"])

        for name in ("composers", "works", "eras", "genres", "firsts"):
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

    def test_no_plays_skip_the_players_query_of_genres_and_diversity(self):
        with self.assertNumQueries(2):
            self.get("genres")
        with self.assertNumQueries(1):
            self.get("diversity")

    def test_no_plays_give_no_firsts_of_either_kind(self):
        for kind in ("composer", "work"):
            with self.subTest(kind=kind):
                with self.assertNumQueries(2):
                    result = self.get("firsts", kind=kind)
                self.assertEqual(
                    result,
                    {
                        "filters": {"scope": "all", "kind": kind},
                        "total_plays": 0,
                        "labels": [],
                        "values": [],
                        "items": [],
                    },
                )


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
                "sessions": 4,
                "requested": 0,
                "composers": 5,
                "works": 5,
                "conductors": 2,
                "orchestras": 2,
                "date_start": "2024-02-29",
                "date_end": "2024-03-12",
            },
        )

    def test_summary_counts_sessions_and_requests_in_the_filter(self):
        # 신청곡: the 3/4 concerto and the 3/12 chant.
        TimeMusic.objects.filter(
            music__title__in=["피아노 협주곡 제2번", "그레고리오 성가"]
        ).update(is_requested=True)
        cases = [
            ({}, 6, 4, 2),
            ({"start": "2024-03-05"}, 3, 2, 1),
            ({"semester_id": self.fall_2023.id}, 1, 1, 0),
            ({"user_id": self.member.id}, 3, 2, 1),
            ({"user_id": self.mentee.id}, 2, 1, 1),
            ({"composer_id": self.mozart.id}, 2, 2, 0),
            ({"conductor_id": self.karajan.id}, 2, 1, 1),
            ({"player_id": self.cellist.id}, 2, 2, 0),
        ]
        for params, plays, sessions, requested in cases:
            with self.subTest(params=params):
                result = self.get("summary", **params)
                self.assertEqual(result["total_plays"], plays)
                self.assertEqual(result["sessions"], sessions)
                self.assertEqual(result["requested"], requested)

    def test_summary_counts_a_session_and_a_request_once_with_mentee_sessions(self):
        # The 3/4 session has two members and two mentees, so the OR across both
        # M2M joins returns each of its plays on more than one row.
        TimeMusic.objects.filter(time__date=datetime.date(2024, 3, 4)).update(
            is_requested=True
        )
        params = {"user_id": self.mentee.id, "include_mentees": "true"}
        result = self.get("summary", **params)
        self.assertEqual(result["total_plays"], 5)
        self.assertEqual(result["sessions"], 3)
        self.assertEqual(result["requested"], 2)

        params["player_id"] = Player.objects.get(name="피아니스트").id
        result = self.get("summary", **params)
        self.assertEqual(result["total_plays"], 1)
        self.assertEqual(result["sessions"], 1)
        self.assertEqual(result["requested"], 1)

    def test_a_session_without_plays_is_not_counted(self):
        TimeInfo.objects.create(
            date=datetime.date(2024, 3, 7), time=1, arrival_time="09:30:00"
        )
        self.assertEqual(self.get("summary")["sessions"], 4)

    def test_summary_takes_two_queries(self):
        params = {"user_id": self.mentee.id, "include_mentees": "true"}
        for scope in ({}, params):
            with self.subTest(params=scope):
                with self.assertNumQueries(2):
                    self.get("summary", **scope)

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
            {
                "id": self.symphony.id,
                "name": "모차르트 - 교향곡 제40번",
                "count": 2,
                "composer_id": self.mozart.id,
                "first_played": "2024-03-04",
                "last_played": "2024-03-06",
            },
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

    RANKINGS = ["composers", "works", "soloists", "conductors", "orchestras"]

    def ranked(self, name, **params):
        result = self.get(name, **params)
        items = result["items"]
        self.assertEqual(
            items,
            sorted(items, key=lambda item: (-item["count"], item["name"], item["id"])),
        )
        return [item["name"] for item in items]

    def test_ties_are_ranked_by_name(self):
        # Created 바흐, 브람스, 베토벤, 작자 미상: ties are not in id order.
        self.assertEqual(
            self.ranked("composers"),
            ["모차르트", "바흐", "베토벤", "브람스", "작자 미상"],
        )
        self.assertEqual(
            self.ranked("works"),
            [
                "모차르트 - 교향곡 제40번",
                "바흐 - 무반주 첼로 모음곡 제1번",
                "베토벤 - 현악 사중주 제14번",
                "브람스 - 피아노 협주곡 제2번",
                "작자 미상 - 그레고리오 성가",
            ],
        )
        self.assertEqual(
            self.ranked("soloists"),
            [
                "첼리스트 (첼로)",
                "비올리스트 (비올라)",
                "제1바이올린 (바이올린)",
                "제2바이올린 (바이올린)",
                "피아니스트 (피아노)",
            ],
        )
        for name in self.RANKINGS:
            with self.subTest(endpoint=name):
                self.ranked(name, start="2024-03-01")

    def test_ties_with_the_same_name_are_ranked_by_id_and_limit_cuts_after(self):
        chung = Conductor.objects.create(name="정명훈")
        abbado = Conductor.objects.create(name="아바도")
        twin = Conductor.objects.create(name="아바도")
        cologne = Orchestra.objects.create(name="쾰른 방송 교향악단")
        london = Orchestra.objects.create(name="런던 심포니")
        london_twin = Orchestra.objects.create(name="런던 심포니")
        for conductor, orchestra in (
            (chung, cologne),
            (twin, london_twin),
            (abbado, london),
        ):
            self.add_play(
                datetime.date(2025, 1, 6),
                time=conductor.id,
                music=self.symphony,
                conductor=conductor,
                orchestra=orchestra,
            )

        later = {"start": "2025-01-01"}
        conductors = self.get("conductors", **later)
        self.assertEqual(
            [item["id"] for item in conductors["items"]], [abbado.id, twin.id, chung.id]
        )
        self.assertEqual(conductors["labels"], ["아바도", "아바도", "정명훈"])
        orchestras = self.get("orchestras", **later)
        self.assertEqual(
            [item["id"] for item in orchestras["items"]],
            [london.id, london_twin.id, cologne.id],
        )
        for name, first_two in (
            ("conductors", [abbado.id, twin.id]),
            ("orchestras", [london.id, london_twin.id]),
        ):
            with self.subTest(endpoint=name):
                top = self.get(name, limit=2, **later)
                self.assertEqual([item["id"] for item in top["items"]], first_two)
        # 카라얀 (2) still leads; the tied ones follow by name.
        self.assertEqual(
            self.get("conductors", limit=3)["labels"], ["카라얀", "번스타인", "아바도"]
        )
        for name in self.RANKINGS:
            with self.subTest(endpoint=name):
                self.ranked(name)

    def test_ties_are_ranked_by_the_name_the_answer_shows(self):
        # By label, not by its parts: "슈트라우스 (요한) - …" sorts before
        # "슈트라우스 - …" ("(" < "-"), and a work whose composer has no name
        # is labelled with its title alone.
        strauss = Composer.objects.create(name="슈트라우스")
        johann = Composer.objects.create(name="슈트라우스 (요한)")
        unnamed = Composer.objects.create(name="")
        waltz = Music.objects.create(composer=strauss, title="왈츠")
        march = Music.objects.create(composer=johann, title="라데츠키 행진곡")
        hymn = Music.objects.create(composer=unnamed, title="슈트라우스 송가")
        # "합창단" < "합창단 & 독창자" < "합창단 (합창)" ("&" < "(").
        choir = Player.objects.create(name="합창단", instrument="합창")
        duo = Player.objects.create(name="합창단 & 독창자", instrument="")
        bare = Player.objects.create(name="합창단", instrument="")
        for time, music in enumerate((waltz, march, hymn), start=1):
            self.add_play(
                datetime.date(2025, 1, 6),
                time=time,
                music=music,
                players=[choir, duo, bare],
            )

        later = {"start": "2025-01-01"}
        self.assertEqual(
            self.ranked("works", **later),
            [
                "슈트라우스 (요한) - 라데츠키 행진곡",
                "슈트라우스 - 왈츠",
                "슈트라우스 송가",
            ],
        )
        self.assertEqual(
            [item["id"] for item in self.get("works", **later)["items"]],
            [march.id, waltz.id, hymn.id],
        )
        self.assertEqual(
            self.ranked("soloists", **later),
            ["합창단", "합창단 & 독창자", "합창단 (합창)"],
        )
        self.assertEqual(
            [item["id"] for item in self.get("soloists", **later)["items"]],
            [bare.id, duo.id, choir.id],
        )
        self.assertEqual(
            self.ranked("composers", **later), ["", "슈트라우스", "슈트라우스 (요한)"]
        )

    def test_works_name_their_composer(self):
        composer_ids = {
            item["name"]: item["composer_id"] for item in self.get("works")["items"]
        }
        self.assertEqual(
            composer_ids,
            {
                f"{music.composer.name} - {music.title}": music.composer_id
                for music in Music.objects.select_related("composer")
            },
        )

    def test_works_first_and_last_played_are_all_time_not_the_filtered_range(self):
        self.add_play(datetime.date(2025, 5, 2), music=self.symphony)
        dates = {"first_played": "2024-03-04", "last_played": "2025-05-02"}
        # Each range holds one of the symphony's three plays.
        for params in [
            {"end": "2024-03-04"},
            {"start": "2024-03-05", "end": "2024-03-06"},
            {"start": "2025-01-01"},
            {"semester_id": self.spring_2024.id, "user_id": self.member.id},
        ]:
            with self.subTest(params=params):
                items = self.get("works", **params)["items"]
                item = next(i for i in items if i["id"] == self.symphony.id)
                self.assertEqual(item["count"], 1)
                self.assertEqual(
                    {k: item[k] for k in ("first_played", "last_played")}, dates
                )

    def test_a_work_played_once_was_first_and_last_played_that_day(self):
        suite = self.get("works", player_id=self.cellist.id, end="2024-03-01")
        self.assertEqual(
            suite["items"][0],
            {
                "id": Music.objects.get(title="무반주 첼로 모음곡 제1번").id,
                "name": "바흐 - 무반주 첼로 모음곡 제1번",
                "count": 1,
                "composer_id": Composer.objects.get(name="바흐").id,
                "first_played": "2024-02-29",
                "last_played": "2024-02-29",
            },
        )

    def test_works_take_three_queries_and_two_when_empty(self):
        # The total, the ranking, and the first and last play of the ranked works.
        for params in [{}, {"user_id": self.mentee.id, "include_mentees": "true"}]:
            with self.subTest(params=params), self.assertNumQueries(3):
                self.get("works", **params)
        with self.assertNumQueries(2):
            self.assertEqual(self.get("works", start="2030-01-01")["items"], [])

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

    # genres and diversity classify every play with its players' instruments.
    def add_april_plays(self):
        """Six plays over two April weeks that reach each genre rule.

        Every session has the mentee as member and mentee, so the
        include_mentees join returns each play on two rows.
        """
        brahms = Composer.objects.get(name="브람스")
        bach = Composer.objects.get(name="바흐")
        pianists = [
            Player.objects.create(name=f"피아니스트 {n}", instrument="피아노")
            for n in (1, 2)
        ]
        cases = [
            # No work, an orchestra and a singer: 기타 (vocal), 미상.
            (
                1,
                1,
                {
                    "orchestra": self.berlin,
                    "players": [
                        Player.objects.create(name="가수", instrument="소프라노")
                    ],
                },
            ),
            # No work, nothing else: 기타, 미상.
            (1, 2, {}),
            # 협주곡 by title, two soloists, 낭만.
            (
                2,
                1,
                {
                    "music": Music.objects.get(title="피아노 협주곡 제2번"),
                    "orchestra": self.vienna,
                    "players": pianists,
                },
            ),
            # An orchestra without soloists: 관현악곡, 고전.
            (
                8,
                1,
                {
                    "music": Music.objects.create(
                        composer=self.mozart, title="세레나데"
                    ),
                    "orchestra": self.berlin,
                },
            ),
            # One player: 독주곡, 바로크.
            (
                8,
                2,
                {
                    "music": Music.objects.create(composer=bach, title="파르티타"),
                    "players": [self.cellist],
                },
            ),
            # 교향곡 by title, though it has an orchestra and soloists.
            (
                9,
                1,
                {"music": self.symphony, "orchestra": self.berlin, "players": pianists},
            ),
        ]
        for day, time, fields in cases:
            self.add_play(
                datetime.date(2024, 4, day),
                time=time,
                users=[self.member, self.mentee],
                mentees=[self.mentee],
                **fields,
            )
        return {"start": "2024-04-01", "end": "2024-04-14"}

    def test_genres_and_diversity_classify_plays_with_and_without_works_once(self):
        april = self.add_april_plays()
        mentee = {"user_id": self.mentee.id, "include_mentees": "true"}
        for params in (april, {**april, **mentee}):
            with self.subTest(params=params):
                genres = self.get("genres", **params)
                self.assertEqual(genres["total_plays"], 6)
                self.assertEqual(
                    self.counts(genres),
                    {"교향곡": 1, "협주곡": 1, "관현악곡": 1, "독주곡": 1, "기타": 2},
                )
                self.assertEqual(
                    genres["labels"], ["교향곡", "협주곡", "관현악곡", "독주곡", "기타"]
                )

                diversity = self.get("diversity", **params)
                self.assertEqual(diversity["total_plays"], 6)
                self.assertEqual(
                    diversity["summary"],
                    {
                        "distinct_works": 4,
                        "distinct_composers": 3,
                        "era": {
                            "labels": ["바로크", "고전", "낭만"],
                            "values": [1, 2, 1],
                            "unknown_share": 0.3333,
                            "entropy": 1.0397,
                            "evenness": 0.646,
                        },
                        "genre": {
                            "labels": [
                                "교향곡",
                                "협주곡",
                                "관현악곡",
                                "독주곡",
                                "기타",
                            ],
                            "values": [1, 1, 1, 1, 2],
                            "entropy": 1.5607,
                            "evenness": 0.871,
                        },
                    },
                )
                self.assertEqual(
                    diversity["timeline"],
                    {
                        "bucket": "week",
                        "labels": ["2024-04-01", "2024-04-08"],
                        "plays": [3, 3],
                        "distinct_works": [1, 3],
                        "era_evenness": [0.0, 0.3955],
                        "genre_evenness": [0.3552, 0.6131],
                    },
                )

    def test_genres_take_three_queries_and_diversity_two(self):
        april = self.add_april_plays()
        mentee = {"user_id": self.mentee.id, "include_mentees": "true"}
        for params in ({}, april, {**april, **mentee}):
            with self.subTest(params=params):
                with self.assertNumQueries(3):
                    self.get("genres", **params)
                with self.assertNumQueries(2):
                    self.get("diversity", **params)

    def test_genres_and_diversity_build_no_model_instances(self):
        # Loading every play and its players as model instances took about
        # 0.5 s (genres) and 0.8 s (diversity) on 5,000 plays.
        self.add_april_plays()
        built = []
        from_db = Model.from_db.__func__

        def counting_from_db(cls, db, field_names, values):
            built.append(cls.__name__)
            return from_db(cls, db, field_names, values)

        with mock.patch.object(Model, "from_db", classmethod(counting_from_db)):
            for name in ("genres", "diversity"):
                for bucket in ("week", "month"):
                    self.assertEqual(self.get(name, bucket=bucket)["total_plays"], 12)
        self.assertEqual(built, [])

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

    def test_timeline_lists_empty_weeks_and_months_with_zero(self):
        self.add_play(datetime.date(2024, 5, 15), music=self.symphony)

        with self.assertNumQueries(2):
            month = self.get("timeline")
        self.assertEqual(month["labels"], ["2024-02", "2024-03", "2024-04", "2024-05"])
        self.assertEqual(month["values"], [1, 5, 0, 1])
        self.assertEqual(month["total_plays"], 7)

        week = self.get("timeline", bucket="week")
        self.assertEqual(
            week["labels"],
            [
                "2024-02-26",
                "2024-03-04",
                "2024-03-11",
                "2024-03-18",
                "2024-03-25",
                "2024-04-01",
                "2024-04-08",
                "2024-04-15",
                "2024-04-22",
                "2024-04-29",
                "2024-05-06",
                "2024-05-13",
            ],
        )
        self.assertEqual(week["values"], [1, 3, 2, 0, 0, 0, 0, 0, 0, 0, 0, 1])

    def test_timeline_fills_months_across_the_new_year(self):
        for date in ("2024-11-29", "2025-02-03"):
            self.add_play(datetime.date.fromisoformat(date), music=self.symphony)

        result = self.get("timeline", start="2024-06-01")
        self.assertEqual(result["labels"], ["2024-11", "2024-12", "2025-01", "2025-02"])
        self.assertEqual(result["values"], [1, 0, 0, 1])

        # 2024-11-29 is a Friday (week of 11/25); 2025-02-03 is a Monday.
        result = self.get("timeline", bucket="week", start="2024-06-01")
        self.assertEqual(len(result["labels"]), 11)
        self.assertEqual(result["labels"][0], "2024-11-25")
        self.assertEqual(result["labels"][4], "2024-12-23")
        self.assertEqual(result["labels"][5], "2024-12-30")
        self.assertEqual(result["labels"][-1], "2025-02-03")
        self.assertEqual(result["values"], [1] + [0] * 9 + [1])

    def test_timeline_fills_only_between_the_first_and_last_play(self):
        # The filter's own start and end add no empty buckets around the plays.
        params = {"start": "2023-01-01", "end": "2025-12-31"}
        result = self.get("timeline", **params)
        self.assertEqual(result["labels"], ["2024-02", "2024-03"])
        self.assertEqual(result["values"], [1, 5])

        result = self.get("timeline", bucket="week", music_id=self.symphony.id)
        self.assertEqual(result["labels"], ["2024-03-04"])
        self.assertEqual(result["values"], [2])

        empty = self.get("timeline", start="2030-01-01")
        self.assertEqual((empty["labels"], empty["values"]), ([], []))

    def test_timeline_ends_at_the_last_play_even_in_the_year_9999(self):
        self.add_play(datetime.date(9999, 12, 31), music=self.symphony)
        for bucket, label in (("week", "9999-12-27"), ("month", "9999-12")):
            with self.subTest(bucket=bucket):
                result = self.get("timeline", bucket=bucket, start="9999-01-01")
                self.assertEqual(result["labels"], [label])
                self.assertEqual(result["values"], [1])

    def test_timeline_semesters_still_skip_a_semester_without_plays(self):
        # Zero-filling covers weeks and months only.
        self.add_play(datetime.date(2025, 3, 10), music=self.symphony)
        result = self.get("timeline", bucket="semester")
        self.assertEqual(result["labels"], ["2023-2", "2024-1", "2025-1"])
        self.assertEqual(result["values"], [1, 5, 1])

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

    # composer_id, music_id, player_id, conductor_id and orchestra_id narrow the
    # plays of every endpoint, for the drill-down from a chart's items.
    def id_filters(self):
        return [
            ("composer_id", self.mozart.id, 2),
            ("music_id", self.symphony.id, 2),
            ("player_id", self.cellist.id, 2),
            ("conductor_id", self.karajan.id, 2),
            ("orchestra_id", self.vienna.id, 1),
        ]

    def test_each_id_filter_narrows_every_endpoint_and_is_echoed(self):
        for param, value, plays in self.id_filters():
            for name in ENDPOINTS:
                with self.subTest(param=param, endpoint=name):
                    result = self.get(name, **{param: value})
                    self.assertEqual(result["total_plays"], plays)
                    self.assertEqual(result["filters"][param], value)
                    self.assertEqual(result["filters"]["scope"], "all")

    def test_id_filters_narrow_the_counts(self):
        mozart = {"composer_id": self.mozart.id}
        summary = self.get("summary", **mozart)
        self.assertEqual(
            summary,
            {
                "filters": {"scope": "all", "composer_id": self.mozart.id},
                "total_plays": 2,
                "sessions": 2,
                "requested": 0,
                "composers": 1,
                "works": 1,
                "conductors": 2,
                "orchestras": 2,
                "date_start": "2024-03-04",
                "date_end": "2024-03-06",
            },
        )
        self.assertEqual(
            self.counts(self.get("conductors", **mozart)), {"카라얀": 1, "번스타인": 1}
        )

        symphony = {"music_id": self.symphony.id}
        self.assertEqual(self.counts(self.get("timeline", **symphony)), {"2024-03": 2})
        self.assertEqual(self.counts(self.get("eras", **symphony)), {"고전": 2})

        karajan = {"conductor_id": self.karajan.id}
        self.assertEqual(
            self.counts(self.get("works", **karajan)),
            {"모차르트 - 교향곡 제40번": 1, "브람스 - 피아노 협주곡 제2번": 1},
        )
        self.assertEqual(
            self.counts(self.get("orchestras", **karajan)), {"베를린 필하모닉": 2}
        )

        vienna = {"orchestra_id": self.vienna.id}
        self.assertEqual(self.counts(self.get("conductors", **vienna)), {"번스타인": 1})

        cellist = {"player_id": self.cellist.id}
        self.assertEqual(
            self.counts(self.get("composers", **cellist)), {"바흐": 1, "베토벤": 1}
        )
        self.assertEqual(
            self.counts(self.get("genres", **cellist)), {"실내악곡": 1, "독주곡": 1}
        )
        # The soloists of those plays: the cellist and the quartet's other players.
        self.assertEqual(
            self.counts(self.get("soloists", **cellist)),
            {
                "첼리스트 (첼로)": 2,
                "제1바이올린 (바이올린)": 1,
                "제2바이올린 (바이올린)": 1,
                "비올리스트 (비올라)": 1,
            },
        )
        diversity = self.get("diversity", **cellist)
        self.assertEqual(diversity["summary"]["distinct_works"], 2)
        self.assertEqual(diversity["timeline"]["labels"], ["2024-02-26", "2024-03-11"])

    def test_player_filter_counts_a_play_once_with_mentee_sessions(self):
        pianist = Player.objects.get(name="피아니스트")
        # The 3/4 session has two members and two mentees: the include_mentees
        # OR join returns its concerto on four rows.
        params = {
            "user_id": self.mentee.id,
            "include_mentees": "true",
            "player_id": pianist.id,
        }
        for name in ENDPOINTS:
            with self.subTest(endpoint=name):
                result = self.get(name, **params)
                self.assertEqual(result["total_plays"], 1)
                self.assertEqual(result["filters"]["scope"], "individual")
                self.assertEqual(result["filters"]["player_id"], pianist.id)
        summary = self.get("summary", **params)
        for key in ("composers", "works", "conductors", "orchestras"):
            self.assertEqual(summary[key], 1)
        self.assertEqual(
            self.get("soloists", **params)["items"],
            [{"id": pianist.id, "name": "피아니스트 (피아노)", "count": 1}],
        )
        self.assertEqual(self.counts(self.get("timeline", **params)), {"2024-03": 1})
        self.assertEqual(self.counts(self.get("genres", **params)), {"협주곡": 1})

    def test_id_filters_combine_with_each_other_and_the_period(self):
        result = self.get(
            "summary", composer_id=self.mozart.id, conductor_id=self.karajan.id
        )
        self.assertEqual(
            result["filters"],
            {
                "scope": "all",
                "composer_id": self.mozart.id,
                "conductor_id": self.karajan.id,
            },
        )
        self.assertEqual(result["total_plays"], 1)
        self.assertEqual(result["date_start"], "2024-03-04")

        result = self.get("summary", composer_id=self.mozart.id, start="2024-03-05")
        self.assertEqual(result["total_plays"], 1)
        self.assertEqual(result["date_start"], "2024-03-06")

        result = self.get(
            "summary", player_id=self.cellist.id, semester_id=self.spring_2024.id
        )
        self.assertEqual(result["total_plays"], 1)
        self.assertEqual(result["date_start"], "2024-03-12")

        bach = Composer.objects.get(name="바흐")
        result = self.get("summary", composer_id=bach.id, conductor_id=self.karajan.id)
        self.assertEqual(result["total_plays"], 0)

    def test_unknown_ids_give_empty_stats(self):
        for param in ("composer_id", "music_id", "player_id"):
            with self.subTest(param=param):
                self.assert_no_plays(**{param: 999999})
        for param in ("conductor_id", "orchestra_id"):
            with self.subTest(param=param):
                self.assertEqual(self.get("summary", **{param: 0})["total_plays"], 0)

    def test_malformed_id_filters_get_400_naming_the_parameter(self):
        params = [p for p, _, _ in self.id_filters()]
        for name in ENDPOINTS:
            for param in params:
                for value in ("abc", "1.5", "9" * 20, "-" + "9" * 20):
                    with self.subTest(endpoint=name, param=param, value=value):
                        error = self.get_error(name, **{param: value})
                        self.assertEqual(list(error), [param])
                        self.assertTrue(error[param])

    def test_blank_id_filters_are_ignored(self):
        params = {p: "" for p, _, _ in self.id_filters()}
        result = self.get("summary", **params)
        self.assertEqual(result["filters"], {"scope": "all"})
        self.assertEqual(result["total_plays"], 6)

    def test_id_filters_add_no_queries(self):
        # A play that matches all five filters.
        self.add_play(
            datetime.date(2024, 3, 13),
            users=[self.member],
            players=[self.cellist, Player.objects.get(name="피아니스트")],
            music=self.symphony,
            conductor=self.karajan,
            orchestra=self.vienna,
        )
        all_ids = {p: v for p, v, _ in self.id_filters()}
        scopes = [
            all_ids,
            {**all_ids, "user_id": self.member.id, "include_mentees": "true"},
        ]

        def query_counts(params):
            counts = {}
            for name in ENDPOINTS:
                with CaptureQueriesContext(connection) as queries:
                    result = self.get(name, **params)
                counts[name] = len(queries), result["total_plays"]
            return counts

        unfiltered = {name: n for name, (n, _) in query_counts({}).items()}
        for params in scopes:
            with self.subTest(params=params):
                counts = query_counts(params)
                self.assertEqual({k: n for k, (n, _) in counts.items()}, unfiltered)
                self.assertEqual({t for _, t in counts.values()}, {1})

        # The counts and the date span, as without filters.
        with self.assertNumQueries(2):
            self.get("summary", **all_ids)

    # stats/firsts: the composers or works first played in the club in the
    # filtered range, for the 학기 결산.
    def test_firsts_list_composers_by_first_play_then_name(self):
        result = self.get("firsts")
        self.assertEqual(result["filters"], {"scope": "all", "kind": "composer"})
        self.assertEqual(result["total_plays"], 6)
        ids = {c.name: c.id for c in Composer.objects.all()}
        self.assertEqual(
            result["items"],
            [
                {
                    "id": ids["바흐"],
                    "name": "바흐",
                    "count": 1,
                    "first_played": "2024-02-29",
                },
                {
                    "id": ids["모차르트"],
                    "name": "모차르트",
                    "count": 2,
                    "first_played": "2024-03-04",
                },
                {
                    "id": ids["브람스"],
                    "name": "브람스",
                    "count": 1,
                    "first_played": "2024-03-04",
                },
                {
                    "id": ids["베토벤"],
                    "name": "베토벤",
                    "count": 1,
                    "first_played": "2024-03-12",
                },
                {
                    "id": ids["작자 미상"],
                    "name": "작자 미상",
                    "count": 1,
                    "first_played": "2024-03-12",
                },
            ],
        )
        self.assertEqual(
            result["labels"], ["바흐", "모차르트", "브람스", "베토벤", "작자 미상"]
        )
        self.assertEqual(result["values"], [1, 2, 1, 1, 1])

    def test_firsts_on_the_same_day_are_ordered_by_name_then_id(self):
        # Added after 베토벤 and 작자 미상, first played the same day.
        gabrieli = Composer.objects.create(name="가브리엘리")
        twin = Composer.objects.create(name="가브리엘리")
        for time, composer in ((2, twin), (3, gabrieli)):
            self.add_play(
                datetime.date(2024, 3, 12),
                time=time,
                music=Music.objects.create(composer=composer, title="칸초나"),
            )
        result = self.get("firsts", start="2024-03-12")
        self.assertEqual(
            [(item["id"], item["name"]) for item in result["items"]],
            [
                (gabrieli.id, "가브리엘리"),
                (twin.id, "가브리엘리"),
                (Composer.objects.get(name="베토벤").id, "베토벤"),
                (Composer.objects.get(name="작자 미상").id, "작자 미상"),
            ],
        )

    def test_firsts_list_works_named_like_stats_works(self):
        result = self.get("firsts", kind="work", start="2024-03-01")
        self.assertEqual(
            result["filters"],
            {"scope": "all", "start": "2024-03-01", "kind": "work"},
        )
        self.assertEqual(result["total_plays"], 5)
        self.assertEqual(
            result["items"],
            [
                {
                    "id": self.symphony.id,
                    "name": "모차르트 - 교향곡 제40번",
                    "count": 2,
                    "first_played": "2024-03-04",
                },
                {
                    "id": Music.objects.get(title="피아노 협주곡 제2번").id,
                    "name": "브람스 - 피아노 협주곡 제2번",
                    "count": 1,
                    "first_played": "2024-03-04",
                },
                {
                    "id": Music.objects.get(title="현악 사중주 제14번").id,
                    "name": "베토벤 - 현악 사중주 제14번",
                    "count": 1,
                    "first_played": "2024-03-12",
                },
                {
                    "id": Music.objects.get(title="그레고리오 성가").id,
                    "name": "작자 미상 - 그레고리오 성가",
                    "count": 1,
                    "first_played": "2024-03-12",
                },
            ],
        )

    def test_firsts_first_play_is_all_time_not_the_filtered_range(self):
        # Mozart and his symphony were first played on 3/4, before the range,
        # so their 3/6 play is not a first.
        composers = self.get("firsts", start="2024-03-05")
        self.assertEqual(composers["labels"], ["베토벤", "작자 미상"])
        works = self.get("firsts", kind="work", start="2024-03-05")
        self.assertEqual(
            works["labels"],
            ["베토벤 - 현악 사중주 제14번", "작자 미상 - 그레고리오 성가"],
        )
        # Bach was first played on the leap day, the end of fall 2023.
        result = self.get("firsts", semester_id=self.fall_2023.id)
        self.assertEqual(result["labels"], ["바흐"])
        self.assertEqual(
            self.get("firsts", semester_id=self.spring_2024.id)["labels"],
            ["모차르트", "브람스", "베토벤", "작자 미상"],
        )
        self.assertEqual(self.get("firsts", start="2024-03-13")["items"], [])

    def test_firsts_count_only_the_plays_in_the_filtered_range(self):
        self.add_play(datetime.date(2024, 9, 2), music=self.symphony)
        result = self.get("firsts", start="2024-03-04", end="2024-03-06")
        self.assertEqual(self.counts(result), {"모차르트": 2, "브람스": 1})
        result = self.get("firsts", start="2024-03-04")
        self.assertEqual(self.counts(result)["모차르트"], 3)
        self.assertEqual(result["items"][0]["first_played"], "2024-03-04")
        # Played again in fall 2024, but first played in spring.
        self.assertEqual(self.get("firsts", semester_id=self.fall_2024.id)["items"], [])

    def test_firsts_take_the_other_filters(self):
        # The member played Bach on 2/29 and Mozart and Brahms on 3/4.
        result = self.get("firsts", user_id=self.member.id, start="2024-03-01")
        self.assertEqual(self.counts(result), {"모차르트": 1, "브람스": 1})
        result = self.get("firsts", user_id=self.mentee.id)
        self.assertEqual(self.counts(result), {"베토벤": 1, "작자 미상": 1})
        result = self.get("firsts", kind="work", conductor_id=self.karajan.id)
        self.assertEqual(
            self.counts(result),
            {"모차르트 - 교향곡 제40번": 1, "브람스 - 피아노 협주곡 제2번": 1},
        )
        result = self.get("firsts", player_id=self.cellist.id, start="2024-03-01")
        self.assertEqual(self.counts(result), {"베토벤": 1})
        # Bernstein conducted the symphony on 3/6, after its first play on 3/4.
        result = self.get("firsts", conductor_id=self.bernstein.id, start="2024-03-05")
        self.assertEqual(result["items"], [])

    def test_firsts_count_a_play_once_with_mentee_sessions(self):
        # The 3/4 session has two members and two mentees, so the OR across both
        # M2M joins returns each of its plays on more than one row.
        params = {"user_id": self.mentee.id, "include_mentees": "true"}
        result = self.get("firsts", **params)
        self.assertEqual(result["total_plays"], 5)
        self.assertEqual(
            self.counts(result),
            {"모차르트": 2, "브람스": 1, "베토벤": 1, "작자 미상": 1},
        )
        result = self.get("firsts", kind="work", **params)
        self.assertEqual(sum(result["values"]), 5)

    def test_firsts_leave_out_plays_without_a_work(self):
        self.add_play(datetime.date(2024, 3, 13))
        for kind in ("composer", "work"):
            with self.subTest(kind=kind):
                result = self.get("firsts", kind=kind, start="2024-03-13")
                self.assertEqual(result["total_plays"], 1)
                self.assertEqual(result["items"], [])

    def test_firsts_kind_must_be_composer_or_work(self):
        for kind in ("composers", "Work", "player", "1"):
            with self.subTest(kind=kind):
                error = self.get_error("firsts", kind=kind)
                self.assertEqual(list(error), ["kind"])
                self.assertTrue(error["kind"])
        error = self.get_error("firsts", kind="x", start="garbage")
        self.assertEqual(set(error), {"kind", "start"})
        blank = self.get("firsts", kind="")
        self.assertEqual(blank["filters"]["kind"], "composer")
        self.assertEqual(len(blank["items"]), 5)

    def test_firsts_take_two_queries(self):
        scopes = [
            {},
            {"kind": "work"},
            {"user_id": self.mentee.id, "include_mentees": "true", "kind": "work"},
            {"start": "2025-01-01"},
        ]
        for params in scopes:
            with self.subTest(params=params):
                with self.assertNumQueries(2):
                    self.get("firsts", **params)
        # The semester's months take one more.
        with self.assertNumQueries(3):
            self.get("firsts", semester_id=self.spring_2024.id)

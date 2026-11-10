import datetime

from django.urls import reverse
from rest_framework.test import APITestCase

from apps.time_manage.models import (
    Composer,
    Conductor,
    Music,
    MusicDetail,
    Orchestra,
    Player,
    Semester,
    TimeInfo,
    TimeMusic,
    User,
)


class PlaysRequests:
    def get(self, **params):
        response = self.client.get(reverse("plays"), params)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def ids(self, **params):
        return [row["id"] for row in self.get(**params)["results"]]

    def session(self, date, time=1, users=(), mentees=()):
        info = TimeInfo.objects.create(date=date, time=time, arrival_time="09:30:00")
        info.users.set(users)
        info.mentees.set(mentees)
        return info


class EmptyPlaysTests(PlaysRequests, APITestCase):
    def test_no_plays_give_an_empty_page_in_one_query(self):
        stats_filters = {
            "user_id": 1,
            "include_mentees": "true",
            "composer_id": 1,
            "music_id": 1,
            "player_id": 1,
            "conductor_id": 1,
            "orchestra_id": 1,
            "requested": "true",
        }
        for params in (
            {},
            {"limit": 10},
            {"q": "바흐", "start": "2024-01-01"},
            stats_filters,
        ):
            with self.subTest(params=params), self.assertNumQueries(1):
                self.assertEqual(
                    self.get(**params),
                    {"count": 0, "next": None, "previous": None, "results": []},
                )

    def test_a_session_without_plays_lists_nothing(self):
        self.session(datetime.date(2024, 3, 4))
        self.assertEqual(self.get()["count"], 0)


class PlaysTests(PlaysRequests, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.member = User.objects.create(name="지기", major="음악학과", year_id="20")
        cls.mentee = User.objects.create(
            name="견습 지기", major="물리학과", year_id="24"
        )

        cls.bach = Composer.objects.create(name="Bach")
        brahms = Composer.objects.create(name="브람스")
        cls.suite = Music.objects.create(composer=cls.bach, title="무반주 첼로 모음곡")
        concerto = Music.objects.create(composer=brahms, title="피아노 협주곡 제2번")
        sonata = Music.objects.create(composer=brahms, title="첼로 소나타 제1번")
        prelude = MusicDetail.objects.create(music=cls.suite, semi_title="전주곡")
        karajan = Conductor.objects.create(name="카라얀")
        berlin = Orchestra.objects.create(name="베를린 필하모닉")
        cls.cellist = Player.objects.create(name="첼리스트", instrument="첼로")
        pianist = Player.objects.create(name="피아니스트", instrument="피아노")

        march_4 = cls.session(cls, datetime.date(2024, 3, 4), users=[cls.member])
        cls.march_6 = cls.session(
            cls,
            datetime.date(2024, 3, 6),
            time=2,
            users=[cls.member],
            mentees=[cls.mentee],
        )

        def play(info, order, music, detail=None, players=(), **fields):
            tm = TimeMusic.objects.create(
                time=info,
                order=order,
                source="CD",
                music=music,
                music_detail=detail,
                **fields,
            )
            for player in players:
                tm.players.add(player)
            return tm

        cls.first = play(march_4, 1, cls.suite, prelude, [cls.cellist])
        cls.second = play(
            march_4, 2, concerto, conductor=karajan, orchestra=berlin, players=[pianist]
        )
        # The pianist typed first, though the cellist's row is older.
        cls.duo = play(
            cls.march_6,
            1,
            sonata,
            players=[pianist, cls.cellist],
            is_requested=True,
            cd_id="DG-1",
        )

    def test_the_answer_is_a_page_without_and_with_limit(self):
        for params in ({}, {"limit": 2}):
            with self.subTest(params=params):
                result = self.get(**params)
                self.assertEqual(list(result), ["count", "next", "previous", "results"])
                self.assertEqual(result["count"], 3)
        self.assertEqual(len(self.get()["results"]), 3)

    def test_plays_are_newest_first_by_date_then_time_then_order(self):
        # Same date, a later 타임; then two plays sharing an order, by id.
        later = self.session(datetime.date(2024, 3, 6), time=3)
        tie_a = TimeMusic.objects.create(time=later, order=1, source="CD")
        tie_b = TimeMusic.objects.create(time=later, order=1, source="CD")
        self.assertEqual(
            self.ids(),
            [tie_b.id, tie_a.id, self.duo.id, self.second.id, self.first.id],
        )

    def test_a_row_has_the_session_list_fields_its_session_and_ids(self):
        self.assertEqual(
            self.get()["results"][0],
            {
                "id": self.duo.id,
                "order": 1,
                "is_requested": True,
                "source": "CD",
                "cd_id": "DG-1",
                "music_title": "첼로 소나타 제1번",
                "composer_name": "브람스",
                # Players as typed, not by player id.
                "player_names": ["피아노: 피아니스트", "첼로: 첼리스트"],
                "time_id": self.march_6.id,
                "date": "2024-03-06",
                "time": 2,
                "composer_id": self.duo.music.composer_id,
                "music_id": self.duo.music_id,
                "jigi_names": ["지기"],
                "mentee_names": ["견습 지기"],
            },
        )
        oldest = self.get()["results"][2]
        self.assertEqual(oldest["music_semi_title"], "전주곡")
        self.assertEqual(oldest["composer_id"], self.bach.id)
        self.assertEqual(oldest["mentee_names"], [])
        middle = self.get()["results"][1]
        self.assertEqual(middle["conductor_name"], "카라얀")
        self.assertEqual(middle["orchestra_name"], "베를린 필하모닉")

    def test_a_play_without_music_has_null_ids(self):
        bare = TimeMusic.objects.create(time=self.march_6, order=2, source="LP")
        row = self.get()["results"][0]
        self.assertEqual(row["id"], bare.id)
        self.assertIsNone(row["music_id"])
        self.assertIsNone(row["composer_id"])
        self.assertEqual(row["player_names"], [])

    def test_q_matches_each_field_ignoring_case(self):
        cases = [
            ("bach", [self.first.id]),  # composer, any case
            ("BACH", [self.first.id]),
            ("협주곡", [self.second.id]),  # title
            ("전주", [self.first.id]),  # 세부 제목
            ("피아니", [self.duo.id, self.second.id]),  # player name
            ("첼로", [self.duo.id, self.first.id]),  # instrument and title
            ("카라", [self.second.id]),  # conductor
            ("필하모닉", [self.second.id]),  # orchestra
            ("없는 이름", []),
        ]
        for q, expected in cases:
            with self.subTest(q=q):
                result = self.get(q=q)
                self.assertEqual([row["id"] for row in result["results"]], expected)
                self.assertEqual(result["count"], len(expected))

    def test_q_lists_a_play_once_when_several_players_match(self):
        # Both players of the duo contain "스트".
        self.assertEqual(
            self.ids(q="스트"), [self.duo.id, self.second.id, self.first.id]
        )
        self.assertEqual(self.get(q="스트")["count"], 3)

    def test_q_is_trimmed_and_blank_q_lists_every_play(self):
        self.assertEqual(self.ids(q="  카라얀 "), [self.second.id])
        self.assertEqual(self.get(q="   ")["count"], 3)
        self.assertEqual(self.get(q="")["count"], 3)

    def test_q_does_not_treat_percent_or_underscore_as_wildcards(self):
        self.assertEqual(self.ids(q="%"), [])
        self.assertEqual(self.ids(q="_"), [])

    def test_start_and_end_are_inclusive_and_combine_with_q(self):
        self.assertEqual(self.ids(start="2024-03-06"), [self.duo.id])
        self.assertEqual(self.ids(end="2024-03-04"), [self.second.id, self.first.id])
        self.assertEqual(
            self.ids(start="2024-03-04", end="2024-03-06"),
            [self.duo.id, self.second.id, self.first.id],
        )
        self.assertEqual(self.ids(start="2024-03-05", end="2024-03-05"), [])
        self.assertEqual(self.ids(end="2024-03-04", q="첼로"), [self.first.id])

    def test_blank_and_unpadded_dates_still_work(self):
        self.assertEqual(self.get(start="", end="")["count"], 3)
        self.assertEqual(self.ids(start="2024-3-6"), [self.duo.id])

    def test_malformed_dates_get_400_naming_the_parameter(self):
        for param, value in [
            ("start", "garbage"),
            ("start", "2024-13-01"),
            ("end", "2024-02-30"),
            ("end", "3/4"),
        ]:
            with self.subTest(param=param, value=value):
                response = self.client.get(reverse("plays"), {param: value})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(list(response.json()), [param])

    def test_each_stats_id_filter_lists_only_its_plays(self):
        brahms = self.duo.music.composer_id
        pianist = self.second.players.get().id
        cases = [
            ({"composer_id": self.bach.id}, [self.first.id]),
            ({"composer_id": brahms}, [self.duo.id, self.second.id]),
            ({"music_id": self.suite.id}, [self.first.id]),
            # The duo has both players and is listed once.
            ({"player_id": self.cellist.id}, [self.duo.id, self.first.id]),
            ({"player_id": pianist}, [self.duo.id, self.second.id]),
            ({"conductor_id": self.second.conductor_id}, [self.second.id]),
            ({"orchestra_id": self.second.orchestra_id}, [self.second.id]),
            ({"composer_id": brahms, "player_id": self.cellist.id}, [self.duo.id]),
            ({"composer_id": 999999}, []),
            ({"player_id": 999999}, []),
        ]
        for params, expected in cases:
            with self.subTest(params=params):
                result = self.get(**params)
                self.assertEqual([row["id"] for row in result["results"]], expected)
                self.assertEqual(result["count"], len(expected))

    def test_semester_id_takes_its_dates_over_start_and_end_as_in_stats(self):
        def semester(year, num):
            return Semester.objects.create(
                year=year, semester_num=num, start_time="09:30", end_time="17:40"
            )

        fall_2023, spring_2024 = semester(2023, 2), semester(2024, 1)
        # 2024 is a leap year: the 2nd semester of 2023 ends on 2024-02-29.
        winter = TimeMusic.objects.create(
            time=self.session(datetime.date(2024, 2, 29)), order=1, source="CD"
        )
        everything = [self.duo.id, self.second.id, self.first.id]
        self.assertEqual(self.ids(semester_id=fall_2023.id), [winter.id])
        self.assertEqual(self.ids(semester_id=spring_2024.id), everything)
        self.assertEqual(
            self.ids(semester_id=spring_2024.id, start="2024-03-05"), everything
        )
        # An unknown semester is no filter, as in stats/.
        self.assertEqual(self.ids(semester_id=999999), everything + [winter.id])

    def test_user_id_lists_their_sessions_and_include_mentees_adds_mentored(self):
        self.assertEqual(
            self.ids(user_id=self.member.id),
            [self.duo.id, self.second.id, self.first.id],
        )
        self.assertEqual(self.ids(user_id=self.mentee.id), [])
        for flag in ("true", "1", "yes"):
            with self.subTest(include_mentees=flag):
                self.assertEqual(
                    self.ids(user_id=self.mentee.id, include_mentees=flag),
                    [self.duo.id],
                )
        self.assertEqual(self.ids(user_id=self.mentee.id, include_mentees="false"), [])

    def test_include_mentees_lists_a_play_once_with_two_jigi_and_two_mentees(self):
        others = [
            User.objects.create(name=f"지기 {n}", major="국문학과", year_id="22")
            for n in range(2)
        ]
        crowded = self.session(
            datetime.date(2024, 3, 8),
            users=[self.member, others[0]],
            mentees=[self.mentee, others[1]],
        )
        play = TimeMusic.objects.create(time=crowded, order=1, source="CD")
        for user in (self.member, self.mentee):
            with self.subTest(user=user.name):
                result = self.get(user_id=user.id, include_mentees="true")
                self.assertEqual(result["results"][0]["id"], play.id)
                ids = [row["id"] for row in result["results"]]
                self.assertEqual(len(ids), len(set(ids)))
                self.assertEqual(result["count"], len(ids))
        self.assertEqual(
            self.get(user_id=self.member.id, include_mentees="true")["count"], 4
        )
        self.assertEqual(
            self.ids(user_id=self.mentee.id, include_mentees="true"),
            [play.id, self.duo.id],
        )

    def test_requested_lists_only_or_no_requests_and_absent_lists_both(self):
        self.assertEqual(self.ids(requested="true"), [self.duo.id])
        self.assertEqual(self.ids(requested="1"), [self.duo.id])
        self.assertEqual(self.ids(requested="false"), [self.second.id, self.first.id])
        self.assertEqual(self.ids(requested="0"), [self.second.id, self.first.id])
        # Absent or blank is both, not false.
        self.assertEqual(self.ids(), [self.duo.id, self.second.id, self.first.id])
        self.assertEqual(
            self.ids(requested=""), [self.duo.id, self.second.id, self.first.id]
        )

    def test_filters_combine_with_q_dates_and_each_other(self):
        brahms = self.duo.music.composer_id
        self.assertEqual(self.ids(composer_id=brahms, q="첼로"), [self.duo.id])
        self.assertEqual(
            self.ids(composer_id=brahms, requested="false"), [self.second.id]
        )
        self.assertEqual(
            self.ids(player_id=self.cellist.id, end="2024-03-04"), [self.first.id]
        )
        self.assertEqual(
            self.ids(user_id=self.mentee.id, include_mentees="true", requested="false"),
            [],
        )

    def test_malformed_filters_get_400_naming_each_parameter(self):
        for param, value in [
            ("semester_id", "abc"),
            ("user_id", "1.5"),
            ("composer_id", "x"),
            ("music_id", "abc"),
            ("player_id", str(2**63)),
            ("conductor_id", "-"),
            ("orchestra_id", "1e3"),
            ("requested", "maybe"),
        ]:
            with self.subTest(param=param, value=value):
                response = self.client.get(reverse("plays"), {param: value})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(list(response.json()), [param])
        response = self.client.get(
            reverse("plays"), {"start": "bad", "composer_id": "x", "requested": "2"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(set(response.json()), {"start", "composer_id", "requested"})

    def test_page_links_keep_the_filters(self):
        brahms = self.duo.music.composer_id
        result = self.get(limit=1, composer_id=brahms, requested="false")
        self.assertEqual([row["id"] for row in result["results"]], [self.second.id])
        self.assertIsNone(result["next"])
        result = self.get(limit=1, composer_id=brahms)
        self.assertIn(f"composer_id={brahms}", result["next"])
        self.assertEqual(
            self.client.get(result["next"]).json()["results"][0]["id"], self.second.id
        )

    def test_pages_go_by_limit_and_offset(self):
        result = self.get(limit=2)
        self.assertEqual(
            [row["id"] for row in result["results"]], [self.duo.id, self.second.id]
        )
        self.assertIsNone(result["previous"])
        self.assertTrue(result["next"].endswith("/plays/?limit=2&offset=2"))

        result = self.get(limit=2, offset=2)
        self.assertEqual([row["id"] for row in result["results"]], [self.first.id])
        self.assertIsNone(result["next"])
        self.assertTrue(result["previous"].endswith("/plays/?limit=2"))

    def test_an_offset_past_the_end_gives_an_empty_page(self):
        for offset in (3, 4, "9" * 30):
            with self.subTest(offset=offset):
                result = self.get(offset=offset)
                self.assertEqual(result["count"], 3)
                self.assertEqual(result["results"], [])


class PlaysPagingTests(PlaysRequests, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.member = User.objects.create(name="지기", major="음악학과", year_id="20")
        cls.mentee = User.objects.create(
            name="견습 지기", major="물리학과", year_id="24"
        )
        composer = Composer.objects.create(name="작곡가")
        cls.music = Music.objects.create(composer=composer, title="소품")
        cls.info = cls.session(
            cls, datetime.date(2024, 3, 4), users=[cls.member], mentees=[cls.mentee]
        )
        TimeMusic.objects.bulk_create(
            TimeMusic(time=cls.info, order=n, source="CD", music=cls.music)
            for n in range(1, 121)
        )

    def test_a_page_holds_50_by_default_and_at_most_100(self):
        for params, size in [
            ({}, 50),
            ({"limit": 10}, 10),
            ({"limit": 100}, 100),
            ({"limit": 101}, 100),
            ({"limit": 0}, 50),
            ({"limit": "abc"}, 50),
        ]:
            with self.subTest(params=params):
                result = self.get(**params)
                self.assertEqual(result["count"], 120)
                self.assertEqual(len(result["results"]), size)
        self.assertTrue(self.get()["next"].endswith("/plays/?limit=50&offset=50"))

    def test_a_page_takes_five_queries_whatever_its_size(self):
        # Every play with players, 지기 and 견습 지기 to prefetch.
        players = [
            Player.objects.create(name=f"연주자 {n}", instrument="피아노")
            for n in range(3)
        ]
        for play in TimeMusic.objects.all():
            play.players.set(players)
        for limit in (1, 50, 100):
            with self.subTest(limit=limit), self.assertNumQueries(5):
                result = self.get(limit=limit)
            self.assertEqual(len(result["results"]), limit)
            self.assertEqual(len(result["results"][-1]["player_names"]), 3)
        with self.assertNumQueries(5):
            self.get(q="연주자")

    def test_the_stats_filters_add_no_query_but_the_semester_lookup(self):
        filters = {
            "user_id": self.mentee.id,
            "include_mentees": "true",
            "composer_id": self.music.composer_id,
            "music_id": self.music.id,
            "requested": "false",
        }
        with self.assertNumQueries(5):
            result = self.get(limit=100, **filters)
        self.assertEqual(len(result["results"]), 100)
        self.assertEqual(result["count"], 120)
        spring_2024 = Semester.objects.create(
            year=2024, semester_num=1, start_time="09:30", end_time="17:40"
        )
        with self.assertNumQueries(6):
            result = self.get(limit=100, semester_id=spring_2024.id, **filters)
        self.assertEqual(result["count"], 120)

import datetime
import unicodedata

from django.urls import reverse
from rest_framework.test import APITestCase

from apps.time_manage.catalog import normalize_name
from apps.time_manage.models import (
    Composer,
    Conductor,
    Music,
    Orchestra,
    Player,
    TimeInfo,
    TimeMusic,
)

KINDS = ["composer", "player", "conductor", "orchestra", "music"]


class NormalizeNameTests(APITestCase):
    def test_ignores_case_spaces_dots_and_hyphens(self):
        for name in ("J. S. Bach", "j.s.bach", "J S BACH", "J.-S. Bach"):
            with self.subTest(name=name):
                self.assertEqual(normalize_name(name), "jsbach")
        self.assertEqual(normalize_name("생-상스"), normalize_name("생상스"))
        self.assertEqual(normalize_name("Saint–Saëns"), "saintsaëns")
        self.assertEqual(normalize_name("Strauß"), normalize_name("STRAUSS"))

    def test_reads_decomposed_hangul_and_full_width_letters_as_typed_ones(self):
        self.assertEqual(
            normalize_name(unicodedata.normalize("NFD", "생상스")), "생상스"
        )
        self.assertEqual(normalize_name("Ｂａｃｈ"), "bach")

    def test_keeps_other_punctuation(self):
        self.assertNotEqual(normalize_name("Bach, J.S."), normalize_name("J.S. Bach"))


class DuplicatesRequests:
    def get(self, **params):
        response = self.client.get(reverse("catalog-duplicates"), params)
        self.assertEqual(response.status_code, 200)
        return response.json()


class EmptyDuplicatesTests(DuplicatesRequests, APITestCase):
    def test_an_empty_catalog_has_no_groups_in_one_query(self):
        for kind in KINDS:
            with self.subTest(kind=kind), self.assertNumQueries(1):
                self.assertEqual(self.get(kind=kind), {"kind": kind, "groups": []})

    def test_kind_defaults_to_composer(self):
        for params in ({}, {"kind": ""}):
            with self.subTest(params=params):
                self.assertEqual(self.get(**params), {"kind": "composer", "groups": []})

    def test_an_unknown_kind_is_a_400(self):
        for kind in ("work", "Composer", "composers", "1"):
            with self.subTest(kind=kind):
                response = self.client.get(
                    reverse("catalog-duplicates"), {"kind": kind}
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("kind", response.json())

    def test_is_read_only(self):
        for method in ("post", "put", "patch", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(
                    reverse("catalog-duplicates"), {"kind": "composer"}
                )
                self.assertEqual(response.status_code, 405)


class DuplicatesTests(DuplicatesRequests, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.session = TimeInfo.objects.create(
            date=datetime.date(2026, 9, 7), time=2, arrival_time="11:20:00"
        )

    def play(self, music=None, players=(), conductor=None, orchestra=None, times=1):
        for _ in range(times):
            play = TimeMusic.objects.create(
                time=self.session,
                order=TimeMusic.objects.count() + 1,
                source="CD",
                music=music,
                conductor=conductor,
                orchestra=orchestra,
            )
            play.players.set(players)

    def composer(self, name, plays=0):
        composer = Composer.objects.create(name=name)
        if plays:
            self.play(Music.objects.create(composer=composer, title="곡"), times=plays)
        return composer

    def row(self, obj, count, **extra):
        return {"id": obj.id, "name": obj.name, "count": count, **extra}

    def test_groups_composers_whose_names_differ_only_in_spelling(self):
        spaced = self.composer("J. S. Bach", plays=1)
        plain = self.composer("J.S. Bach", plays=3)
        lower = self.composer("js bach")
        hyphen = self.composer("생-상스", plays=2)
        decomposed = self.composer(unicodedata.normalize("NFD", "생상스"), plays=2)
        self.composer("브람스", plays=5)  # no variant: not listed

        with self.assertNumQueries(1):
            body = self.get(kind="composer")
        self.assertEqual(
            body,
            {
                "kind": "composer",
                "groups": [
                    # Most plays first; in a group, most plays, then name, then id.
                    {
                        "key": "jsbach",
                        "count": 4,
                        "rows": [
                            self.row(plain, 3),
                            self.row(spaced, 1),
                            self.row(lower, 0),
                        ],
                    },
                    {
                        "key": "생상스",
                        "count": 4,
                        "rows": [self.row(decomposed, 2), self.row(hyphen, 2)],
                    },
                ],
            },
        )

    def test_counts_a_composer_s_plays_over_all_its_works(self):
        first = self.composer("Bach")
        Music.objects.bulk_create(
            Music(composer=first, title=title) for title in ("가", "나")
        )
        for music in Music.objects.filter(composer=first):
            self.play(music, times=2)
        second = self.composer("BACH", plays=1)
        self.assertEqual(
            self.get()["groups"],
            [
                {
                    "key": "bach",
                    "count": 5,
                    "rows": [self.row(first, 4), self.row(second, 1)],
                }
            ],
        )

    def test_groups_of_equal_plays_follow_their_key(self):
        self.composer("Liszt", plays=1)
        self.composer("liszt")
        self.composer("Chopin", plays=1)
        self.composer("chopin")
        self.assertEqual(
            [group["key"] for group in self.get()["groups"]], ["chopin", "liszt"]
        )

    def test_groups_players_by_name_whatever_their_instrument(self):
        cho = Player.objects.create(name="조성진", instrument="피아노")
        cho_spaced = Player.objects.create(name="조 성진", instrument="피아노")
        cho_english = Player.objects.create(name="조성진", instrument="Piano")
        other = Player.objects.create(name="임윤찬", instrument="피아노")
        self.play(players=[cho, other], times=2)
        self.play(players=[cho_english])

        with self.assertNumQueries(1):
            body = self.get(kind="player")
        self.assertEqual(
            body,
            {
                "kind": "player",
                "groups": [
                    {
                        "key": "조성진",
                        "count": 3,
                        "rows": [
                            self.row(cho, 2, instrument="피아노"),
                            self.row(cho_english, 1, instrument="Piano"),
                            self.row(cho_spaced, 0, instrument="피아노"),
                        ],
                    }
                ],
            },
        )

    def test_groups_conductors_and_orchestras(self):
        karajan = Conductor.objects.create(name="Herbert von Karajan")
        karajan_lower = Conductor.objects.create(name="herbert von karajan")
        Conductor.objects.create(name="카라얀")
        berlin = Orchestra.objects.create(name="베를린 필하모닉")
        berlin_joined = Orchestra.objects.create(name="베를린필하모닉")
        Orchestra.objects.create(name="빈 필하모닉")
        self.play(conductor=karajan, orchestra=berlin_joined, times=2)
        self.play(conductor=karajan_lower, orchestra=berlin)

        for kind, key, rows in (
            ("conductor", "herbertvonkarajan", [(karajan, 2), (karajan_lower, 1)]),
            ("orchestra", "베를린필하모닉", [(berlin_joined, 2), (berlin, 1)]),
        ):
            with self.subTest(kind=kind), self.assertNumQueries(1):
                self.assertEqual(
                    self.get(kind=kind)["groups"],
                    [
                        {
                            "key": key,
                            "count": 3,
                            "rows": [self.row(obj, count) for obj, count in rows],
                        }
                    ],
                )

    def test_groups_a_composer_s_works_by_catalog_number(self):
        beethoven = Composer.objects.create(name="베토벤")
        other_beethoven = Composer.objects.create(name="Beethoven")
        mozart = Composer.objects.create(name="모차르트")
        fifth = Music.objects.create(composer=beethoven, title="교향곡 제5번 Op. 67")
        fifth_short = Music.objects.create(composer=beethoven, title="Symphony 5 op.67")
        Music.objects.create(composer=beethoven, title="교향곡 제7번 Op. 92")
        Music.objects.create(composer=beethoven, title="교향곡 제9번")
        Music.objects.create(composer=beethoven, title="교향곡 제9번")
        # Another composer row: grouped with its own works only.
        Music.objects.create(composer=other_beethoven, title="Symphony No. 5, Op. 67")
        k550 = Music.objects.create(composer=mozart, title="교향곡 40번 K. 550")
        kv550 = Music.objects.create(composer=mozart, title="Symphony No. 40 KV 550")
        self.play(fifth, times=2)
        self.play(fifth_short)
        self.play(kv550)

        with self.assertNumQueries(1):
            body = self.get(kind="music")

        def work(music, count):
            return {
                "id": music.id,
                "name": music.title,
                "count": count,
                "composer_id": music.composer_id,
                "composer_name": music.composer.name,
            }

        self.assertEqual(
            body,
            {
                "kind": "music",
                "groups": [
                    {
                        "key": "op67",
                        "count": 3,
                        "rows": [work(fifth, 2), work(fifth_short, 1)],
                    },
                    {
                        "key": "k550",
                        "count": 1,
                        "rows": [work(kv550, 1), work(k550, 0)],
                    },
                ],
            },
        )

    def test_only_kind_changes_the_report(self):
        self.composer("Bach")
        self.composer("bach")
        self.assertEqual(self.get(kind="conductor")["groups"], [])
        self.assertEqual(len(self.get(kind="composer")["groups"]), 1)

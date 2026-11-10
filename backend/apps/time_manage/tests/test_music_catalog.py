import datetime

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.time_manage.models import Composer, Music, TimeInfo, TimeMusic


class MusicCatalogTests(APITestCase):
    """composers/ and musics/ list everything ever played, most played first."""

    def setUp(self):
        self.session = TimeInfo.objects.create(
            date=datetime.date(2026, 9, 7), time=2, arrival_time="11:20:00"
        )
        self.beethoven = Composer.objects.create(name="루트비히 판 베토벤")
        self.brahms = Composer.objects.create(name="요하네스 브람스")
        self.chopin = Composer.objects.create(name="프레데리크 쇼팽")
        self.sonata = self.music(self.beethoven, "피아노 소나타 제23번 Op. 57", 1)
        self.concerto = self.music(self.brahms, "이중 협주곡 Op. 102", 2)
        self.symphony = self.music(self.beethoven, "교향곡 제7번 Op. 92", 3)
        self.nocturne = self.music(self.chopin, "녹턴 Op. 9 No. 2", 0)

    def music(self, composer, title, plays):
        music = Music.objects.create(composer=composer, title=title)
        for _ in range(plays):
            self.play(music)
        return music

    def play(self, music):
        order = TimeMusic.objects.count() + 1
        TimeMusic.objects.create(
            time=self.session, order=order, source="CD", music=music
        )

    def composer_body(self, composer, plays, era="미상"):
        return {
            "id": composer.id,
            "name": composer.name,
            "num_time_music": plays,
            "birth_year": composer.birth_year,
            "era_override": composer.era_override,
            "era": era,
        }

    def music_body(self, music, plays):
        return {
            "id": music.id,
            "title": music.title,
            "composer": {"name": music.composer.name},
            "num_time_music": plays,
        }

    def test_lists_composers_by_plays_of_all_their_musics(self):
        response = self.client.get(reverse("composerlist-list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                self.composer_body(self.beethoven, 4),
                self.composer_body(self.brahms, 2),
                self.composer_body(self.chopin, 0),
            ],
        )

    def test_shows_one_composer(self):
        response = self.client.get(
            reverse("composerlist-detail", args=[self.brahms.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.composer_body(self.brahms, 2))
        missing = self.client.get(reverse("composerlist-detail", args=[9999]))
        self.assertEqual(missing.status_code, 404)

    def test_shows_each_composers_birth_year_override_and_era(self):
        self.beethoven.birth_year = 1770
        self.beethoven.era_override = "고전"  # 1770 is 낭만 by birth year
        self.beethoven.save()
        self.brahms.birth_year = 1833
        self.brahms.save()
        # An override that is not an era falls back to the birth year.
        self.chopin.birth_year = 1810
        self.chopin.era_override = "19세기"
        self.chopin.save()

        response = self.client.get(reverse("composerlist-list"))
        self.assertEqual(
            response.json(),
            [
                self.composer_body(self.beethoven, 4, era="고전"),
                self.composer_body(self.brahms, 2, era="낭만"),
                self.composer_body(self.chopin, 0, era="낭만"),
            ],
        )
        self.assertEqual(response.json()[0]["era_override"], "고전")
        self.assertEqual(response.json()[2]["era_override"], "19세기")
        detail = self.client.get(reverse("composerlist-detail", args=[self.brahms.id]))
        self.assertEqual(detail.json(), self.composer_body(self.brahms, 2, era="낭만"))

    def get_composers(self, **params):
        response = self.client.get(reverse("composerlist-list"), params)
        self.assertEqual(response.status_code, 200)
        return [composer["name"] for composer in response.json()]

    def test_q_keeps_composers_whose_name_contains_it(self):
        self.assertEqual(self.get_composers(q="브람스"), [self.brahms.name])
        # Trimmed, as saved names are.
        self.assertEqual(self.get_composers(q=" 베토벤 "), [self.beethoven.name])
        # Case-insensitive.
        Composer.objects.create(name="Johannes BRAHMS")
        self.assertEqual(self.get_composers(q="brahms"), ["Johannes BRAHMS"])
        self.assertEqual(self.get_composers(q="바흐"), [])

    def test_limit_keeps_the_most_played_composers(self):
        self.assertEqual(
            self.get_composers(limit=2), [self.beethoven.name, self.brahms.name]
        )
        self.assertEqual(self.get_composers(limit=1), [self.beethoven.name])
        self.assertEqual(len(self.get_composers(limit=100)), 3)

    def test_composers_with_as_many_plays_are_listed_by_name_then_id(self):
        # Created after 쇼팽, so not in id order.
        haydn = Composer.objects.create(name="하이든")
        gabrieli = Composer.objects.create(name="가브리엘리")
        twin = Composer.objects.create(name="가브리엘리")
        response = self.client.get(reverse("composerlist-list"))
        self.assertEqual(
            [composer["id"] for composer in response.json()],
            [
                self.beethoven.id,
                self.brahms.id,
                gabrieli.id,
                twin.id,
                self.chopin.id,
                haydn.id,
            ],
        )
        self.assertEqual(
            self.get_composers(limit=3),
            [self.beethoven.name, self.brahms.name, gabrieli.name],
        )

    def test_q_and_limit_combine(self):
        ockeghem = Composer.objects.create(name="요하네스 오케겜")
        self.assertEqual(
            self.get_composers(q="요하네스"), [self.brahms.name, ockeghem.name]
        )
        self.assertEqual(self.get_composers(q="요하네스", limit=1), [self.brahms.name])

    def test_blank_q_and_limit_list_every_composer(self):
        everyone = [self.beethoven.name, self.brahms.name, self.chopin.name]
        self.assertEqual(self.get_composers(), everyone)
        self.assertEqual(self.get_composers(q="", limit=""), everyone)
        self.assertEqual(self.get_composers(q="   "), everyone)

    def test_malformed_limit_is_400_naming_it(self):
        for limit in ["abc", "0", "-1", "1.5", str(2**63)]:
            with self.subTest(limit=limit):
                response = self.client.get(
                    reverse("composerlist-list"), {"limit": limit}
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(list(response.json()), ["limit"])

    def test_one_composer_ignores_q_and_limit(self):
        url = reverse("composerlist-detail", args=[self.chopin.id])
        response = self.client.get(url, {"q": "브람스", "limit": "abc"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.composer_body(self.chopin, 0))

    def test_lists_musics_by_plays_with_their_composer(self):
        response = self.client.get(reverse("musiclist-list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                self.music_body(self.symphony, 3),
                self.music_body(self.concerto, 2),
                self.music_body(self.sonata, 1),
                self.music_body(self.nocturne, 0),
            ],
        )

    def test_shows_one_music(self):
        response = self.client.get(reverse("musiclist-detail", args=[self.sonata.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.music_body(self.sonata, 1))
        missing = self.client.get(reverse("musiclist-detail", args=[9999]))
        self.assertEqual(missing.status_code, 404)

    def test_lists_one_composers_musics_by_plays(self):
        url = reverse("music-by-composer-list", args=[self.beethoven.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [self.music_body(self.symphony, 3), self.music_body(self.sonata, 1)],
        )
        response = self.client.get(
            reverse(
                "music-by-composer-detail", args=[self.beethoven.id, self.sonata.id]
            )
        )
        self.assertEqual(response.json(), self.music_body(self.sonata, 1))
        # Another composer's music is not found under this one.
        response = self.client.get(
            reverse(
                "music-by-composer-detail", args=[self.beethoven.id, self.concerto.id]
            )
        )
        self.assertEqual(response.status_code, 404)

    def test_an_unknown_composer_has_no_musics(self):
        url = reverse("music-by-composer-list", args=[9999])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_reads_each_list_in_one_query_however_many_musics(self):
        # Each music shows its composer's name: one SELECT per music before.
        urls = [
            reverse("composerlist-list"),
            reverse("musiclist-list"),
            reverse("music-by-composer-list", args=[self.beethoven.id]),
        ]
        for url in urls:
            with self.subTest(url=url), self.assertNumQueries(1):
                self.assertEqual(self.client.get(url).status_code, 200)

        for number in range(20):
            composer = Composer.objects.create(name=f"작곡가 {number}")
            self.music(composer, f"소품 {number}", 1)
            self.music(self.beethoven, f"바가텔 {number}", 1)
        for url in urls:
            with self.subTest(url=url), self.assertNumQueries(1):
                self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(len(self.client.get(urls[1]).json()), 44)
        self.assertEqual(len(self.client.get(urls[2]).json()), 22)

    def test_searches_composers_in_one_query_however_many_match(self):
        url = reverse("composerlist-list")
        for number in range(20):
            composer = Composer.objects.create(name=f"작곡가 {number}")
            self.music(composer, f"소품 {number}", 1)
        for params in [{"q": "작곡가"}, {"limit": 5}, {"q": "작곡가", "limit": 50}]:
            with self.subTest(params=params), self.assertNumQueries(1):
                self.assertEqual(self.client.get(url, params).status_code, 200)
        self.assertEqual(len(self.get_composers(q="작곡가")), 20)

    def test_an_empty_catalog_lists_no_composers(self):
        TimeMusic.objects.all().delete()
        Music.objects.all().delete()
        Composer.objects.all().delete()
        self.assertEqual(self.get_composers(), [])
        self.assertEqual(self.get_composers(q="브람스", limit=3), [])


class ComposerCorrectionTests(APITestCase):
    """PATCH composers/<id>/ corrects a composer's birth_year and era_override,
    the two values the stats count its 시대 by. Nothing else is writable."""

    def setUp(self):
        session = TimeInfo.objects.create(
            date=datetime.date(2026, 9, 7), time=2, arrival_time="11:20:00"
        )
        self.beethoven = Composer.objects.create(name="루트비히 판 베토벤")
        self.chopin = Composer.objects.create(
            name="프레데리크 쇼팽", birth_year=1810, era_override="19세기"
        )
        for order in [1, 2]:
            music = Music.objects.create(
                composer=self.beethoven, title=f"소나타 {order}"
            )
            TimeMusic.objects.create(
                time=session, order=order, source="CD", music=music
            )
        self.url = reverse("composerlist-detail", args=[self.beethoven.id])

    def patch(self, body, url=None):
        return self.client.patch(url or self.url, body, format="json")

    def stored(self, composer=None):
        composer = Composer.objects.get(id=(composer or self.beethoven).id)
        return composer.name, composer.birth_year, composer.era_override

    def test_sets_birth_year_and_era_override_and_answers_the_composer(self):
        response = self.patch({"birth_year": 1770, "era_override": "고전"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "id": self.beethoven.id,
                "name": "루트비히 판 베토벤",
                "num_time_music": 2,
                "birth_year": 1770,
                "era_override": "고전",
                "era": "고전",  # 1770 is 낭만 by birth year
            },
        )
        self.assertEqual(self.stored(), ("루트비히 판 베토벤", 1770, "고전"))
        detail = self.client.get(self.url)
        self.assertEqual(detail.json(), response.json())

    def test_sets_one_field_and_keeps_the_other(self):
        response = self.patch({"birth_year": 1770})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["era"], "낭만")
        self.assertEqual(self.stored(), ("루트비히 판 베토벤", 1770, None))

        response = self.patch({"era_override": "고전"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["era"], "고전")
        self.assertEqual(self.stored(), ("루트비히 판 베토벤", 1770, "고전"))

        # An override that is not an era, stored before, is kept and still
        # ignored by era until it is corrected.
        url = reverse("composerlist-detail", args=[self.chopin.id])
        response = self.patch({"birth_year": 1811}, url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["era_override"], "19세기")
        self.assertEqual(response.json()["era"], "낭만")
        self.assertEqual(self.stored(self.chopin), ("프레데리크 쇼팽", 1811, "19세기"))

    def test_takes_every_era_including_unknown(self):
        for era in ["중세", "바로크", "고전", "낭만", "근현대", "미상"]:
            with self.subTest(era=era):
                response = self.patch({"birth_year": 1770, "era_override": era})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["era"], era)
                self.assertEqual(self.stored()[2], era)

    def test_null_or_blank_clears_either_field(self):
        for empty in [None, ""]:
            with self.subTest(empty=empty):
                self.patch({"birth_year": 1770, "era_override": "고전"})
                response = self.patch({"era_override": empty})
                self.assertEqual(response.status_code, 200)
                self.assertIsNone(response.json()["era_override"])
                self.assertEqual(response.json()["era"], "낭만")
                self.assertEqual(self.stored(), ("루트비히 판 베토벤", 1770, None))

                response = self.patch({"birth_year": empty})
                self.assertEqual(response.status_code, 200)
                self.assertIsNone(response.json()["birth_year"])
                self.assertEqual(response.json()["era"], "미상")
                self.assertEqual(self.stored(), ("루트비히 판 베토벤", None, None))

    def test_the_era_chart_counts_the_corrected_era(self):
        eras = reverse("stats-eras")
        self.assertEqual(self.client.get(eras).json()["labels"], ["미상"])
        self.patch({"birth_year": 1770})
        self.assertEqual(self.client.get(eras).json()["labels"], ["낭만"])
        self.patch({"era_override": "고전"})
        self.assertEqual(self.client.get(eras).json()["labels"], ["고전"])
        self.assertEqual(self.client.get(eras).json()["values"], [2])

    def test_birth_year_from_1000_to_this_year(self):
        this_year = timezone.localdate().year
        for year in [1000, 1685, this_year]:
            with self.subTest(year=year):
                response = self.patch({"birth_year": year})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self.stored()[1], year)

    def test_malformed_birth_year_is_400_naming_it(self):
        self.patch({"birth_year": 1770, "era_override": "고전"})
        this_year = timezone.localdate().year
        for year in [999, this_year + 1, 0, -1770, 2**63, "abc", 1770.5, True, [1770]]:
            with self.subTest(year=year):
                response = self.patch({"birth_year": year, "era_override": "낭만"})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(list(response.json()), ["birth_year"])
                self.assertEqual(self.stored(), ("루트비히 판 베토벤", 1770, "고전"))

    def test_era_override_not_an_era_is_400_naming_it(self):
        self.patch({"birth_year": 1770, "era_override": "고전"})
        for era in ["19세기", "Baroque", " 낭만 ", "고전주의", 5, True, ["낭만"]]:
            with self.subTest(era=era):
                response = self.patch({"birth_year": 1810, "era_override": era})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(list(response.json()), ["era_override"])
                self.assertEqual(self.stored(), ("루트비히 판 베토벤", 1770, "고전"))

    def test_every_other_field_stays_read_only(self):
        response = self.patch(
            {
                "id": self.chopin.id,
                "name": "베토벤",
                "num_time_music": 99,
                "era": "중세",
                "birth_year": 1770,
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["id"], self.beethoven.id)
        self.assertEqual(response.json()["name"], "루트비히 판 베토벤")
        self.assertEqual(response.json()["num_time_music"], 2)
        self.assertEqual(response.json()["era"], "낭만")
        self.assertEqual(self.stored(), ("루트비히 판 베토벤", 1770, None))
        self.assertEqual(self.stored(self.chopin), ("프레데리크 쇼팽", 1810, "19세기"))

        # An empty body changes nothing.
        response = self.patch({})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.stored(), ("루트비히 판 베토벤", 1770, None))

    def test_a_body_that_is_not_an_object_is_400(self):
        for body in ["1770", "[]", '["고전"]', '"고전"', "true", "null"]:
            with self.subTest(body=body):
                response = self.client.patch(
                    self.url, body, content_type="application/json"
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(list(response.json()), ["non_field_errors"])
        self.assertEqual(self.stored(), ("루트비히 판 베토벤", None, None))

    def test_put_post_and_delete_are_not_allowed(self):
        body = {"name": "베토벤", "birth_year": 1770, "era_override": "고전"}
        self.assertEqual(
            self.client.put(self.url, body, format="json").status_code, 405
        )
        self.assertEqual(self.client.delete(self.url).status_code, 405)
        response = self.client.post(reverse("composerlist-list"), body, format="json")
        self.assertEqual(response.status_code, 405)
        self.assertEqual(Composer.objects.count(), 2)
        self.assertEqual(self.stored(), ("루트비히 판 베토벤", None, None))
        allowed = self.client.options(self.url)["Allow"]
        self.assertNotIn("PUT", allowed)
        self.assertIn("PATCH", allowed)

    def test_an_unknown_composer_is_404(self):
        for composer_id in [9999, 2**63]:
            with self.subTest(composer_id=composer_id):
                url = reverse("composerlist-detail", args=[composer_id])
                response = self.patch({"birth_year": 1770}, url)
                self.assertEqual(response.status_code, 404)

    def test_patch_takes_two_queries(self):
        # The composer with its play count, then the UPDATE.
        with self.assertNumQueries(2):
            response = self.patch({"birth_year": 1770, "era_override": "고전"})
        self.assertEqual(response.status_code, 200)
        # A refused body never reaches the UPDATE.
        with self.assertNumQueries(1):
            response = self.patch({"birth_year": 999})
        self.assertEqual(response.status_code, 400)

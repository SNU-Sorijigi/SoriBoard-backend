import datetime

from django.urls import reverse
from rest_framework.test import APITestCase

from apps.time_manage.models import Composer, Music, TimeInfo, TimeMusic

RACHMANINOFF = "세르게이 라흐마니노프"
CONCERTO = "피아노 협주곡 제2번 Op. 18"


class CheckDuplicateTests(APITestCase):
    session_date = datetime.date(2026, 6, 25)

    def setUp(self):
        self.session = TimeInfo.objects.create(
            date=self.session_date, time=1, arrival_time="09:30:00"
        )

    def play(self, title, composer_name=RACHMANINOFF, days_ago=0, time=1):
        composer, _ = Composer.objects.get_or_create(name=composer_name)
        music, _ = Music.objects.get_or_create(composer=composer, title=title)
        info, _ = TimeInfo.objects.get_or_create(
            date=self.session_date - datetime.timedelta(days=days_ago),
            time=time,
            defaults={"arrival_time": "09:30:00"},
        )
        return TimeMusic.objects.create(music=music, time=info, order=1, source="ROON")

    def request(self, title, composer_name=RACHMANINOFF, **params):
        return self.client.get(
            reverse("check-duplicate"),
            {
                "time_id": self.session.id,
                "composer_name": composer_name,
                "title": title,
                **params,
            },
        )

    def duplicates(self, title, composer_name=RACHMANINOFF, **params):
        response = self.request(title, composer_name, **params)
        self.assertEqual(response.status_code, 200)
        return response.json()["duplicates"]

    def test_each_catalogue_matches_the_same_work_written_the_same_way(self):
        for composer_name, played, title, identifier in (
            (RACHMANINOFF, CONCERTO, "Piano Concerto No. 2, op. 18", "op.18"),
            ("쇼팽", "녹턴 Op. 9 No. 2", "Nocturne OP. 9 NO. 2", "op.9no.2"),
            ("바흐", "무반주 첼로 모음곡 BWV 1007", "Cello Suite BWV1007", "bwv1007"),
            ("슈베르트", "피아노 소나타 D. 960", "Piano Sonata d. 960", "d.960"),
            ("모차르트", "교향곡 제40번 K. 550", "Symphony No. 40, K. 550", "k.550"),
            ("베토벤", "안단테 파보리 WoO 57", "Andante favori WoO 57", "woo57"),
            ("퍼셀", "디도와 에네아스 Z. 626", "Dido and Aeneas Z. 626", "z.626"),
            ("헨델", "메시아 HWV 56", "Messiah HWV 56", "hwv56"),
        ):
            with self.subTest(title=title):
                self.play(played, composer_name)
                result = self.duplicates(title, composer_name)
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0]["music_title"], played)
                self.assertEqual(result[0]["matched_identifiers"], [identifier])

    def test_catalog_numbers_match_whatever_their_punctuation_or_spacing(self):
        # matched_identifiers reports the requested title's form, spaces removed.
        for composer_name, played, title, identifier in (
            (RACHMANINOFF, CONCERTO, "Piano Concerto No. 2 Op 18", "op18"),
            ("차이콥스키", "피아노 협주곡 제1번 Op 23", "Op.23", "op.23"),
            ("쇼팽", "녹턴 Op. 9, No. 2", "Nocturne Op.9 No.2", "op.9no.2"),
            ("슈베르트", "피아노 소나타 D. 960", "Piano Sonata D 960", "d960"),
            ("모차르트", "교향곡 제40번 K. 550", "Symphony No. 40 KV 550", "kv550"),
            ("모차르트", "교향곡 제41번 KV 551", "Symphony No. 41 K551", "k551"),
            ("베토벤", "안단테 파보리 WoO. 57", "Andante favori WoO 57", "woo57"),
            ("퍼셀", "디도와 에네아스 Z. 626", "Dido and Aeneas Z 626", "z626"),
        ):
            with self.subTest(title=title):
                self.play(played, composer_name)
                result = self.duplicates(title, composer_name)
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0]["music_title"], played)
                self.assertEqual(result[0]["matched_identifiers"], [identifier])

        # Ignoring punctuation must not merge different numbers.
        for composer_name, title in (
            ("쇼팽", "Op. 92"),
            ("쇼팽", "Op. 9 No. 1"),
            ("모차르트", "KV 55"),
        ):
            with self.subTest(title=title):
                self.assertEqual(self.duplicates(title, composer_name), [])

    def test_lists_every_earlier_play_of_the_work_with_its_session(self):
        self.play(CONCERTO, time=2)
        self.play("Piano Concerto No. 2 (Op. 18)", days_ago=3, time=4)
        self.play("교향곡 제2번 Op. 27", days_ago=1)

        self.assertCountEqual(
            self.duplicates("Piano Concerto No. 2, Op. 18"),
            [
                {
                    "date": "2026-06-25",
                    "time": 2,
                    "music_title": CONCERTO,
                    "composer_name": RACHMANINOFF,
                    "matched_identifiers": ["op.18"],
                },
                {
                    "date": "2026-06-22",
                    "time": 4,
                    "music_title": "Piano Concerto No. 2 (Op. 18)",
                    "composer_name": RACHMANINOFF,
                    "matched_identifiers": ["op.18"],
                },
            ],
        )

    def test_other_numbers_and_other_composers_are_not_flagged(self):
        self.play(CONCERTO)
        self.play("현악 사중주 Op. 18 No. 1", "베토벤")
        for composer_name, title in (
            (RACHMANINOFF, "Op. 180"),
            (RACHMANINOFF, "Op. 1"),
            (RACHMANINOFF, "BWV 18"),
            ("세르게이 프로코피예프", "Op. 18"),
            ("베토벤", "현악 사중주 Op. 18 No. 2"),
        ):
            with self.subTest(composer_name=composer_name, title=title):
                self.assertEqual(self.duplicates(title, composer_name), [])

    def test_composer_name_is_trimmed_like_the_saved_name(self):
        self.play(CONCERTO)
        result = self.duplicates("Op. 18", f"  {RACHMANINOFF} ")
        self.assertEqual([d["music_title"] for d in result], [CONCERTO])

    def test_window_ends_on_the_session_date_and_defaults_to_seven_days(self):
        for days_ago in (-1, 0, 6, 7):
            self.play(CONCERTO, days_ago=days_ago)

        def dates(**params):
            return sorted(d["date"] for d in self.duplicates("Op. 18", **params))

        self.assertEqual(dates(), ["2026-06-19", "2026-06-25"])
        self.assertEqual(dates(days=1), ["2026-06-25"])
        self.assertEqual(dates(days=8), ["2026-06-18", "2026-06-19", "2026-06-25"])

    def test_days_must_be_a_positive_integer(self):
        for days in ("0", "-3", "abc"):
            with self.subTest(days=days):
                self.assertEqual(self.request("Op. 18", days=days).status_code, 400)

    def test_query_count_does_not_grow_with_earlier_plays(self):
        for days_ago in range(5):
            self.play(CONCERTO, days_ago=days_ago)
        with self.assertNumQueries(2):
            self.assertEqual(len(self.duplicates("Op. 18")), 5)

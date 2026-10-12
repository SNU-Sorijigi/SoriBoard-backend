import datetime

from django.urls import reverse
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

    def composer_body(self, composer, plays):
        return {"id": composer.id, "name": composer.name, "num_time_music": plays}

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

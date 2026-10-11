from django.urls import reverse
from rest_framework.test import APITestCase

from apps.time_manage.models import Semester


def semester(year, semester_num):
    return Semester.objects.create(
        year=year, semester_num=semester_num, start_time="09:30", end_time="17:40"
    )


class CheckSemesterTests(APITestCase):
    """학기 관리 asks checksemester/<year>/ which of the year's 1st and 2nd
    semesters exist; the session calendar uses it to find a date's semester."""

    def check(self, year):
        response = self.client.get(reverse("checksemester", args=[year]))
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_lists_the_years_first_and_second_semester(self):
        fall_2025 = semester(2025, 2)
        spring_2026 = semester(2026, 1)
        fall_2026 = semester(2026, 2)

        self.assertEqual(self.check(2026), [spring_2026.id, fall_2026.id])
        self.assertEqual(self.check(2025), [None, fall_2025.id])
        self.assertEqual(self.check(2027), [None, None])

    def test_only_the_first_and_second_semester_are_listed(self):
        spring = semester(2026, 1)
        semester(2026, 3)
        semester(2026, 0)
        self.assertEqual(self.check(2026), [spring.id, None])

    def test_the_frontends_url_without_a_slash_works(self):
        spring = semester(2026, 1)
        url = reverse("checksemester", args=[2026])
        response = self.client.get(url.rstrip("/"))
        self.assertRedirects(response, url, status_code=301)
        self.assertEqual(self.client.get(url).json(), [spring.id, None])

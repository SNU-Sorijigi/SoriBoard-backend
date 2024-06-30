from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from apps.time_manage.models import *


class UserTests(APITestCase):
    def test_create_user(self):
        url = reverse("user-list")
        data = {
            "name": "John Doe",
            "major": "Computer Science",
            "year_id": "20",
            "is_ob": False,
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(User.objects.get().name, "John Doe")

    def test_update_user(self):
        user = User.objects.create(
            name="John Doe", major="Computer Science", year_id="20", is_ob=False
        )
        url = reverse("user-detail", args=[user.id])
        data = {
            "name": "Jane Doe",
            "major": "Electrical Engineering",
            "year_id": "21",
            "is_ob": True,
        }
        response = self.client.put(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        user.refresh_from_db()
        self.assertEqual(user.name, "Jane Doe")

    def test_delete_user(self):
        user = User.objects.create(
            name="John Doe", major="Computer Science", year_id="20", is_ob=False
        )
        url = reverse("user-detail", args=[user.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(User.objects.count(), 0)


class SemesterTests(APITestCase):
    def test_create_semester(self):
        url = reverse("semester-list")
        data = {
            "year": 2021,
            "semester_num": 1,
            "total_time": 4,
            "start_time": "09:00:00",
            "end_time": "17:00:00",
            "rest_time": 10,
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Semester.objects.count(), 1)
        self.assertEqual(Semester.objects.get().year, 2021)

    def test_update_semester(self):
        semester = Semester.objects.create(
            year=2021,
            semester_num=1,
            total_time=4,
            start_time="09:00:00",
            end_time="17:00:00",
            rest_time=10,
        )
        url = reverse("semester-detail", args=[semester.id])
        data = {
            "year": 2022,
            "semester_num": 2,
            "total_time": 5,
            "start_time": "08:00:00",
            "end_time": "18:00:00",
            "rest_time": 15,
        }
        response = self.client.put(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        semester.refresh_from_db()
        self.assertEqual(semester.year, 2022)

    def test_delete_semester(self):
        semester = Semester.objects.create(
            year=2021,
            semester_num=1,
            total_time=4,
            start_time="09:00:00",
            end_time="17:00:00",
            rest_time=10,
        )
        url = reverse("semester-detail", args=[semester.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Semester.objects.count(), 0)

    def test_create_timetable_when_semester_created(self):
        url = reverse("semester-list")
        data = {
            "year": 2021,
            "semester_num": 1,
            "total_time": 4,
            "start_time": "09:00:00",
            "end_time": "17:00:00",
            "rest_time": 10,
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Timetable.objects.count(), 1)
        self.assertEqual(Timetable.objects.get().semester.year, 2021)

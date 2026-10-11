from django.urls import reverse
from rest_framework.test import APITestCase

from apps.time_manage.models import Semester, Timetable, TimetableUnit, User


class SemesterTimetableTests(APITestCase):
    """A semester comes with its timetable: one cell per weekday and 타임, and a
    table mapping each weekday and 타임 to its cell. Changing the 타임 count
    rebuilds the cells."""

    # What the semester settings pages send.
    create_body = {
        "year": 2026,
        "total_time": 4,
        "semester_num": 2,
        "start_time": "09:30",
        "end_time": "17:40",
        "rest_time": 10,
    }
    edit_body = {
        "total_time": 4,
        "start_time": "09:30",
        "end_time": "17:40",
        "rest_time": 10,
    }

    def setUp(self):
        self.jigi = User.objects.create(name="김지기", major="음악학과", year_id="22")
        self.mentee = User.objects.create(name="박견습", major="경제학부", year_id="25")

    def create_semester(self):
        response = self.client.post(
            reverse("semester-list"), self.create_body, format="json"
        )
        self.assertEqual(response.status_code, 201)
        return Semester.objects.get(pk=response.json()["id"])

    def cells(self, semester):
        return list(
            TimetableUnit.objects.filter(timetable=semester.timetable).order_by("id")
        )

    def assertGrid(self, semester, total_time):
        """One cell per weekday and 타임, ids in weekday-then-타임 order, and a
        table that maps each to its cell."""
        cells = self.cells(semester)
        self.assertEqual(
            [(cell.day, cell.time) for cell in cells],
            [(day, time) for day in range(7) for time in range(1, total_time + 1)],
        )
        self.assertEqual(
            Timetable.objects.get(semester=semester).table,
            {
                str(day): {str(cell.time): cell.id for cell in cells if cell.day == day}
                for day in range(7)
            },
        )
        return cells

    def assign(self, cell):
        cell.users.set([self.jigi])
        cell.mentees.set([self.mentee])

    def test_creating_a_semester_builds_its_timetable(self):
        semester = self.create_semester()
        self.assertGrid(semester, 4)

        response = self.client.get(reverse("semester-detail", args=[semester.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["timetable_id"], semester.timetable.id)

    def test_changing_the_time_count_rebuilds_the_cells(self):
        semester = self.create_semester()
        old_ids = [cell.id for cell in self.cells(semester)]
        self.assign(
            TimetableUnit.objects.get(timetable=semester.timetable, day=1, time=2)
        )

        for total_time in (5, 3):
            with self.subTest(total_time=total_time):
                response = self.client.put(
                    reverse("semester-detail", args=[semester.id]),
                    {**self.edit_body, "total_time": total_time},
                    format="json",
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.json(),
                    {
                        "id": semester.id,
                        "timetable_id": semester.timetable.id,
                        "year": 2026,
                        "semester_num": 2,
                        "total_time": total_time,
                        "start_time": "09:30:00",
                        "end_time": "17:40:00",
                        "rest_time": 10,
                    },
                )
                semester.refresh_from_db()
                self.assertEqual(semester.total_time, total_time)
                cells = self.assertGrid(semester, total_time)

                # New cells, empty: the old ones and their 지기/견습 are gone.
                self.assertGreater(cells[0].id, max(old_ids))
                self.assertFalse(TimetableUnit.objects.filter(id__in=old_ids).exists())
                for cell in cells:
                    self.assertEqual(list(cell.users.all()), [])
                    self.assertEqual(list(cell.mentees.all()), [])
                old_ids = [cell.id for cell in cells]

    def test_an_edit_that_keeps_the_time_count_keeps_the_cells(self):
        semester = self.create_semester()
        cells = self.cells(semester)
        self.assign(cells[5])

        for body in (
            {**self.edit_body, "end_time": "18:00", "rest_time": 15},
            {"rest_time": 5},
        ):
            with self.subTest(body=body):
                response = self.client.put(
                    reverse("semester-detail", args=[semester.id]),
                    body,
                    format="json",
                )
                self.assertEqual(response.status_code, 200)
                semester.refresh_from_db()
                self.assertEqual(self.assertGrid(semester, 4), cells)
                self.assertEqual(list(cells[5].users.all()), [self.jigi])
                self.assertEqual(list(cells[5].mentees.all()), [self.mentee])

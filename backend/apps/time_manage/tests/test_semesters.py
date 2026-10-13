from django.urls import reverse
from rest_framework.test import APITestCase

from apps.time_manage.models import Semester, Timetable, TimetableUnit, User


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

    def test_reads_both_semesters_in_one_query(self):
        spring = semester(2026, 1)
        fall = semester(2026, 2)
        with self.assertNumQueries(1):
            self.assertEqual(self.check(2026), [spring.id, fall.id])

    def test_a_year_past_sqlites_integers_has_no_semesters(self):
        # SQLite stores 64-bit integers; binding a bigger year was a 500.
        semester(2026, 1)
        self.assertEqual(self.check(2**63 - 1), [None, None])
        for year in [2**63, 10**30]:
            with self.subTest(year=year), self.assertNumQueries(0):
                self.assertEqual(self.check(year), [None, None])


class SemesterBoundsTests(APITestCase):
    """A semester is the 1st or 2nd of a year, with at least one 타임 a day
    and at most one a minute. Anything else could not be shown or used, so it
    is refused."""

    # What 학기 생성 and 학기 수정 send.
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
    out_of_range = [
        ("semester_num", 0),
        ("semester_num", 3),
        ("semester_num", -1),
        ("total_time", 0),
        ("total_time", -3),
        # More than one 타임 a minute. Each 타임 is 7 timetable cells, so a
        # mistyped count (4000000) made the save build them for minutes, or
        # for ever. Larger values are left out: they hung without the bound.
        ("total_time", 24 * 60 + 1),
        ("year", 0),
        ("year", -2026),
        ("year", 9999),
        ("year", 20266),
        ("year", int("9" * 25)),
        # Past SQLite's 64-bit INTEGER the save raised OverflowError (500).
        ("rest_time", 2**63),
        ("rest_time", -(2**63) - 1),
        ("rest_time", 10**30),
    ]

    def create(self, **changes):
        return self.client.post(
            reverse("semester-list"), {**self.create_body, **changes}, format="json"
        )

    def edit(self, semester, **changes):
        return self.client.put(
            reverse("semester-detail", args=[semester.id]),
            {**self.edit_body, **changes},
            format="json",
        )

    def test_a_semester_out_of_range_is_400_and_not_created(self):
        for field, value in self.out_of_range:
            with self.subTest(field=field, value=value):
                response = self.create(**{field: value})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(list(response.json()), [field])
                self.assertFalse(Semester.objects.exists())

    def test_an_edit_out_of_range_is_400_and_keeps_the_timetable(self):
        saved = Semester.objects.get(pk=self.create().json()["id"])
        jigi = User.objects.create(name="김지기", major="음악학과", year_id="22")
        mentee = User.objects.create(name="박견습", major="경제학부", year_id="25")
        cell = TimetableUnit.objects.get(timetable=saved.timetable, day=1, time=2)
        cell.users.set([jigi])
        cell.mentees.set([mentee])
        cells = list(TimetableUnit.objects.filter(timetable=saved.timetable))
        table = saved.timetable.table

        for field, value in self.out_of_range:
            with self.subTest(field=field, value=value):
                response = self.edit(saved, **{field: value})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(list(response.json()), [field])
                semester = Semester.objects.get(pk=saved.pk)
                self.assertEqual(
                    (
                        semester.year,
                        semester.semester_num,
                        semester.total_time,
                        semester.rest_time,
                    ),
                    (2026, 2, 4, 10),
                )
                self.assertEqual(
                    list(TimetableUnit.objects.filter(timetable=saved.timetable)),
                    cells,
                )
                self.assertEqual(Timetable.objects.get(semester=saved).table, table)
                self.assertEqual(list(cell.users.all()), [jigi])
                self.assertEqual(list(cell.mentees.all()), [mentee])

    def test_the_bounds_themselves_are_accepted(self):
        for changes in (
            {"year": 1, "semester_num": 1, "total_time": 1, "rest_time": -(2**63)},
            {"year": 9998, "semester_num": 2, "total_time": 1, "rest_time": 2**63 - 1},
        ):
            with self.subTest(**changes):
                response = self.create(**changes)
                self.assertEqual(response.status_code, 201)
                semester = Semester.objects.get(pk=response.json()["id"])
                self.assertEqual(semester.rest_time, changes["rest_time"])
                self.assertEqual(
                    TimetableUnit.objects.filter(timetable=semester.timetable).count(),
                    7,
                )

        # One 타임 a minute: a full grid of 7 × 1440 cells, created and edited.
        response = self.create(year=2027, total_time=24 * 60)
        self.assertEqual(response.status_code, 201)
        semester = Semester.objects.get(pk=response.json()["id"])
        self.assertEqual(semester.timetable.units.count(), 7 * 24 * 60)
        self.assertEqual(len(semester.timetable.table["6"]), 24 * 60)
        response = self.edit(semester, total_time=24 * 60 - 1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(semester.timetable.units.count(), 7 * (24 * 60 - 1))
        response = self.edit(semester, total_time=24 * 60)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(semester.timetable.units.count(), 7 * 24 * 60)

        # The last year whose 2nd semester the stats can still read.
        last = Semester.objects.get(year=9998)
        response = self.client.get(reverse("stats-summary"), {"semester_id": last.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["filters"]["end"], "9999-02-28")

    def test_a_semester_saved_before_can_still_be_edited(self):
        # 학기 수정 sends neither the year nor the semester number.
        old = semester(2026, 3)
        response = self.edit(old, total_time=5)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["semester_num"], 3)
        self.assertEqual(response.json()["total_time"], 5)


class SemesterReadTests(APITestCase):
    """semester/ and semester/<id>/ show each semester with its timetable's id;
    the session calendar and 학기 관리 read the timetable through it."""

    def body(self, semester, timetable_id):
        return {
            "id": semester.id,
            "year": semester.year,
            "semester_num": semester.semester_num,
            "total_time": 4,
            "start_time": "09:30:00",
            "end_time": "17:40:00",
            "rest_time": 10,
            "timetable_id": timetable_id,
        }

    def test_list_and_detail_show_the_timetable_id(self):
        spring = semester(2026, 1)
        fall = semester(2026, 2)

        response = self.client.get(reverse("semester-list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            sorted(response.json(), key=lambda row: row["id"]),
            [
                self.body(spring, spring.timetable.id),
                self.body(fall, fall.timetable.id),
            ],
        )

        response = self.client.get(reverse("semester-detail", args=[fall.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.body(fall, fall.timetable.id))

    def test_the_list_and_detail_take_one_query(self):
        first = semester(2020, 1)
        for count in (1, 6):
            while Semester.objects.count() < count:
                semester(2020 + Semester.objects.count(), 2)
            with self.subTest(semesters=count):
                with self.assertNumQueries(1):
                    response = self.client.get(reverse("semester-list"))
                self.assertEqual(len(response.json()), count)
        with self.assertNumQueries(1):
            response = self.client.get(reverse("semester-detail", args=[first.id]))
        self.assertEqual(response.json()["timetable_id"], first.timetable.id)

    def test_a_semester_without_a_timetable_shows_none(self):
        # DELETE timetable/<id>/ (or the admin) can remove it; that was a 500.
        kept = semester(2026, 1)
        lost = semester(2026, 2)
        Timetable.objects.filter(semester=lost).delete()

        response = self.client.get(reverse("semester-list"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            sorted(response.json(), key=lambda row: row["id"]),
            [self.body(kept, kept.timetable.id), self.body(lost, None)],
        )
        response = self.client.get(reverse("semester-detail", args=[lost.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.body(lost, None))

    def test_an_edit_rebuilds_a_missing_timetable(self):
        # 학기 수정, with the same 타임 count and with another one.
        for total_time in (4, 2):
            with self.subTest(total_time=total_time):
                lost = semester(2020 + total_time, 2)
                Timetable.objects.filter(semester=lost).delete()
                response = self.client.put(
                    reverse("semester-detail", args=[lost.id]),
                    {"total_time": total_time, "rest_time": 10},
                    format="json",
                )
                self.assertEqual(response.status_code, 200)
                timetable = Timetable.objects.get(semester=lost)
                self.assertEqual(response.json()["timetable_id"], timetable.id)
                cells = list(TimetableUnit.objects.filter(timetable=timetable))
                self.assertEqual(
                    sorted((cell.day, cell.time) for cell in cells),
                    [(d, t) for d in range(7) for t in range(1, total_time + 1)],
                )
                self.assertEqual(
                    timetable.table,
                    {
                        str(day): {str(c.time): c.id for c in cells if c.day == day}
                        for day in range(7)
                    },
                )

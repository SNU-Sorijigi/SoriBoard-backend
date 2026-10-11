from django.urls import reverse
from rest_framework.test import APITestCase

from apps.time_manage.models import Semester, TimetableUnit, User


class TimetableUnitTests(APITestCase):
    """The semester timetable: timetable/<id>/ maps each weekday and slot to a
    cell, and the page fetches each cell from timetableunit/<id>/."""

    def setUp(self):
        self.semester = Semester.objects.create(
            year=2026,
            semester_num=2,
            total_time=4,
            start_time="09:30:00",
            end_time="17:40:00",
        )
        self.timetable = self.semester.timetable
        self.jigi = User.objects.create(
            name="김지기", major="음악학과", year_id="22", join_year=2022
        )
        self.senior = User.objects.create(
            name="이선배", major="물리학과", year_id="21", join_year=2021
        )
        self.mentee = User.objects.create(
            name="박견습", major="경제학부", year_id="25", join_year=2025
        )
        self.other = User.objects.create(
            name="최지기", major="작곡과", year_id="23", join_year=2023
        )
        self.cell = self.cell_at(day=1, time=2)
        self.cell.users.set([self.senior, self.jigi])
        self.cell.mentees.set([self.mentee])

    def cell_at(self, day, time):
        return TimetableUnit.objects.get(timetable=self.timetable, day=day, time=time)

    def body(self, cell, jigis=(), mentees=()):
        # Newest 지기 first (User.Meta.ordering), in the ids and the info alike.
        return {
            "id": cell.id,
            "jigi_info": [f"{u.name} {u.major} {u.year_id}" for u in jigis],
            "mentee_info": [f"{m.name} {m.major} {m.year_id}" for m in mentees],
            "day": cell.day,
            "time": cell.time,
            "timetable": self.timetable.id,
            "users": [u.id for u in jigis],
            "mentees": [m.id for m in mentees],
        }

    def test_timetable_maps_every_weekday_and_slot_to_a_cell(self):
        response = self.client.get(
            reverse("timetable-detail", args=[self.timetable.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "id": self.timetable.id,
                "table": {
                    str(day): {
                        str(time): self.cell_at(day, time).id for time in range(1, 5)
                    }
                    for day in range(7)
                },
                "semester": self.semester.id,
            },
        )

    def test_a_cell_lists_its_jigis_and_mentees(self):
        response = self.client.get(reverse("timetableunit-detail", args=[self.cell.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            self.body(self.cell, [self.jigi, self.senior], [self.mentee]),
        )
        self.assertEqual(
            response.json()["jigi_info"], ["김지기 음악학과 22", "이선배 물리학과 21"]
        )

    def test_an_empty_cell(self):
        empty = self.cell_at(day=3, time=4)
        response = self.client.get(reverse("timetableunit-detail", args=[empty.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.body(empty))

    def test_editing_a_cell_changes_and_clears_its_jigis_and_mentees(self):
        url = reverse("timetableunit-detail", args=[self.cell.id])
        # What timetableunit.svelte sends: the cell as read, with the new ids.
        edit = {"day": 1, "time": 2, "timetable": self.timetable.id}

        response = self.client.put(
            url,
            {
                **edit,
                "users": [self.jigi.id, self.other.id],
                "mentees": [self.mentee.id],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        changed = self.body(self.cell, [self.other, self.jigi], [self.mentee])
        self.assertEqual(response.json(), changed)
        self.assertEqual(self.client.get(url).json(), changed)

        response = self.client.put(
            url, {**edit, "users": [], "mentees": []}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.body(self.cell))
        self.assertEqual(self.client.get(url).json(), self.body(self.cell))

        # The cell keeps its place in the timetable.
        table = self.client.get(
            reverse("timetable-detail", args=[self.timetable.id])
        ).json()["table"]
        self.assertEqual(table["1"]["2"], self.cell.id)

    def table(self):
        return self.client.get(
            reverse("timetable-detail", args=[self.timetable.id])
        ).json()["table"]

    def test_a_deleted_cell_can_be_added_back_in_its_slot(self):
        gone = self.cell_at(day=3, time=4)
        response = self.client.delete(reverse("timetableunit-detail", args=[gone.id]))
        self.assertEqual(response.status_code, 204)
        self.assertIsNone(self.table()["3"]["4"])

        response = self.client.post(
            reverse("timetableunit-list"),
            {
                "day": 3,
                "time": 4,
                "timetable": self.timetable.id,
                "users": [self.other.id],
                "mentees": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        added = self.cell_at(day=3, time=4)
        self.assertEqual(response.json(), self.body(added, [self.other]))
        self.assertEqual(self.table()["3"]["4"], added.id)

    def test_a_cell_cannot_take_another_cells_slot(self):
        table = self.table()
        response = self.client.put(
            reverse("timetableunit-detail", args=[self.cell.id]),
            {
                "day": 3,
                "time": 4,
                "timetable": self.timetable.id,
                "users": [self.other.id],
                "mentees": [],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(list(response.json()), ["non_field_errors"])
        self.cell.refresh_from_db()
        self.assertEqual((self.cell.day, self.cell.time), (1, 2))
        self.assertEqual(list(self.cell.users.all()), [self.jigi, self.senior])
        self.assertEqual(self.table(), table)

    def test_a_cell_outside_the_timetable_is_400_and_not_saved(self):
        # Weekdays 0 to 6, 타임 1 to the semester's 4.
        url = reverse("timetableunit-detail", args=[self.cell.id])
        edit = {"day": 1, "time": 2, "timetable": self.timetable.id}
        table = self.table()
        for field, value in [
            ("day", -1),
            ("day", 7),
            ("time", 0),
            ("time", 5),
            ("time", int("9" * 25)),
        ]:
            for method, body in [
                ("put", {**edit, field: value, "users": [self.other.id]}),
                ("patch", {field: value}),
            ]:
                with self.subTest(method=method, field=field, value=value):
                    response = getattr(self.client, method)(url, body, format="json")
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(list(response.json()), [field])
                    self.cell.refresh_from_db()
                    self.assertEqual((self.cell.day, self.cell.time), (1, 2))
                    self.assertEqual(
                        list(self.cell.users.all()), [self.jigi, self.senior]
                    )
                    self.assertEqual(self.table(), table)
        self.assertEqual(
            self.client.patch(url, {"time": 5}, format="json").json(),
            {"time": ["Ensure this value is less than or equal to 4."]},
        )

        # Every cell can still be edited.
        other_cell = self.cell_at(day=3, time=4)
        response = self.client.put(
            reverse("timetableunit-detail", args=[other_cell.id]),
            {
                "day": 3,
                "time": 4,
                "timetable": self.timetable.id,
                "users": [self.other.id],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), self.body(other_cell, [self.other]))

    def test_a_new_cell_outside_the_timetable_is_400_and_not_created(self):
        for field, value in [("day", 7), ("time", 5)]:
            with self.subTest(field=field, value=value):
                response = self.client.post(
                    reverse("timetableunit-list"),
                    {"day": 3, "time": 4, "timetable": self.timetable.id, field: value},
                    format="json",
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(list(response.json()), [field])
                self.assertEqual(
                    TimetableUnit.objects.filter(timetable=self.timetable).count(),
                    7 * 4,
                )

    def test_a_cell_moved_to_another_timetable_must_fit_its_times(self):
        longer = Semester.objects.create(
            year=2027,
            semester_num=1,
            total_time=5,
            start_time="09:30:00",
            end_time="17:40:00",
        )
        last = TimetableUnit.objects.get(timetable=longer.timetable, day=0, time=5)
        url = reverse("timetableunit-detail", args=[last.id])
        for method, body in [
            ("put", {"day": 0, "time": 5, "timetable": self.timetable.id}),
            ("patch", {"timetable": self.timetable.id}),
        ]:
            with self.subTest(method=method):
                response = getattr(self.client, method)(url, body, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    response.json(),
                    {"time": ["Ensure this value is less than or equal to 4."]},
                )
                last.refresh_from_db()
                self.assertEqual(last.timetable, longer.timetable)

    def test_the_first_and_last_weekday_and_time_are_accepted(self):
        for day, time in [(0, 1), (6, 4)]:
            with self.subTest(day=day, time=time):
                cell = self.cell_at(day, time)
                response = self.client.put(
                    reverse("timetableunit-detail", args=[cell.id]),
                    {
                        "day": day,
                        "time": time,
                        "timetable": self.timetable.id,
                        "users": [self.other.id],
                        "mentees": [self.mentee.id],
                    },
                    format="json",
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.json(), self.body(cell, [self.other], [self.mentee])
                )
        # An edit that sends only the 지기 keeps the cell's place.
        response = self.client.patch(
            reverse("timetableunit-detail", args=[self.cell.id]),
            {"users": [self.other.id]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), self.body(self.cell, [self.other], [self.mentee])
        )
        self.assertEqual(self.table()["1"]["2"], self.cell.id)

    def test_lists_every_cell(self):
        late = self.cell_at(day=5, time=4)
        late.mentees.set([self.other])

        response = self.client.get(reverse("timetableunit-list"))
        self.assertEqual(response.status_code, 200)
        cells = {cell["id"]: cell for cell in response.json()}
        self.assertEqual(len(cells), 7 * 4)
        self.assertEqual(
            cells.pop(self.cell.id),
            self.body(self.cell, [self.jigi, self.senior], [self.mentee]),
        )
        self.assertEqual(cells.pop(late.id), self.body(late, mentees=[self.other]))
        for cell in TimetableUnit.objects.exclude(id__in=[self.cell.id, late.id]):
            self.assertEqual(cells.pop(cell.id), self.body(cell))

    def test_reads_a_cell_or_every_cell_in_three_queries(self):
        for cell in TimetableUnit.objects.exclude(id=self.cell.id)[:15]:
            cell.users.set([self.other, self.jigi])
            cell.mentees.set([self.mentee])
        # The cells, their 지기, their 견습.
        with self.assertNumQueries(3):
            response = self.client.get(
                reverse("timetableunit-detail", args=[self.cell.id])
            )
        self.assertEqual(
            response.json(),
            self.body(self.cell, [self.jigi, self.senior], [self.mentee]),
        )
        with self.assertNumQueries(3):
            response = self.client.get(reverse("timetableunit-list"))
        self.assertEqual(len(response.json()), 7 * 4)
        self.assertEqual(sum(len(cell["users"]) for cell in response.json()), 32)

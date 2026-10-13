from rest_framework import generics, viewsets, status, serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from collections.abc import Mapping
import datetime
import re
from .models import *
from .serializers import *
from django.db import transaction
from django.db.models import Count, prefetch_related_objects
from django.http import Http404


def get_object_or_404(queryset, *filter_args, **filter_kwargs):
    """DRF's get_object_or_404 (a malformed pk is 404 too), and a 404 for an
    id past SQLite's 64-bit INTEGER: the driver raised OverflowError (500)."""
    try:
        return generics.get_object_or_404(queryset, *filter_args, **filter_kwargs)
    except OverflowError:
        raise Http404


class SQLiteIdMixin:
    """The same 404 for the router viewsets' detail routes."""

    def get_object(self):
        try:
            return super().get_object()
        except OverflowError:
            raise Http404


_CATALOG_PATTERNS = [
    # Op. 55, Op. 55 No. 1, and Op.55-1 (Korean listings' short form of No. 1)
    r"Op\.?\s*\d+(?:\s*,?\s*No\.?\s*\d+|-\d+\b)?",
    r"BWV\.?\s*\d+[a-z]?",  # BWV 147, BWV.147, BWV 147a
    r"\bD[.\s]\s*\d{3,}\b",  # D. 960 (Schubert, ≥3 digits)
    r"\bKV?\.?\s*\d+\b",  # K. 550, KV 550 (Mozart)
    r"WoO\.?\s*\d+",  # WoO 80 (Beethoven)
    r"\bZ\.?\s*\d+\b",  # Z. 340 (Purcell)
    r"HWV\.?\s*\d+",  # HWV 56, HWV.56 (Handel)
]


def extract_catalog_ids(title):
    """Map the catalog identifiers in a music title to their normalized form.

    Keys ignore dots and commas, read KV as K and "-" as No., so "Op. 18",
    "Op 18" and "op.18" (or "K. 550" and "KV 550", or "Op.9-2" and
    "Op. 9 No. 2") match as the same work.
    """
    ids = {}
    for pattern in _CATALOG_PATTERNS:
        for match in re.finditer(pattern, title, re.IGNORECASE):
            normalized = re.sub(r"\s+", "", match.group().lower()).rstrip(".")
            key = re.sub(r"^kv", "k", re.sub(r"[.,]", "", normalized))
            key = key.replace("-", "no")
            ids.setdefault(key, normalized)
    return ids


class UserViewSet(SQLiteIdMixin, viewsets.ModelViewSet):
    # sabu_info spells out each user's 사부.
    queryset = User.objects.select_related("sabu_id")
    serializer_class = UserSerializer

    def perform_destroy(self, instance):
        # sabu_id cascades, so deleting a 사부 deleted every 제자 below them
        # (and their places in sessions). Keep the 제자, without a 사부.
        with transaction.atomic():
            instance.jejas.update(sabu_id=None)
            instance.delete()


class SemesterViewSet(viewsets.ViewSet):
    # Each semester shows its timetable's id: one query, not one per semester.
    def list(self, request):
        queryset = Semester.objects.select_related("timetable")
        serializer = SemesterSerializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        queryset = Semester.objects.select_related("timetable")
        semester = get_object_or_404(queryset, pk=pk)
        serializer = SemesterSerializer(semester)
        return Response(serializer.data)

    def create(self, request):
        serializer = SemesterSerializer(data=request.data)
        if serializer.is_valid():
            instance = serializer.save()
            return Response({"id": instance.id}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None):
        semester = get_object_or_404(Semester, pk=pk)
        serializer = SemesterSerializer(semester, data=request.data, partial=True)
        if serializer.is_valid():
            semester = serializer.save()
            return Response(SemesterSerializer(semester).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None):
        semester = get_object_or_404(Semester, pk=pk)
        semester.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_by_year_and_semester(self, request):
        year = request.query_params.get("year")
        semester = request.query_params.get("semester")
        if year and semester:
            queryset = Semester.objects.filter(year=year, semester=semester).first()
            return Response({"id": queryset.id if queryset else None})
        return Response(status=status.HTTP_400_BAD_REQUEST)


class TimetableViewSet(SQLiteIdMixin, viewsets.ModelViewSet):
    queryset = Timetable.objects.all()
    serializer_class = TimetableSerializer


class TimetableUnitViewSet(SQLiteIdMixin, viewsets.ModelViewSet):
    queryset = TimetableUnit.objects.all()
    serializer_class = TimetableUnitSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action in ("list", "retrieve"):
            # A cell shows its 지기 and 견습 twice: as ids and as info.
            # Writes prefetch after saving instead (below).
            queryset = queryset.prefetch_related("users", "mentees")
        return queryset

    def perform_create(self, serializer):
        cell = serializer.save()
        # The answer shows the 지기 and 견습 twice too: 2 queries, not 4.
        prefetch_related_objects([cell], "users", "mentees")

    def update(self, request, *args, **kwargs):
        # DRF's update() would drop a prefetch made in perform_update().
        partial = kwargs.pop("partial", False)
        serializer = self.get_serializer(
            self.get_object(), data=request.data, partial=partial
        )
        serializer.is_valid(raise_exception=True)
        cell = serializer.save()
        prefetch_related_objects([cell], "users", "mentees")
        return Response(serializer.data)


def with_legacy_single_fields(data):
    """A session write's body, with the legacy single user and mentee as lists."""
    # A body that is not a JSON object goes to the serializer as it is, which
    # refuses it with 400; copying it here raised AttributeError (500).
    if not isinstance(data, Mapping):
        return data
    data = data.copy()
    # Backward-compat: coerce single fields to arrays
    if "user" in data and "users" not in data:
        u = data.get("user")
        data["users"] = [u] if u else []
    if "mentee" in data and "mentees" not in data:
        m = data.get("mentee")
        data["mentees"] = [m] if m else []
    return data


class TimeInfoViewSet(viewsets.ViewSet):
    def list(self, request):
        # A blank date or time is a missing one. Both were answered with an
        # empty 400; now the 400 names them, as it names malformed ones.
        params = {
            name: request.query_params[name]
            for name in ("date", "time")
            if request.query_params.get(name)
        }
        lookup = TimeInfoLookupSerializer(data=params)
        lookup.is_valid(raise_exception=True)
        queryset = TimeInfo.objects.filter(**lookup.validated_data).first()
        return Response({"id": queryset.id if queryset else None})

    def retrieve(self, request, pk=None):
        # users and mentees are each read three ways by the serializer.
        queryset = TimeInfo.objects.prefetch_related("users", "mentees")
        timeinfo = get_object_or_404(queryset, pk=pk)
        serializer = TimeInfoDetailSerializer(timeinfo)
        return Response(serializer.data)

    def create(self, request):
        data = with_legacy_single_fields(request.data)
        serializer = TimeInfoSerializer(data=data)
        if serializer.is_valid():
            # Saves users/mentees too, from the validated ids.
            instance = serializer.save()
            return Response({"id": instance.id}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None):
        time_info = get_object_or_404(TimeInfo, pk=pk)
        data = with_legacy_single_fields(request.data)
        serializer = TimeInfoSerializer(time_info, data=data, partial=True)
        if serializer.is_valid():
            # Saves users/mentees too, from the validated ids.
            time_info = serializer.save()
            # The answer reads users and mentees three ways each: 2 queries, not 6.
            prefetch_related_objects([time_info], "users", "mentees")
            return Response(TimeInfoSerializer(time_info).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None):
        time_info = get_object_or_404(TimeInfo, pk=pk)
        time_info.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TimeMusicViewSet(viewsets.ViewSet):
    def create(self, request):
        serializer = TimeMusicSerializer(data=request.data)
        if serializer.is_valid():
            time_music = serializer.save()
            return Response(
                TimeMusicSerializer(time_music).data, status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None):
        time_music = get_object_or_404(TimeMusic, pk=pk)
        serializer = TimeMusicSerializer(time_music, data=request.data, partial=True)
        if serializer.is_valid():
            time_music = serializer.save()
            return Response(TimeMusicSerializer(time_music).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None):
        time_music = get_object_or_404(TimeMusic, pk=pk)
        time_music.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CheckSemesterInfoAPIView(APIView):
    def get(self, request, year):
        # Past SQLite's 64-bit INTEGER the driver raises OverflowError (500);
        # no semester can have such a year.
        if year > 2**63 - 1:
            return Response([None, None])

        # Both semesters in one query; (year, semester_num) is unique.
        semester_ids = dict(
            Semester.objects.filter(year=year, semester_num__in=[1, 2]).values_list(
                "semester_num", "id"
            )
        )
        return Response([semester_ids.get(sem) for sem in [1, 2]])


# A century of days, checktime/ lists at most.
CHECKTIME_MAX_DAYS = 36600


class CheckTimeInfoAPIView(APIView):
    def get(
        self, request, start_year, start_month, start_day, end_year, end_month, end_day
    ):
        start_date_str = f"{start_year}-{start_month}-{start_day}"
        end_date_str = f"{end_year}-{end_month}-{end_day}"
        try:
            start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except ValueError:
            return Response({"error": "Invalid date format"}, status=400)

        if start_date > end_date:
            return Response({"error": "Start date must be before end date"}, status=400)

        # The answer has a row for each day: 1000-01-01 to 9999-12-31 took
        # 7 s and 0.7 GB for an 89 MB body. The session page asks for at
        # most ten years each way.
        if (end_date - start_date).days >= CHECKTIME_MAX_DAYS:
            return Response(
                {"error": f"The range must be at most {CHECKTIME_MAX_DAYS} days"},
                status=400,
            )

        # One query for the whole range; (time, date) is unique.
        session_ids = {
            (date, time): pk
            for date, time, pk in TimeInfo.objects.filter(
                date__range=(start_date, end_date)
            ).values_list("date", "time", "id")
        }

        times_status = []
        for single_date in (
            start_date + datetime.timedelta(days=n)
            for n in range((end_date - start_date).days + 1)
        ):
            times_status.append(
                [session_ids.get((single_date, time)) for time in range(1, 6)]
            )

        return Response(times_status)


class TimetableAPIView(APIView):
    def get(self, request, semester_id):
        try:
            semester = Semester.objects.get(id=semester_id)
        except Semester.DoesNotExist:
            return Response(
                {"error": "The specified semester does not exist."}, status=404
            )

        semester_users = SemesterUser.objects.filter(semester=semester)
        timetable = [["" for _ in range(semester.total_time)] for _ in range(7)]

        for su in semester_users:
            day = su.day
            time = su.time
            jigi_name = su.user.name
            mentee_name = ""
            if su.mentee:
                mentee_name = su.mentee.name
            if mentee_name != "":
                timetable[day][time] = f"{jigi_name}, {mentee_name}"
            else:
                timetable[day][time] = jigi_name

        return Response(timetable, status=status.HTTP_200_OK)


class SwapOrderView(APIView):
    def post(self, request, upper_id, lower_id, *args, **kwargs):
        with transaction.atomic():
            try:
                time_music_upper = TimeMusic.objects.get(id=upper_id)
                time_music_lower = TimeMusic.objects.get(id=lower_id)
            # OverflowError: an id past SQLite's 64-bit INTEGER (was a 500).
            except (TimeMusic.DoesNotExist, OverflowError):
                return Response(
                    {
                        "error": "One or both of the specified TimeMusic instances do not exist."
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )
            # ↑/↓ moves a play within its session's playlist. Swapped across
            # two sessions, each play took the other's place number in a
            # playlist it is not in.
            if time_music_upper.time_id != time_music_lower.time_id:
                return Response(
                    {"error": "The two plays are in different sessions."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # Plays can share an order (a double-clicked 추가 sends the same
            # one twice); swapping those would move nothing. Number the
            # session 1..n in its listed order first.
            plays = list(
                TimeMusic.objects.filter(time_id=time_music_upper.time_id)
                .only("order")
                .order_by("order", "id")
            )
            if len({play.order for play in plays}) < len(plays):
                for number, play in enumerate(plays, start=1):
                    play.order = number
                TimeMusic.objects.bulk_update(plays, ["order"])
                numbered = {play.id: play.order for play in plays}
                time_music_upper.order = numbered[time_music_upper.id]
                time_music_lower.order = numbered[time_music_lower.id]
            time_music_upper.order, time_music_lower.order = (
                time_music_lower.order,
                time_music_upper.order,
            )
            time_music_upper.save(update_fields=["order"])
            time_music_lower.save(update_fields=["order"])
        return Response({"message": "Order swapped successfully."})


class ComposerViewSet(SQLiteIdMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = ComposerSerializer

    def get_queryset(self):
        return Composer.objects.annotate(
            num_time_music=Count("musics__timemusic")
        ).order_by("-num_time_music")


class MusicViewSet(SQLiteIdMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = MusicSerializer

    def get_queryset(self):
        # Each music shows its composer's name: one query, not one per music.
        return (
            Music.objects.select_related("composer")
            .annotate(num_time_music=Count("timemusic"))
            .order_by("-num_time_music")
        )


class MusicByComposerViewSet(SQLiteIdMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = MusicSerializer

    def get_queryset(self):
        composer_id = self.kwargs["composer_id"]
        # Past SQLite's 64-bit INTEGER the driver raises OverflowError (500);
        # no composer can have such an id.
        if int(composer_id) > 2**63 - 1:
            return Music.objects.none()
        return (
            Music.objects.filter(composer__id=composer_id)
            .select_related("composer")
            .annotate(num_time_music=Count("timemusic"))
            .order_by("-num_time_music")
        )


class NewsViewSet(SQLiteIdMixin, viewsets.ModelViewSet):
    # The TV shows the first news: the oldest, not whichever row comes first.
    queryset = News.objects.order_by("id")
    serializer_class = NewsSerializer


def session_reference_date(request):
    """Use the saved session date, never the browser or server's current date."""
    # Past SQLite's 64-bit INTEGER the driver raises OverflowError (500).
    session_id = serializers.IntegerField(min_value=1, max_value=2**63 - 1)
    time_id = session_id.run_validation(request.query_params.get("time_id"))
    return get_object_or_404(TimeInfo.objects.only("date"), pk=time_id).date


def days_before(date, days):
    """The date `days` days earlier, or 0001-01-01 if that is before it."""
    try:
        return date - datetime.timedelta(days=days)
    except OverflowError:  # past datetime.date.min, or a timedelta too large
        return datetime.date.min


class RecentPlaysView(APIView):
    """Prefix matches from 30 calendar days ending on the selected session date."""

    def get(self, request):
        reference_date = session_reference_date(request)
        composer_prefix = request.query_params.get("composer_name", "").strip()
        title_prefix = request.query_params.get("title", "").strip().casefold()
        if not composer_prefix:
            return Response(
                {
                    "reference_date": reference_date.isoformat(),
                    "composers": [],
                    "works": [],
                }
            )

        week_start = days_before(reference_date, 6)
        month_start = days_before(reference_date, 29)
        plays = (
            TimeMusic.objects.filter(
                music__composer__name__istartswith=composer_prefix,
                time__date__range=(month_start, reference_date),
            )
            .order_by("-time__date", "-time__time", "-order", "-id")
            .values("music__composer__name", "music__title", "time__date")
        )

        # One play-history query for both hints, after resolving the session date.
        # Title input must not narrow composer counts.
        composers = {}
        works = {}
        for play in plays:
            name = play["music__composer__name"]
            title = play["music__title"]
            date = play["time__date"]
            composer = composers.setdefault(
                name,
                {
                    "name": name,
                    "count_1d": 0,
                    "count_7d": 0,
                    "count_30d": 0,
                    "recent_titles": [],
                },
            )
            composer["count_1d"] += int(date == reference_date)
            composer["count_7d"] += int(date >= week_start)
            composer["count_30d"] += 1
            if len(composer["recent_titles"]) < 3:
                composer["recent_titles"].append(title)

            if title_prefix and title.casefold().startswith(title_prefix):
                work = works.setdefault(
                    (name, title),
                    {
                        "composer_name": name,
                        "title": title,
                        "count_30d": 0,
                        "last_played": date.isoformat(),
                        "days_since_last_played": (reference_date - date).days,
                    },
                )
                work["count_30d"] += 1

        return Response(
            {
                "reference_date": reference_date.isoformat(),
                "composers": list(composers.values()),
                "works": list(works.values()),
            }
        )


class CheckDuplicateMusicView(APIView):
    def get(self, request):
        reference_date = session_reference_date(request)
        # Saved composer names are trimmed (CharField), so trim the lookup too.
        composer_name = request.query_params.get("composer_name", "").strip()
        title = request.query_params.get("title", "")
        days = serializers.IntegerField(min_value=1).run_validation(
            request.query_params.get("days", 7)
        )

        new_ids = extract_catalog_ids(title)
        if not new_ids:
            return Response({"duplicates": []})

        cutoff = days_before(reference_date, days - 1)
        # The warning lists the plays newest first, as recent-plays does;
        # unordered, they came back in the order they were added.
        candidates = (
            TimeMusic.objects.filter(
                music__composer__name=composer_name,
                time__date__range=(cutoff, reference_date),
            )
            .select_related("music", "music__composer", "time")
            .order_by("-time__date", "-time__time", "-order", "-id")
        )

        duplicates = []
        for tm in candidates:
            existing_ids = extract_catalog_ids(tm.music.title)
            matched = new_ids.keys() & existing_ids.keys()
            if matched:
                duplicates.append(
                    {
                        "date": str(tm.time.date),
                        "time": tm.time.time,
                        "music_title": tm.music.title,
                        "composer_name": tm.music.composer.name,
                        "matched_identifiers": sorted(new_ids[key] for key in matched),
                    }
                )

        return Response({"duplicates": duplicates})

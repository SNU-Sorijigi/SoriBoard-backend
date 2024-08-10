from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.views import APIView
import datetime
from django.shortcuts import get_object_or_404
from .models import *
from .serializers import *
from django.db.models import Count


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer


class SemesterViewSet(viewsets.ViewSet):
    def list(self, request):
        queryset = Semester.objects.all()
        serializer = SemesterSerializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        queryset = Semester.objects.all()
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
        semester = Semester.objects.get(pk=pk)
        serializer = SemesterSerializer(semester, data=request.data, partial=True)
        if serializer.is_valid():
            semester = serializer.save()
            return Response(SemesterSerializer(semester).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None):
        semester = Semester.objects.get(pk=pk)
        semester.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    def get_by_year_and_semester(self, request):
        year = request.query_params.get("year")
        semester = request.query_params.get("semester")
        if year and semester:
            queryset = Semester.objects.filter(year=year, semester=semester).first()
            return Response({"id": queryset.id if queryset else None})
        return Response(status=status.HTTP_400_BAD_REQUEST)


class TimetableViewSet(viewsets.ModelViewSet):
    queryset = Timetable.objects.all()
    serializer_class = TimetableSerializer


class TimetableUnitViewSet(viewsets.ModelViewSet):
    queryset = TimetableUnit.objects.all()
    serializer_class = TimetableUnitSerializer


class TimeInfoViewSet(viewsets.ViewSet):
    def list(self, request):
        date = request.query_params.get("date")
        time = request.query_params.get("time")
        if date and time:
            queryset = TimeInfo.objects.filter(date=date, time=time).first()
            return Response({"id": queryset.id if queryset else None})
        return Response(status=status.HTTP_400_BAD_REQUEST)

    def retrieve(self, request, pk=None):
        queryset = TimeInfo.objects.all()
        timeinfo = get_object_or_404(queryset, pk=pk)
        serializer = TimeInfoDetailSerializer(timeinfo)
        return Response(serializer.data)

    def create(self, request):
        serializer = TimeInfoSerializer(data=request.data)
        if serializer.is_valid():
            instance = serializer.save()
            return Response({"id": instance.id}, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None):
        time_info = TimeInfo.objects.get(pk=pk)
        serializer = TimeInfoSerializer(time_info, data=request.data, partial=True)
        if serializer.is_valid():
            time_info = serializer.save()
            return Response(TimeInfoSerializer(time_info).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None):
        time_info = TimeInfo.objects.get(pk=pk)
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
        print(serializer.errors)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def update(self, request, pk=None):
        time_music = TimeMusic.objects.get(pk=pk)
        serializer = TimeMusicSerializer(time_music, data=request.data, partial=True)
        if serializer.is_valid():
            time_music = serializer.save()
            return Response(TimeMusicSerializer(time_music).data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def destroy(self, request, pk=None):
        time_music = TimeMusic.objects.get(pk=pk)
        time_music.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CheckSemesterInfoAPIView(APIView):
    def get(self, request, year):
        # serializer = SemesterSerializer(semester, many=True)
        # return Response(serializer.data)

        semester_status = []
        for sem in [1, 2]:
            try:
                semester = Semester.objects.get(year=year, semester_num=sem)
                if semester:
                    semester_status.append(semester.id)
                else:
                    semester_status.append(None)
            except Semester.DoesNotExist:
                semester_status.append(None)

        return Response(semester_status)


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

        times_status = []
        for single_date in (
            start_date + datetime.timedelta(days=n)
            for n in range((end_date - start_date).days + 1)
        ):
            day_status = []
            for time in range(1, 6):
                try:
                    time_info = TimeInfo.objects.filter(
                        date=single_date, time=time
                    ).first()
                    if time_info:
                        day_status.append(time_info.id)
                    else:
                        day_status.append(None)
                except TimeInfo.DoesNotExist:
                    day_status.append(None)
            times_status.append(day_status)

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
        try:
            time_music_upper = TimeMusic.objects.get(id=upper_id)
            time_music_lower = TimeMusic.objects.get(id=lower_id)
        except TimeMusic.DoesNotExist:
            return Response(
                {
                    "error": "One or both of the specified TimeMusic instances do not exist."
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        time_music_upper.order, time_music_lower.order = (
            time_music_lower.order,
            time_music_upper.order,
        )
        time_music_upper.save()
        time_music_lower.save()
        return Response({"message": "Order swapped successfully."})


class ComposerViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ComposerSerializer

    def get_queryset(self):
        return Composer.objects.annotate(
            num_time_music=Count("musics__timemusic")
        ).order_by("-num_time_music")


class MusicViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = MusicSerializer

    def get_queryset(self):
        return Music.objects.annotate(num_time_music=Count("timemusic")).order_by(
            "-num_time_music"
        )


class MusicByComposerViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = MusicSerializer

    def get_queryset(self):
        composer_id = self.kwargs["composer_id"]
        return (
            Music.objects.filter(composer__id=composer_id)
            .annotate(num_time_music=Count("timemusic"))
            .order_by("-num_time_music")
        )

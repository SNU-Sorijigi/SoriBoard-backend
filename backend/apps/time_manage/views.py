from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.views import APIView
import datetime
from django.shortcuts import get_object_or_404
from .models import *
from .serializers import *
from django.db.models import Count


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

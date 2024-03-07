from rest_framework import viewsets, status
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import *
from .serializers import *


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


# 프론트 구조 바꿔야 해서 나중에 변경
"""
class CheckTimeInfoAPIView(APIView):
    def get(self, request, year, month):
        try:
            start_date, end_date = self.get_month_date_range(year, month)
        except ValueError as e:
            return Response({"error": str(e)}, status=400)
        
        month_status = []
        for day in (start_date + datetime.timedelta(days=n) for n in range((end_date - start_date).days + 1)):
            day_status = []
            for time in range(1, 6):
                time_exists = TimeInfo.objects.filter(date=day, time=time).exists()
                day_status.append(time_exists)
            month_status.extend(day_status)
        
        return Response(month_status)

    def get_month_date_range(self, year, month):
        year, month = int(year), int(month)

        if month < 1 or month > 12:
            raise ValueError("Month must be betwen 1 and 12")
        first_day = datetime.date(year, month, 1)
        last_day = datetime.date(year, month, calendar.monthrange(year, month)[1])
        return first_day, last_day
"""

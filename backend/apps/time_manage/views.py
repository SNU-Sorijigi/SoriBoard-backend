from rest_framework import viewsets, status
from rest_framework.views import APIView
import datetime
from rest_framework.response import Response
from rest_framework.decorators import action
from .models import User, SemesterInfo, TimeInfo, MusicInfo, PlayerInfo, ComposerInfo, ConductorInfo, OrchestraInfo, SemesterUserInfo
from .serializers import TimeInfoGetSerializer, UserSerializer, SemesterInfoSerializer, TimeInfoSerializer, MusicInfoSerializer, PlayerInfoSerializer, ComposerInfoSerializer, ConductorInfoSerializer, OrchestraInfoSerializer, SemesterUserInfoSerializer, SemesterUserInfoPostSerializer

class CheckTimeInfoAPIView(APIView):
    def get(self, request, year, month, day, time):
        date_str = f"{year}-{month}-{day}"
        try:
            date_obj = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            return Response({"error": "Invalid date format"}, status=400)

        time_info = TimeInfo.objects.filter(date=date_obj, time=time).first()
        if time_info:
            return Response({"id": time_info.id})
        else:
            return Response({"error": "TimeInfo not found"}, status=404)

class CreateTimeInfoAPIView(APIView):
    def post(self, request, *args, **kwargs):
        serializer = TimeInfoSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class TimeInfoDetailView(APIView):
    def get_object(self, pk):
        try:
            return TimeInfo.objects.get(pk=pk)
        except TimeInfo.DoesNotExist:
            return Response({"error": "TimeInfo not found"}, status=404)

    def get(self, request, pk, format=None):
        time_info = self.get_object(pk)
        serializer = TimeInfoGetSerializer(time_info)
        return Response(serializer.data)
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
class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

class SemesterInfoViewSet(viewsets.ViewSet):

    def list(self, request):
        year = request.query_params.get('year')
        semester = request.query_params.get('semester')
        if year is not None and semester is not None:
            semester_info = SemesterInfo.objects.filter(year=year, semester=semester).first()
            if semester_info:
                serializer = SemesterInfoSerializer(semester_info)
                return Response(serializer.data)
        return Response([])
    
class SemesterInfoPostViewSet(viewsets.ModelViewSet):
    queryset = SemesterInfo.objects.all()
    serializer_class = SemesterInfoSerializer

class SemesterUserInfoViewSet(viewsets.ViewSet):

    def list(self, request):
        year = request.query_params.get('year')
        semester = request.query_params.get('semester')
        if year is not None and semester is not None:
            semester_info = SemesterInfo.objects.filter(year=year, semester=semester).first()
            if semester_info:
                user_semester_infos = SemesterUserInfo.objects.filter(semester_info=semester_info)
                serializer = SemesterUserInfoSerializer(user_semester_infos, many=True)
                return Response(serializer.data)
        return Response([])
    
class SemesterUserInfoPostViewSet(viewsets.ModelViewSet):
    queryset = SemesterUserInfo.objects.all()
    serializer_class = SemesterUserInfoPostSerializer


class TimeInfoViewSet(viewsets.ModelViewSet):
    queryset = TimeInfo.objects.all()
    serializer_class = TimeInfoSerializer

class MusicInfoViewSet(viewsets.ModelViewSet):
    queryset = MusicInfo.objects.all()
    serializer_class = MusicInfoSerializer

class PlayerInfoViewSet(viewsets.ModelViewSet):
    queryset = PlayerInfo.objects.all()
    serializer_class = PlayerInfoSerializer

class ComposerInfoViewSet(viewsets.ModelViewSet):
    queryset = ComposerInfo.objects.all()
    serializer_class = ComposerInfoSerializer

class ConductorInfoViewSet(viewsets.ModelViewSet):
    queryset = ConductorInfo.objects.all()
    serializer_class = ConductorInfoSerializer

class OrchestraInfoViewSet(viewsets.ModelViewSet):
    queryset = OrchestraInfo.objects.all()
    serializer_class = OrchestraInfoSerializer

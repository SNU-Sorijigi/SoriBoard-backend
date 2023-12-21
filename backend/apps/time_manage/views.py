from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from .models import User, SemesterInfo, TimeInfo, MusicInfo, PlayerInfo, ComposerInfo, ConductorInfo, OrchestraInfo, SemesterUserInfo
from .serializers import UserSerializer, SemesterInfoSerializer, TimeInfoSerializer, MusicInfoSerializer, PlayerInfoSerializer, ComposerInfoSerializer, ConductorInfoSerializer, OrchestraInfoSerializer, SemesterUserInfoSerializer, SemesterUserInfoPostSerializer

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

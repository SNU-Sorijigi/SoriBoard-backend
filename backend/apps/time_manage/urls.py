from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CheckTimeInfoAPIView, UserViewSet, SemesterInfoViewSet, TimeInfoViewSet, MusicInfoViewSet, PlayerInfoViewSet, ComposerInfoViewSet, ConductorInfoViewSet, OrchestraInfoViewSet, SemesterUserInfoViewSet, SemesterUserInfoPostViewSet, SemesterInfoPostViewSet

router = DefaultRouter()
router.register(r'users', UserViewSet)

router.register(r'music', MusicInfoViewSet)
router.register(r'player', PlayerInfoViewSet)
router.register(r'semester', SemesterInfoViewSet, basename='semester')
router.register(r'semesterpost', SemesterInfoPostViewSet, basename='semesterpost')
router.register(r'time', TimeInfoViewSet)
router.register(r'composer', ComposerInfoViewSet)
router.register(r'conductor', ConductorInfoViewSet)
router.register(r'orchestra', OrchestraInfoViewSet)
router.register(r'semesteruser', SemesterUserInfoViewSet, basename='semesteruser')
router.register(r'semesteruserpost', SemesterUserInfoPostViewSet, basename='semesteruserpost')

urlpatterns = [
    path('', include(router.urls)),
    path('check-timeinfo/<int:year>/<int:month>/<int:day>/<int:time>', CheckTimeInfoAPIView.as_view(), name='check_timeinfo'),
]
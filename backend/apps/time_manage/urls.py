from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import *

router = DefaultRouter()
router.register(r"timeinfo", TimeInfoViewSet, basename="timeinfo")
router.register(r"timemusic", TimeMusicViewSet, basename="timemusic")
router.register(r"composers", ComposerViewSet, basename="composerlist")
router.register(r"musics", MusicViewSet, basename="musiclist")
router.register(
    r"musics/by-composer/(?P<composer_id>\d+)",
    MusicByComposerViewSet,
    basename="music-by-composer",
)

urlpatterns = [
    path("", include(router.urls)),
    path(
        "checktime/<int:start_year>/<int:start_month>/<int:start_day>/<int:end_year>/<int:end_month>/<int:end_day>/",
        CheckTimeInfoAPIView.as_view(),
        name="checktime",
    ),
    path(
        "swaporder/<int:upper_id>/<int:lower_id>/",
        SwapOrderView.as_view(),
        name="swaporder",
    ),
]

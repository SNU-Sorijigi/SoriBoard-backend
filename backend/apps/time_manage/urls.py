from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import *
from .stats import (
    StatsSummaryView,
    TopComposersStatsView,
    TopWorksStatsView,
    TopConductorsStatsView,
    TopOrchestrasStatsView,
    TopSoloistsStatsView,
    PlaysOverTimeStatsView,
    EraDistributionStatsView,
    GenreDistributionStatsView,
    DiversityStatsView,
)

router = DefaultRouter()
router.register(r"user", UserViewSet, basename="user")
router.register(r"semester", SemesterViewSet, basename="semester")
router.register(r"timetable", TimetableViewSet, basename="timetable")
router.register(r"timetableunit", TimetableUnitViewSet, basename="timetableunit")
router.register(r"timeinfo", TimeInfoViewSet, basename="timeinfo")
router.register(r"timemusic", TimeMusicViewSet, basename="timemusic")
router.register(r"composers", ComposerViewSet, basename="composerlist")
router.register(r"musics", MusicViewSet, basename="musiclist")
router.register(
    r"musics/by-composer/(?P<composer_id>\d+)",
    MusicByComposerViewSet,
    basename="music-by-composer",
)
router.register(r"information", NewsViewSet, basename="information")

urlpatterns = [
    path("", include(router.urls)),
    path(
        "checksemester/<int:year>/",
        CheckSemesterInfoAPIView.as_view(),
        name="checksemester",
    ),
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
    path(
        "check-duplicate/",
        CheckDuplicateMusicView.as_view(),
        name="check-duplicate",
    ),
    path("recent-plays/", RecentPlaysView.as_view(), name="recent-plays"),
    # 통계
    path("stats/summary/", StatsSummaryView.as_view(), name="stats-summary"),
    path("stats/composers/", TopComposersStatsView.as_view(), name="stats-composers"),
    path("stats/works/", TopWorksStatsView.as_view(), name="stats-works"),
    path("stats/soloists/", TopSoloistsStatsView.as_view(), name="stats-soloists"),
    path(
        "stats/conductors/", TopConductorsStatsView.as_view(), name="stats-conductors"
    ),
    path(
        "stats/orchestras/", TopOrchestrasStatsView.as_view(), name="stats-orchestras"
    ),
    path("stats/timeline/", PlaysOverTimeStatsView.as_view(), name="stats-timeline"),
    path("stats/eras/", EraDistributionStatsView.as_view(), name="stats-eras"),
    path("stats/genres/", GenreDistributionStatsView.as_view(), name="stats-genres"),
    path("stats/diversity/", DiversityStatsView.as_view(), name="stats-diversity"),
]

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import *

router = DefaultRouter()
router.register(r"timeinfo", TimeInfoViewSet, basename="timeinfo")
router.register(r"timemusic", TimeMusicViewSet, basename="timemusic")

urlpatterns = [
    path("", include(router.urls)),
    path("checktime/", CheckTimeInfoAPIView.as_view(), name="checktime"),
]

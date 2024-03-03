from django.urls import path
from .consumers import TvDisplayConsumer

websocket_urlpatterns = [
    path("ws/tv_display/", TvDisplayConsumer.as_asgi()),
]

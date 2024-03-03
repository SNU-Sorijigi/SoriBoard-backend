from django.urls import re_path
from .consumers import TvDisplayConsumer

websocket_urlpatterns = [
    re_path(r"ws/tv_display/$", TvDisplayConsumer.as_asgi()),
]

from django.contrib import admin

from .models import (
    User,
    SemesterInfo,
    TimeInfo,
    MusicInfo,
    PlayerInfo,
    ComposerInfo,
    ConductorInfo,
    OrchestraInfo,
    SemesterUserInfo,
)

admin.site.register(User)
admin.site.register(SemesterInfo)
admin.site.register(TimeInfo)
admin.site.register(MusicInfo)
admin.site.register(PlayerInfo)
admin.site.register(ComposerInfo)
admin.site.register(ConductorInfo)
admin.site.register(OrchestraInfo)
admin.site.register(SemesterUserInfo)

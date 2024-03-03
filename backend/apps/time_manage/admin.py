from django.contrib import admin

from .models import *

admin.site.register(User)
admin.site.register(Semester)
admin.site.register(TimeInfo)
admin.site.register(TimeMusic)
admin.site.register(Music)
admin.site.register(Player)
admin.site.register(Composer)
admin.site.register(Conductor)
admin.site.register(Orchestra)
admin.site.register(SemesterUser)

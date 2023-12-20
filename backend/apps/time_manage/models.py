from django.db import models

# 지기 정보
class User(models.Model):
    name = models.CharField(max_length=20) # 이름
    major = models.CharField(max_length=40) # 전공
    year_id = models.CharField(max_length=2) # 학번
    is_ob = models.BooleanField(default=False) # OB 여부
    
    class Meta:
        db_table = 'user'

# 학기 운영 정보
class SemesterInfo(models.Model):
    year = models.IntegerField() # 연도
    semester = models.IntegerField() # 학기
    total_time = models.IntegerField(default=4) # 하루 타임 수 (기본 4)
    start_time = models.TimeField() # 타임 시작 시간 (예: 9시 30분)
    end_time = models.TimeField() # 타임 종료 시간 (예: 17시 40분)
    rest_time = models.IntegerField(default=10) # 쉬는 시간 (기본 10분)

# 학기 - 지기 연결
class SemesterUserInfo(models.Model):
    user = models.ForeignKey('User', on_delete=models.CASCADE, related_name='usersemesterinfo') # 지기
    mentee = models.ForeignKey('User', on_delete=models.CASCADE, related_name='menteesemesterinfo', null=True, blank=True) # 견습 지기
    semester_info = models.ForeignKey('SemesterInfo', on_delete=models.CASCADE, related_name='userinfo') # 학기
    day = models.IntegerField() # 요일
    time = models.IntegerField() # 타임

    class Meta:
        db_table = 'semester_user_info'

# 타임 정보
class TimeInfo(models.Model):
    time = models.IntegerField() # 타임
    date = models.DateField() # 날짜
    SemesterInfo = models.ForeignKey('SemesterInfo', on_delete=models.CASCADE, related_name='timeinfo') # 학기
    user = models.ForeignKey('User', on_delete=models.CASCADE, related_name='time') # 지기
    arrival_time = models.TimeField() # 지기 도착 시간
    mentee = models.ForeignKey('User', on_delete=models.CASCADE, related_name='mentee_time', null=True, blank=True) # 견습 지기
    mentee_arrival_time = models.TimeField(null=True, blank=True) # 견습 지기 도착 시간
    time_comment_music = models.TextField(default="", blank=True, null=True) # 음악 관련 코멘트
    time_comment_gigi = models.TextField(default="", blank=True, null=True) # 기기 관련 코멘트
    time_comment_etc = models.TextField(default="", blank=True, null=True) # 기타 코멘트

    class Meta:
        db_table = 'time_info'

# 곡 정보
class MusicInfo(models.Model):
    time_info = models.ForeignKey('TimeInfo', on_delete=models.CASCADE)
    is_requested = models.BooleanField(default=False)
    source = models.CharField(max_length=20)
    cd_id = models.CharField(max_length=20, blank=True, null=True)
    title = models.CharField(max_length=200)
    semi_title = models.CharField(max_length=200, blank=True, null=True)
    composer = models.ForeignKey('ComposerInfo', related_name='musics', on_delete=models.CASCADE, blank=True, null=True)
    conductor = models.ForeignKey('ConductorInfo', on_delete=models.CASCADE, blank=True, null=True)
    orchestra = models.ForeignKey('OrchestraInfo', on_delete=models.CASCADE, blank=True, null=True)
    players = models.ManyToManyField('PlayerInfo')

    class Meta:
        db_table = 'music_info'

class ComposerInfo(models.Model):
    name = models.CharField(max_length=50)

    class Meta:
        db_table = 'composer_info'

class ConductorInfo(models.Model):
    name = models.CharField(max_length=50)

    class Meta:
        db_table = 'conducter_info'

class OrchestraInfo(models.Model):
    name = models.CharField(max_length=50)

    class Meta:
        db_table = 'orchestra_info'

# 연주자 정보
class PlayerInfo(models.Model):
    name = models.CharField(max_length=50)
    instrument = models.CharField(max_length=50)

    class Meta:
        db_table = 'player_info'
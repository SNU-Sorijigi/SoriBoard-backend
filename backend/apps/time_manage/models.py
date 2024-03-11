from django.db import models


# 지기 정보
class User(models.Model):
    name = models.CharField(max_length=20)  # 이름
    major = models.CharField(max_length=40)  # 전공
    year_id = models.CharField(max_length=2)  # 학번
    is_ob = models.BooleanField(default=False)  # OB 여부

    class Meta:
        db_table = "user"


# 학기 운영 정보
class Semester(models.Model):
    year = models.IntegerField()  # 연도
    semester_num = models.IntegerField()  # 학기
    total_time = models.IntegerField(default=4)  # 하루 타임 수 (기본 4)
    start_time = models.TimeField()  # 타임 시작 시간 (예: 9시 30분)
    end_time = models.TimeField()  # 타임 종료 시간 (예: 17시 40분)
    rest_time = models.IntegerField(default=10)  # 쉬는 시간 (기본 10분)

    class Meta:
        db_table = "semester"


# 학기 - 지기 연결
class SemesterUser(models.Model):
    user = models.ForeignKey(
        "User", on_delete=models.CASCADE, related_name="usersemesterinfo"
    )  # 지기
    mentee = models.ForeignKey(
        "User",
        on_delete=models.CASCADE,
        related_name="menteesemesterinfo",
        null=True,
        blank=True,
    )  # 견습 지기
    semester = models.ForeignKey(
        "Semester", on_delete=models.CASCADE, related_name="userinfo"
    )  # 학기
    day = models.IntegerField()  # 요일 (Monday = 0)
    time = models.IntegerField()  # 타임

    class Meta:
        db_table = "semester_user"


# 타임 정보
class TimeInfo(models.Model):
    time = models.IntegerField()  # 타임
    date = models.DateField()  # 날짜
    user = models.ForeignKey(
        "User", on_delete=models.CASCADE, related_name="time"
    )  # 지기
    arrival_time = models.TimeField()  # 지기 도착 시간
    mentee = models.ForeignKey(
        "User",
        on_delete=models.CASCADE,
        related_name="mentee_time",
        null=True,
        blank=True,
    )  # 견습 지기
    mentee_arrival_time = models.TimeField(null=True, blank=True)  # 견습 지기 도착 시간
    time_comment_music = models.TextField(
        default="", blank=True, null=True
    )  # 음악 관련 코멘트
    time_comment_gigi = models.TextField(
        default="", blank=True, null=True
    )  # 기기 관련 코멘트
    time_comment_etc = models.TextField(
        default="", blank=True, null=True
    )  # 기타 코멘트

    class Meta:
        db_table = "time"
        unique_together = ("time", "date")


# 선곡 정보
class TimeMusic(models.Model):
    time = models.ForeignKey(
        "TimeInfo", on_delete=models.CASCADE, related_name="timeplaylist"
    )  # 타임 id
    order = models.IntegerField()  # 순서
    is_requested = models.BooleanField(default=False)  # 신청곡
    source = models.CharField(max_length=20)  # 소스
    cd_id = models.CharField(max_length=20, blank=True, null=True)  # 음반
    music = models.ForeignKey(
        "Music", on_delete=models.CASCADE, blank=True, null=True
    )  # 곡
    music_detail = models.ForeignKey(
        "MusicDetail", on_delete=models.CASCADE, blank=True, null=True
    )  # 세부 제목
    conductor = models.ForeignKey(
        "Conductor", on_delete=models.CASCADE, blank=True, null=True
    )  # 지휘자
    orchestra = models.ForeignKey(
        "Orchestra", on_delete=models.CASCADE, blank=True, null=True
    )  # 오케스트라
    players = models.ManyToManyField("Player")  # 연주자

    class Meta:
        db_table = "time_music"


# 곡 정보
class Music(models.Model):
    title = models.CharField(max_length=200)
    composer = models.ForeignKey(
        "Composer",
        related_name="musics",
        on_delete=models.CASCADE,
    )

    class Meta:
        db_table = "music"


# 세부 제목 정보
class MusicDetail(models.Model):
    music = models.ForeignKey("Music", related_name="details", on_delete=models.CASCADE)
    semi_title = models.CharField(max_length=200)

    class Meta:
        db_table = "music_detail"


# 작곡가 정보
class Composer(models.Model):
    name = models.CharField(max_length=50)

    class Meta:
        db_table = "composer"


# 지휘자 정보
class Conductor(models.Model):
    name = models.CharField(max_length=50)

    class Meta:
        db_table = "conducter"


# 오케스트라 정보
class Orchestra(models.Model):
    name = models.CharField(max_length=50)

    class Meta:
        db_table = "orchestra"


# 연주자 정보
class Player(models.Model):
    name = models.CharField(max_length=50)
    instrument = models.CharField(max_length=50)

    class Meta:
        db_table = "player"

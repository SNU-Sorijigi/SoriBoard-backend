from django.db import models, transaction
from rest_framework import serializers
from .models import *


class BlankAsNullIntegerField(serializers.IntegerField):
    """An emptied number input sends "": read it as no number, as DRF does for forms."""

    def validate_empty_values(self, data):
        return super().validate_empty_values(None if data == "" else data)


class UserSerializer(serializers.ModelSerializer):
    sabu_info = serializers.SerializerMethodField()
    # 지기 설정 sends "" when 입부 년도 or 학기 (the integer fields, both
    # optional) is left empty. Mapped, not declared, to keep the field order.
    serializer_field_mapping = {
        **serializers.ModelSerializer.serializer_field_mapping,
        models.IntegerField: BlankAsNullIntegerField,
    }

    class Meta:
        model = User
        fields = "__all__"
        # Past SQLite's 64-bit INTEGER the driver raises OverflowError (500).
        extra_kwargs = {
            name: {"min_value": -(2**63), "max_value": 2**63 - 1}
            for name in ("join_year", "join_semester")
        }

    def get_sabu_info(self, obj):
        if obj.sabu_id:
            return f"{obj.sabu_id.name} {obj.sabu_id.major} {obj.sabu_id.year_id}"
        else:
            return ""


class ComposerSerializer(serializers.ModelSerializer):
    num_time_music = serializers.IntegerField(read_only=True)

    class Meta:
        model = Composer
        fields = ["id", "name", "num_time_music"]


class ComposerNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = Composer
        fields = ["name"]


class MusicSerializer(serializers.ModelSerializer):
    num_time_music = serializers.IntegerField(read_only=True)
    composer = ComposerNameSerializer()

    class Meta:
        model = Music
        fields = ["id", "title", "composer", "num_time_music"]


class UserNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["name"]


class CreatingSlugRelatedField(serializers.SlugRelatedField):
    def to_internal_value(self, data):
        try:
            user, created = User.objects.get_or_create(name=data)
            return user
        except (TypeError, ValueError):
            self.fail("invalid")
        except User.DoesNotExist:
            self.fail("does_not_exist", slug_name=self.slug_field, value=data)
        except User.MultipleObjectsReturned:
            self.fail("multiple_objects", slug_name=self.slug_field, value=data)


class SemesterSerializer(serializers.ModelSerializer):
    timetable_id = serializers.SerializerMethodField()

    class Meta:
        model = Semester
        fields = "__all__"
        extra_kwargs = {
            # stats reads a 2nd semester up to the next year's February.
            "year": {"min_value": 1, "max_value": 9998},
            # checksemester/ and the session calendar know only these two.
            "semester_num": {"min_value": 1, "max_value": 2},
            # With no 타임 a semester has no timetable cells at all.
            "total_time": {"min_value": 1},
            # Past SQLite's 64-bit INTEGER the driver raises OverflowError (500).
            "rest_time": {"min_value": -(2**63), "max_value": 2**63 - 1},
        }

    def get_timetable_id(self, obj):
        # A deleted timetable (timetable/<id>/ DELETE, the admin) was a 500.
        try:
            return obj.timetable.id
        except Timetable.DoesNotExist:
            return None


class TimetableSerializer(serializers.ModelSerializer):
    class Meta:
        model = Timetable
        fields = "__all__"


class TimetableUnitSerializer(serializers.ModelSerializer):
    jigi_info = serializers.SerializerMethodField()
    mentee_info = serializers.SerializerMethodField()

    class Meta:
        model = TimetableUnit
        fields = "__all__"
        extra_kwargs = {
            # Timetable.update_table has weekdays 0 to 6; a cell on another day
            # made it fail, and with it every later edit of the timetable.
            "day": {"min_value": 0, "max_value": 6},
            # Past SQLite's 64-bit INTEGER the driver raises OverflowError (500).
            "time": {"min_value": 1, "max_value": 2**63 - 1},
        }

    def validate(self, attrs):
        # It has 타임 1 to the semester's total_time: a cell past that fell
        # out of the timetable. PATCH may send neither, so use the cell's.
        timetable = (
            attrs["timetable"] if "timetable" in attrs else self.instance.timetable
        )
        time = attrs["time"] if "time" in attrs else self.instance.time
        total_time = timetable.semester.total_time
        if time > total_time:
            message = self.fields["time"].error_messages["max_value"]
            raise serializers.ValidationError(
                {"time": [message.format(max_value=total_time)]}
            )
        return attrs

    def get_jigi_info(self, obj):
        return [f"{jigi.name} {jigi.major} {jigi.year_id}" for jigi in obj.users.all()]

    def get_mentee_info(self, obj):
        return [f"{m.name} {m.major} {m.year_id}" for m in obj.mentees.all()]


class SemesterUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = SemesterUser
        fields = "__all__"


class BlankAsNullTimeField(serializers.TimeField):
    """A cleared time input sends "": read it as no time, as DRF does for forms."""

    def validate_empty_values(self, data):
        return super().validate_empty_values(None if data == "" else data)


class TimeInfoSerializer(serializers.ModelSerializer):
    jigi_info = serializers.SerializerMethodField()
    mentee_info = serializers.SerializerMethodField()
    # The session forms send "" when no 견습 arrival time is entered.
    mentee_arrival_time = BlankAsNullTimeField(allow_null=True, required=False)
    # Backward-compat single fields
    user = serializers.SerializerMethodField()
    mentee = serializers.SerializerMethodField()

    class Meta:
        model = TimeInfo
        fields = [
            "id",
            "time",
            "date",
            "users",
            "arrival_time",
            "mentees",
            "mentee_arrival_time",
            "time_comment_music",
            "time_comment_gigi",
            "time_comment_etc",
            # legacy-compatible fields
            "user",
            "mentee",
            "jigi_info",
            "mentee_info",
        ]
        extra_kwargs = {
            # checktime/ and the session calendar start at 타임 1, so a session
            # on 타임 0 or below was saved but never shown. Past SQLite's 64-bit
            # INTEGER the driver raises OverflowError (500).
            "time": {"min_value": 1, "max_value": 2**63 - 1},
        }

    def get_jigi_info(self, obj):
        return [f"{u.name} {u.major} {u.year_id}" for u in obj.users.all()]

    def get_mentee_info(self, obj):
        return [f"{m.name} {m.major} {m.year_id}" for m in obj.mentees.all()]

    def get_user(self, obj):
        first = obj.users.first()
        return first.id if first else None

    def get_mentee(self, obj):
        first = obj.mentees.first()
        return first.id if first else None


class TimeInfoLookupSerializer(serializers.Serializer):
    """Query of GET timeinfo/: a malformed date or time is a 400, not a 500."""

    date = serializers.DateField()
    # Past SQLite's 64-bit INTEGER the driver raises OverflowError (500).
    time = serializers.IntegerField(min_value=-(2**63), max_value=2**63 - 1)


class TimeMusicListSerializer(serializers.ModelSerializer):
    music_title = serializers.CharField(source="music.title", read_only=True)
    music_semi_title = serializers.CharField(
        source="music_detail.semi_title", read_only=True
    )
    composer_name = serializers.CharField(source="music.composer.name", read_only=True)
    conductor_name = serializers.CharField(source="conductor.name", read_only=True)
    orchestra_name = serializers.CharField(source="orchestra.name", read_only=True)
    player_names = serializers.SerializerMethodField()

    class Meta:
        model = TimeMusic
        fields = [
            "id",
            "order",
            "is_requested",
            "source",
            "cd_id",
            "music_title",
            "music_semi_title",
            "composer_name",
            "conductor_name",
            "orchestra_name",
            "player_names",
        ]

    def get_player_names(self, obj):
        return [
            (player.instrument + ": " + player.name) for player in obj.players.all()
        ]


class TimeInfoDetailSerializer(serializers.ModelSerializer):
    jigi_info = serializers.SerializerMethodField()
    mentee_info = serializers.SerializerMethodField()
    time_music = serializers.SerializerMethodField()
    user = serializers.SerializerMethodField()
    mentee = serializers.SerializerMethodField()

    class Meta:
        model = TimeInfo
        fields = [
            "id",
            "time",
            "date",
            "users",
            "arrival_time",
            "mentees",
            "mentee_arrival_time",
            "time_comment_music",
            "time_comment_gigi",
            "time_comment_etc",
            "user",
            "mentee",
            "jigi_info",
            "mentee_info",
            "time_music",
        ]

    def get_time_music(self, obj):
        # Everything TimeMusicListSerializer reads, in two queries, not ~5 per play.
        queryset = (
            obj.timeplaylist.select_related(
                "music__composer", "music_detail", "conductor", "orchestra"
            )
            .prefetch_related("players")
            .order_by("order", "id")  # swaporder/ counts on ties going by id
        )
        return TimeMusicListSerializer(queryset, many=True, read_only=True).data

    def get_jigi_info(self, obj):
        return [f"{u.name} {u.major} {u.year_id}" for u in obj.users.all()]

    def get_mentee_info(self, obj):
        return [f"{m.name} {m.major} {m.year_id}" for m in obj.mentees.all()]

    def get_user(self, obj):
        first = obj.users.first()
        return first.id if first else None

    def get_mentee(self, obj):
        first = obj.mentees.first()
        return first.id if first else None


class TimeMusicSerializer(serializers.ModelSerializer):
    title = serializers.CharField(write_only=True)
    semi_title = serializers.CharField(
        write_only=True, allow_blank=True, required=False
    )
    composer_name = serializers.CharField(write_only=True)
    conductor_name = serializers.CharField(
        write_only=True, allow_blank=True, required=False
    )
    orchestra_name = serializers.CharField(
        write_only=True, allow_blank=True, required=False
    )
    player_names = serializers.ListField(
        child=serializers.CharField(write_only=True, allow_blank=True, required=False),
        write_only=True,
        allow_empty=True,
    )

    class Meta:
        model = TimeMusic
        fields = "__all__"
        extra_kwargs = {
            "source": {"allow_blank": False},
            # Past SQLite's 64-bit INTEGER the driver raises OverflowError (500).
            "order": {"min_value": -(2**63), "max_value": 2**63 - 1},
            "music": {"read_only": True},
            "music_detail": {"read_only": True},
            "conductor": {"read_only": True},
            "orchestra": {"read_only": True},
            "players": {"read_only": True},
        }

    def validate_player_names(self, value):
        # create() and update() split each non-blank row on ": ".
        malformed = [row for row in value if row and len(row.split(": ")) != 2]
        if malformed:
            raise serializers.ValidationError(
                [f'"{row}" is not "instrument: name".' for row in malformed]
            )
        return value

    def validate_conductor_name(self, value):
        # update() splits it on ": " (the edit form shows "지휘: " + name);
        # create() takes the name as it is.
        if self.instance is not None and value and len(value.split(": ")) != 2:
            raise serializers.ValidationError(f'"{value}" is not "role: name".')
        return value

    def validate(self, attrs):
        # PUT is partial (the edit form sends no time or order), but update()
        # rebuilds the music from these two, so a PUT needs them too.
        missing = [name for name in ("title", "composer_name") if name not in attrs]
        if missing:
            raise serializers.ValidationError(
                {name: self.fields[name].error_messages["required"] for name in missing}
            )
        return attrs

    # A play is written whole or not at all, never without its players.
    @transaction.atomic
    def create(self, validated_data):
        composer_name = validated_data.pop("composer_name", "")
        composer, _ = Composer.objects.get_or_create(name=composer_name)

        conductor_name = validated_data.pop("conductor_name", "")
        conductor, _ = (
            Conductor.objects.get_or_create(name=conductor_name)
            if conductor_name
            else (None, False)
        )

        orchestra_name = validated_data.pop("orchestra_name", "")
        orchestra, _ = (
            Orchestra.objects.get_or_create(name=orchestra_name)
            if orchestra_name
            else (None, False)
        )

        title = validated_data.pop("title")
        semi_title = validated_data.pop("semi_title", None)
        music, _ = Music.objects.get_or_create(title=title, composer=composer)
        music_detail, _ = (
            MusicDetail.objects.get_or_create(music=music, semi_title=semi_title)
            if semi_title
            else (None, False)
        )

        player_names = validated_data.pop("player_names", [])

        time_music = TimeMusic.objects.create(
            **validated_data,
            music=music,
            music_detail=music_detail,
            conductor=conductor,
            orchestra=orchestra,
        )

        for player_name in player_names:
            if player_name:
                instrument, name = player_name.split(": ")
                player, _ = Player.objects.get_or_create(
                    instrument=instrument.strip(), name=name.strip()
                )
                time_music.players.add(player)

        return time_music

    @transaction.atomic
    def update(self, instance, validated_data):
        player_names = validated_data.pop("player_names", [])
        title = validated_data.pop("title")
        semi_title = validated_data.pop("semi_title", None)
        composer_name = validated_data.pop("composer_name")
        conductor_name = validated_data.pop("conductor_name", None)
        orchestra_name = validated_data.pop("orchestra_name", None)

        composer, _ = Composer.objects.get_or_create(name=composer_name)

        if conductor_name:
            _, conductor_name = conductor_name.split(": ")
            conductor, _ = Conductor.objects.get_or_create(name=conductor_name)
            instance.conductor = conductor
        else:
            instance.conductor = None

        if orchestra_name:
            orchestra, _ = Orchestra.objects.get_or_create(name=orchestra_name)
            instance.orchestra = orchestra
        else:
            instance.orchestra = None

        music, _ = Music.objects.get_or_create(title=title, composer=composer)

        if semi_title:
            music_detail, _ = MusicDetail.objects.get_or_create(
                music=music, semi_title=semi_title
            )
            instance.music_detail = music_detail
        else:
            instance.music_detail = None

        instance.music = music

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if player_names:
            instance.players.clear()
            for player_name in player_names:
                if player_name:
                    instrument, name = player_name.split(": ")
                    player, _ = Player.objects.get_or_create(
                        instrument=instrument.strip(), name=name.strip()
                    )
                    instance.players.add(player)
        else:
            instance.players.clear()

        return instance


class NewsSerializer(serializers.ModelSerializer):
    class Meta:
        model = News
        fields = "__all__"

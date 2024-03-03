from rest_framework import serializers
from .models import *


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = "__all__"


class UserNameSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["name"]


class TimeInfoSerializer(serializers.ModelSerializer):
    user = serializers.SlugRelatedField(slug_field="name", queryset=User.objects.all())
    mentee = serializers.SlugRelatedField(
        slug_field="name", queryset=User.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = TimeInfo
        fields = [
            "date",
            "time",
            "user",
            "mentee",
            "arrival_time",
            "mentee_arrival_time",
        ]


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
            "order",
            "is_requested",
            "source",
            "cd_id",
            "music_title",
            "music_semi_title",
            "composer_name" "conductor_name",
            "orchestra_name",
            "player_names",
        ]

    def get_player_names(self, obj):
        return [player.name for player in obj.players.all()]


class TimeInfoDetailSerializer(serializers.ModelSerializer):
    user = UserNameSerializer(read_only=True)
    mentee = UserNameSerializer(read_only=True)
    time_music = TimeMusicListSerializer(
        source="timeplaylist", many=True, read_only=True
    )

    class Meta:
        model = TimeInfo
        fields = "__all__"


class TimeMusicSerializer(serializers.ModelSerializer):
    title = serializers.CharField(write_only=True)
    semi_title = serializers.CharField(write_only=True, required=False)
    composer_name = serializers.CharField(write_only=True)
    conductor_name = serializers.CharField(write_only=True, required=False)
    orchestra_name = serializers.CharField(write_only=True, required=False)
    player_names = serializers.ListField(
        child=serializers.CharField(), write_only=True, required=False
    )

    class Meta:
        model = TimeMusic
        fields = "__all__"
        extra_kwargs = {
            "music": {"read_only": True},
            "music_detail": {"read_only": True},
            "conductor": {"read_only": True},
            "orchestra": {"read_only": True},
            "players": {"read_only": True},
        }

    def create(self, validated_data):
        player_names = validated_data.pop("player_names", [])
        title = validated_data.pop("title")
        semi_title = validated_data.pop("semi_title", None)
        composer_name = validated_data.pop("composer_name")
        conductor_name = validated_data.pop("conductor_name", None)
        orchestra_name = validated_data.pop("orchestra_name", None)

        composer, _ = Composer.objects.get_or_create(name=composer_name)

        music, _ = Music.objects.get_or_create(title=title, composer=composer)
        music_detail = None
        if semi_title:
            music_detail, _ = MusicDetail.objects.get_or_create(
                music=music, semi_title=semi_title
            )

        conductor = None
        if conductor_name:
            conductor, _ = Conductor.objects.get_or_create(name=conductor_name)

        orchestra = None
        if orchestra_name:
            orchestra, _ = Orchestra.objects.get_or_create(name=orchestra_name)

        time_music = TimeMusic.objects.create(
            music=music,
            music_detail=music_detail,
            conductor=conductor,
            orchestra=orchestra,
            **validated_data
        )

        for player_name in player_names:
            instrument, name = player_name.split(": ")
            player, _ = Player.objects.get_or_create(
                name=name.strip(), instrument=instrument.strip()
            )
            time_music.players.add(player)

        return time_music

    def update(self, instance, validated_data):
        return super().update(instance, validated_data)

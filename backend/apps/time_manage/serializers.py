from rest_framework import serializers
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


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = "__all__"


class SemesterInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = SemesterInfo
        fields = "__all__"


class SemesterUserInfoSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    mentee = UserSerializer(read_only=True)

    class Meta:
        model = SemesterUserInfo
        fields = "__all__"


class SemesterUserInfoPostSerializer(serializers.ModelSerializer):

    class Meta:
        model = SemesterUserInfo
        fields = "__all__"


class TimeInfoSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(write_only=True, required=False)
    mentee_name = serializers.CharField(write_only=True, required=False, allow_blank=True, allow_null=True)

    class Meta:
        model = TimeInfo
        fields = '__all__'
        extra_kwargs = {
            'user': {'read_only': True},
            'mentee': {'read_only': True},
        }
    
    def create(self, validated_data):
        user_name = validated_data.pop('user_name', None)
        mentee_name = validated_data.pop('mentee_name', None)

        # Find or create the user (userr)
        user, _ = User.objects.get_or_create(name=user_name)
        validated_data['user'] = user

        # Find or create the mentee, if a name is provided
        if mentee_name:
            mentee, _ = User.objects.get_or_create(name=mentee_name)
            validated_data['mentee'] = mentee
        else:
            validated_data['mentee'] = None
        
        print(validated_data)

        return super().create(validated_data)
    
    def get_user_name(self, obj):
        return obj.user.name if obj.user else None

    def get_mentee_name(self, obj):
        return obj.mentee.name if obj.mentee else None
    
class TimeInfoGetSerializer(serializers.ModelSerializer):
    mento_name = serializers.SerializerMethodField()
    mentee_name = serializers.SerializerMethodField()

    class Meta:
        model = TimeInfo
        fields = ['id', 'time', 'date', 'time_comment_music', 'time_comment_gigi', 'time_comment_etc', 'mento_name', 'mentee_name']
        # Exclude the 'user' and 'mentee' fields if you don't want their IDs to be part of the response

    def get_mento_name(self, obj):
        return obj.user.name if obj.user else None

    def get_mentee_name(self, obj):
        return obj.mentee.name if obj.mentee else None

class TimeInfoPostSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(write_only=True)
    mentee_name = serializers.CharField(
        write_only=True, required=False, allow_null=True
    )

    class Meta:
        model = TimeInfo
        fields = [
            "time",
            "date",
            "user_name",
            "mentee_name",
            "arrival_time",
            "time_comment_music",
            "time_comment_gigi",
            "time_comment_etc",
        ]

    def create(self, validated_data):
        user_name = validated_data.pop("user_name")
        mentee_name = validated_data.pop("mentee_name", None)

        user = User.objects.get(name=user_name)
        mentee = User.objects.get(name=mentee_name) if mentee_name else None

        # Assuming the logic to get the current semester info
        current_semester = SemesterInfo.objects.get_current_semester()

        time_info = TimeInfo.objects.create(
            user=user, mentee=mentee, SemesterInfo=current_semester, **validated_data
        )
        return time_info


class MusicInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MusicInfo
        fields = "__all__"


class PlayerInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlayerInfo
        fields = "__all__"


class ComposerInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComposerInfo
        fields = "__all__"


class ConductorInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConductorInfo
        fields = "__all__"


class OrchestraInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrchestraInfo
        fields = "__all__"

from rest_framework import serializers
from .models import User, SemesterInfo, TimeInfo, MusicInfo, PlayerInfo, ComposerInfo, ConductorInfo, OrchestraInfo, SemesterUserInfo

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = '__all__'

class SemesterInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = SemesterInfo
        fields = '__all__'

class SemesterUserInfoSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    mentee = UserSerializer(read_only=True)

    class Meta:
        model = SemesterUserInfo
        fields = '__all__'

class SemesterUserInfoPostSerializer(serializers.ModelSerializer):

    class Meta:
        model = SemesterUserInfo
        fields = '__all__'

class TimeInfoSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    mentee = UserSerializer(read_only=True)

    class Meta:
        model = TimeInfo
        fields = '__all__'

class TimeInfoPostSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(write_only=True)
    mentee_name = serializers.CharField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = TimeInfo
        fields = ['time', 'date', 'user_name', 'mentee_name', 'arrival_time', 
                  'time_comment_music', 'time_comment_gigi', 'time_comment_etc']

    def create(self, validated_data):
        user_name = validated_data.pop('user_name')
        mentee_name = validated_data.pop('mentee_name', None)

        user = User.objects.get(name=user_name)
        mentee = User.objects.get(name=mentee_name) if mentee_name else None

        # Assuming the logic to get the current semester info
        current_semester = SemesterInfo.objects.get_current_semester()

        time_info = TimeInfo.objects.create(
            user=user, 
            mentee=mentee, 
            SemesterInfo=current_semester,
            **validated_data
        )
        return time_info

class MusicInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MusicInfo
        fields = '__all__'

class PlayerInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlayerInfo
        fields = '__all__'

class ComposerInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComposerInfo
        fields = '__all__'

class ConductorInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConductorInfo
        fields = '__all__'

class OrchestraInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrchestraInfo
        fields = '__all__'
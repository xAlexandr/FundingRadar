from rest_framework import serializers
from .models import User
from rest_framework_simplejwt.views import TokenViewBase
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model

User = get_user_model()

class TelegramTokenObtainSerializer(serializers.Serializer):
    telegram_id = serializers.IntegerField()

    def validate(self, attrs):
        telegram_id = attrs.get('telegram_id')
        user = User.objects.filter(telegram_id=telegram_id).first()

        if not user:
            raise serializers.ValidationError('Пользователь с таким Telegram ID не найден.')

        # Создаем и возвращаем токены
        refresh = RefreshToken.for_user(user)
        return {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }

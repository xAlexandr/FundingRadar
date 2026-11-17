from django.db import models
import sys
from datetime import timedelta
from django.utils.timezone import now
from email.policy import default
from django.utils import timezone
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin, Group, Permission

#sys.path.append("..")

class CustomUserManager(BaseUserManager):
   # def create_user(self, telegram_id, password=None, **extra_fields):
    def create_user(self, telegram_id, password=None, **extra_fields):
        if not telegram_id:
            raise ValueError('The Telegram ID must be set')
        user = self.model(telegram_id=telegram_id, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, telegram_id, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(telegram_id, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    telegram_id = models.BigIntegerField(unique=True, blank=False, null=False)
    username = models.CharField(max_length=150, blank=True, null=True)  # Уникальность убрана
    first_name = models.CharField(max_length=30, blank=True, null=True)
    last_name = models.CharField(max_length=30, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    language = models.CharField(max_length=50, blank=True, null=True)
    date_of_registration = models.DateTimeField(auto_now_add=True)
    last_login_time = models.DateTimeField(auto_now=True)
    depth_value = models.PositiveIntegerField(default=0)
    market1_value = models.PositiveIntegerField(default=0)
    market2_value = models.PositiveIntegerField(default=0)
    memo = models.CharField(max_length=50, blank=True, null=True)

    test_active = models.BooleanField(default=False)
    test_start_date = models.DateTimeField(blank=True, null=True)
    subscribe_active = models.BooleanField(default=False)
    subscribe_start_date = models.DateTimeField(blank=True, null=True)

    referral = models.IntegerField(blank=True, null=True)

    mon_coin = models.IntegerField(blank=True, null=True)
    mon_in = models.IntegerField(blank=True, null=True)
    mon_out = models.IntegerField(blank=True, null=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    groups = models.ManyToManyField(
        Group,
        related_name='custom_user_groups',
        blank=True,
        help_text='The groups this user belongs to.',
        verbose_name='groups'
    )
    user_permissions = models.ManyToManyField(
        Permission,
        related_name='custom_user_permissions',
        blank=True,
        help_text='Specific permissions for this user.',
        verbose_name='user permissions'
    )

    objects = CustomUserManager()

    USERNAME_FIELD = 'telegram_id'  # Для аутентификации по Telegram ID
    REQUIRED_FIELDS = []

    def is_subscription_active(self):
        if self.test_active and self.test_start_date:
            return self.test_start_date + timedelta(hours=8) > timezone.now()
        elif self.subscribe_active and self.subscribe_start_date:
            # Проверка, активна ли подписка
            return self.subscribe_start_date + timedelta(days=30) > timezone.now()
        return False

    def __str__(self):
        return f"{self.telegram_id} ({self.username})"


class UserLoginRecord(models.Model):
    user = models.ForeignKey('User', on_delete=models.CASCADE, null=True, blank=True)  # Связь с пользователем (если он авторизован)
    ip_address = models.GenericIPAddressField()  # Поле для хранения IP-адреса
    timestamp = models.DateTimeField(default=now)  # Время входа

    def __str__(self):
        return f"{self.user} - {self.ip_address} - {self.timestamp}"

class DeviceRecord(models.Model):
    """
    Запись о устройстве, которое запросило подписку sub_id.
    sub_id: строка идентификатор подписки (то, что ты используешь в URL)
    client_id: устойчивый идентификатор устройства (X-Hwid или fallback)
    ua: User-Agent
    hw_info: небольшая json/text с дополнительной информацией (device model, os, app version)
    first_seen / last_seen - временные метки
    blocked - можно вручную блокировать устройство
    """
    sub_id = models.CharField(max_length=255, db_index=True)
    client_id = models.CharField(max_length=255, db_index=True)
    ua = models.CharField(max_length=512, blank=True, null=True)
    hw_info = models.JSONField(blank=True, null=True)  # хранит headers / meta
    first_seen = models.DateTimeField(default=timezone.now)
    last_seen = models.DateTimeField(default=timezone.now)
    request_count = models.PositiveIntegerField(default=1)
    blocked = models.BooleanField(default=False)

    class Meta:
        unique_together = ("sub_id", "client_id")
        indexes = [
            models.Index(fields=["sub_id", "last_seen"]),
        ]

    def touch(self):
        self.last_seen = timezone.now()
        self.request_count = (self.request_count or 0) + 1
        self.save(update_fields=["last_seen", "request_count"])

class SubscriptionSetting(models.Model):
    """
    Персональные настройки для подписки (sub_id).
    Если записи нет — используется глобальный DEFAULT (settings.MAX_DEVICES_PER_SUB).
    """
    sub_id = models.CharField(max_length=128, unique=True, db_index=True)
    max_devices = models.PositiveSmallIntegerField(default=2)  # сколько устройств разрешить
    note = models.CharField(max_length=200, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Настройка подписки"
        verbose_name_plural = "Настройки подписок"

    def __str__(self):
        return f"{self.sub_id} — {self.max_devices} devices"
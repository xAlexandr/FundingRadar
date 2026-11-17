from django.contrib import admin
from django.utils.html import format_html
from .models import User, UserLoginRecord, DeviceRecord, SubscriptionSetting

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = (
        'telegram_id', 'username', 'first_name', 'last_name', 'country', 'language',
        'date_of_registration', 'last_login_time', 'test_active', 'subscribe_active'
    )
    search_fields = ('telegram_id', 'username', 'first_name', 'last_name')
    list_filter = ('is_active', 'is_staff', 'country', 'language')
    ordering = ('-date_of_registration',)
    readonly_fields = ('date_of_registration', 'last_login_time')

@admin.register(UserLoginRecord)
class UserLoginRecordAdmin(admin.ModelAdmin):
    list_display = ('user_display', 'ip_address', 'timestamp')
    search_fields = ('ip_address', 'user__telegram_id', 'user__username')
    list_filter = ('timestamp', 'user')
    ordering = ('-timestamp',)

    def user_display(self, obj):
        if obj.user:
            return format_html('<a href="/admin/accounts/user/{user_id}/">{user}</a>', user_id=obj.user.id, user=obj.user)
        return "Анонимный пользователь"
    user_display.short_description = "Пользователь"

@admin.register(DeviceRecord)
class DeviceRecordAdmin(admin.ModelAdmin):
    list_display = ("sub_id", "client_id", "ua", "first_seen", "last_seen", "request_count", "blocked")
    list_filter = ("sub_id", "blocked")
    search_fields = ("sub_id", "client_id", "ua")

@admin.register(SubscriptionSetting)
class SubscriptionSettingAdmin(admin.ModelAdmin):
    list_display = ("sub_id", "max_devices", "note", "updated_at")
    search_fields = ("sub_id", "note")
    list_editable = ("max_devices",)
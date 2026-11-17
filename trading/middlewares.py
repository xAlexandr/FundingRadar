# middlewares.py (или где у вас)
import ipaddress
from django.utils.timezone import now
from .models import UserLoginRecord
from django.contrib.auth import get_user

def _clean_ip(ip_str):
    if not ip_str:
        return None
    # X-Forwarded-For может содержать "client, proxy1, proxy2"
    if ',' in ip_str:
        ip_str = ip_str.split(',')[0].strip()
    # убрать порт, если есть (e.g. "1.2.3.4:56789")
    if ':' in ip_str and ip_str.count(':') == 1:
        ip_str = ip_str.split(':')[0]
    try:
        # validate IPv4/IPv6
        ipaddress.ip_address(ip_str)
        return ip_str
    except Exception:
        return None

class LogIPMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        ip = self.get_client_ip(request)
        user = get_user(request)

        if ip:
            UserLoginRecord.objects.create(
                user=user if user.is_authenticated else None,
                ip_address=ip,
                timestamp=now()
            )

        return response

    def get_client_ip(self, request):
        # priority: X-Real-IP, X-Forwarded-For (first), REMOTE_ADDR
        ip = request.META.get('HTTP_X_REAL_IP')
        if ip:
            ip = _clean_ip(ip)
            if ip:
                return ip

        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        if xff:
            ip = _clean_ip(xff)
            if ip:
                return ip

        # fallback
        return request.META.get('REMOTE_ADDR')

class RealIPMiddleware:
    """
    Проставляет реальный IP клиента в request.META['REMOTE_ADDR'],
    основываясь на заголовках X-Real-IP и X-Forwarded-For.
    Помещать до middleware, который читает REMOTE_ADDR.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # сначала пытаемся X-Real-IP (nginx ставит его)
        ip = request.META.get('HTTP_X_REAL_IP')
        if ip:
            ip = _clean_ip(ip)

        # если нет — смотрим X-Forwarded-For
        if not ip:
            xff = request.META.get('HTTP_X_FORWARDED_FOR')
            ip = _clean_ip(xff)

        # если всё равно нет — оставляем REMOTE_ADDR как есть (fallback)
        if ip:
            request.META['REMOTE_ADDR'] = ip

        response = self.get_response(request)
        return response
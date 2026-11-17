from django.urls import path

from .views import (index, telegram_login, get_coins, update_depth_value, get_subscribe, get_futures, get_futures_pages,
                    get_futures_id, get_spot, get_spot_pages, get_spot_id, get_change_to_course, get_change_to_spread,
                    get_change_to_big, get_data_settings, proxy_subscription, get_dex, get_dex_pages, get_dex_id,
                    get_top_funding, get_top_funding_spot)

urlpatterns = [
    path('<str:sp_or_ft>/<str:market1>/<str:market2>/<str:coin>/', index, name='main'),
    path('coins/', get_coins, name='get_coins'),
    path('get_futures_pages/', get_futures_pages, name='get_futures_pages'),
    path('get_change_to_course/', get_change_to_course, name='get_change_to_course'),
    path('get_data_settings/', get_data_settings, name='get_data_settings'),
    path('get_change_to_spread/', get_change_to_spread, name='get_change_to_spread'),
    path('get_change_to_big/', get_change_to_big, name='get_change_to_big'),
    path('get_spot_pages/', get_spot_pages, name='get_spot_pages'),
    path('get_futures_id/', get_futures_id, name='get_futures_id'),
    path('get_spot_id/', get_spot_id, name='get_spot_id'),
    path('get_futures/', get_futures, name='get_futures'),
    path('get_spot/', get_spot, name='get_spot'),
    path('get_dex/', get_dex, name='get_dex'),
    path('get_dex_pages/', get_dex_pages, name='get_dex_pages'),
    path('get_dex_id/', get_dex_id, name='get_dex_id'),
    path('top-funding/', get_top_funding, name='get_top_funding'),
    path('top-funding-spot/', get_top_funding_spot, name='get_top_funding_spot'),
    path('update-depth/', update_depth_value, name='update-depth'),
    path('auth/telegram/', telegram_login, name='telegram_login'),
    path('get_subscribe/', get_subscribe, name='get_subscribe'),
    path('proxy/<str:user>', proxy_subscription),
]

__all__ = ("router",)
from aiogram import Router

from .page_markets import router as page_markets_router
from .spot_page_markets import router as spot_page_markets_router
from .dex_page_markets import router as dex_page_router

router = Router(name=__name__)

router.include_routers(page_markets_router, spot_page_markets_router, dex_page_router)
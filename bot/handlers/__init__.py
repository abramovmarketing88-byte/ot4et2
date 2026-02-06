"""Bot handlers package."""
from bot.handlers.register import router as register_router
from bot.handlers.profiles import router as profiles_router
from bot.handlers.reports import router as reports_router
from bot.handlers.settings import router as settings_router

__all__ = [
    "register_router",
    "profiles_router",
    "reports_router",
    "settings_router",
]

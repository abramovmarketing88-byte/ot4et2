"""Bot handlers package."""
from bot.handlers.register import router as register_router
from bot.handlers.profiles import router as profiles_router
from bot.handlers.reports import router as reports_router
from bot.handlers.settings import router as settings_router
from bot.handlers.ai_mode import router as ai_mode_router
from bot.handlers.ai_admin import router as ai_admin_router
from bot.handlers.daily_limits import router as daily_limits_router

__all__ = [
    "register_router",
    "profiles_router",
    "reports_router",
    "settings_router",
    "ai_mode_router",
    "ai_admin_router",
    "daily_limits_router",
]

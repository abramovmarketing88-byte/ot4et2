"""Каналы / Интеграции: выбор Avito или Telegram."""
import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.reports import render_reports_entry
from bot.keyboards import integrations_menu_kb
from core.database.models import User

logger = logging.getLogger(__name__)
router = Router(name="integrations")


async def _get_user(telegram_id: int, session: AsyncSession) -> User | None:
    r = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return r.scalar_one_or_none()


@router.callback_query(F.data == "main:integrations")
async def cb_main_integrations(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    """Показать экран каналов интеграции."""
    await state.clear()
    await callback.message.edit_text(
        "🔌 <b>Каналы / Интеграции</b>\n\nВыберите канал:",
        reply_markup=integrations_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "intg:avito")
async def cb_intg_avito(
    callback: CallbackQuery, session: AsyncSession, state: FSMContext
) -> None:
    """Переход к отчётам (Avito)."""
    await render_reports_entry(callback, session)
    await callback.answer()


@router.callback_query(F.data == "intg:back")
async def cb_intg_back(callback: CallbackQuery, state: FSMContext) -> None:
    """Назад в меню каналов."""
    await state.clear()
    await callback.message.edit_text(
        "🔌 <b>Каналы / Интеграции</b>\n\nВыберите канал:",
        reply_markup=integrations_menu_kb(),
    )
    await callback.answer()

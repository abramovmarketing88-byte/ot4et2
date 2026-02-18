"""Handler для команды /start."""
import logging

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import mode_select_kb, start_main_menu_kb
from core.database.models import User

logger = logging.getLogger(__name__)
router = Router(name="register")


async def get_or_create_user(telegram_id: int, session: AsyncSession) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user:
        return user
    user = User(telegram_id=telegram_id)
    session.add(user)
    await session.flush()
    await session.refresh(user)
    return user


@router.message(CommandStart())
async def cmd_start(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    telegram_id = message.from_user.id if message.from_user else 0
    await get_or_create_user(telegram_id, session)
    await message.answer(
        "👋 <b>Добро пожаловать в Avito Analytics Bot!</b>\n\nВыберите раздел:",
        reply_markup=start_main_menu_kb(),
    )


@router.callback_query(F.data == "main:help")
async def cb_main_help(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "Команды:\n/start\n/profiles\n/stats\n/mode",
        reply_markup=start_main_menu_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "main:reports")
async def cb_main_reports(callback: CallbackQuery) -> None:
    await callback.message.edit_text("Откройте /profiles и выберите Report Settings", reply_markup=start_main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "main:ai")
async def cb_main_ai(callback: CallbackQuery) -> None:
    await callback.message.edit_text("Откройте /mode для AI Seller режима.", reply_markup=mode_select_kb("ai_seller"))
    await callback.answer()


@router.callback_query(F.data == "main:profiles")
async def cb_main_profiles(callback: CallbackQuery) -> None:
    await callback.message.edit_text("Откройте /profiles для управления профилями.", reply_markup=start_main_menu_kb())
    await callback.answer()


@router.callback_query(F.data == "main:templates")
async def cb_main_templates(callback: CallbackQuery) -> None:
    await callback.message.edit_text("Global AI Templates: используйте /prompts", reply_markup=start_main_menu_kb())
    await callback.answer()

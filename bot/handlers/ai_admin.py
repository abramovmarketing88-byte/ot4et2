"""AI admin handlers: prompts + compatibility commands."""
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states import PromptAdminStates
from core.config import settings
from core.database.models import PromptTemplate

logger = logging.getLogger(__name__)
router = Router(name="ai_admin")


def _is_admin(user_id: int, chat_id: int | None = None) -> bool:
    admin_id = settings.ADMIN_CHAT_ID
    return bool(admin_id and (user_id == admin_id or chat_id == admin_id))


@router.message(Command("ai_branches"))
async def cmd_ai_branches_compat(message: Message) -> None:
    await message.answer("AI branches удалены. Используйте 🤖 AI Settings внутри профиля (/profiles).")


@router.message(Command("followups"))
async def cmd_followups_compat(message: Message) -> None:
    await message.answer("Followup chains удалены. Используйте 📩 Follow-ups внутри AI Settings профиля.")


@router.message(Command("prompts"))
async def cmd_prompts(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else 0, message.chat.id if message.chat else None):
        await message.answer("Доступ к AI-админке только для администратора.")
        return
    await state.clear()
    result = await session.execute(select(PromptTemplate).where(PromptTemplate.owner_id == message.from_user.id))
    rows = list(result.scalars().all())
    builder = InlineKeyboardBuilder()
    for p in rows:
        builder.row(
            builder.button(text=f"✏️ {p.name}", callback_data=f"ai_prompt:edit:{p.id}"),  # type: ignore[arg-type]
            builder.button(text="🗑 Удалить", callback_data=f"ai_prompt:delete:{p.id}"),  # type: ignore[arg-type]
        )
    builder.row(builder.button(text="➕ Новый prompt", callback_data="ai_prompt:new"))  # type: ignore[arg-type]
    text = "\n".join([f"#{p.id} [{p.scope}] {p.name}" for p in rows]) or "Пусто"
    await message.answer(f"<b>Prompt templates</b>\n{text}", reply_markup=builder.as_markup())


@router.callback_query(F.data == "ai_prompt:new")
async def cb_prompt_new(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(PromptAdminStates.waiting_scope)
    await callback.message.answer("Введите scope (system|followup|summary):")
    await callback.answer()


@router.message(PromptAdminStates.waiting_scope, F.text)
async def prompts_scope(message: Message, state: FSMContext) -> None:
    scope = message.text.strip()
    if scope not in {"system", "followup", "summary"}:
        await message.answer("Допустимо: system|followup|summary")
        return
    await state.update_data(scope=scope)
    await state.set_state(PromptAdminStates.waiting_name)
    await message.answer("Введите имя шаблона:")


@router.message(PromptAdminStates.waiting_name, F.text)
async def prompts_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())
    await state.set_state(PromptAdminStates.waiting_content)
    await message.answer("Введите содержимое prompt:")


@router.message(PromptAdminStates.waiting_content, F.text)
async def prompts_content(message: Message, session: AsyncSession, state: FSMContext) -> None:
    data = await state.get_data()
    prompt = PromptTemplate(owner_id=message.from_user.id, scope=data["scope"], name=data["name"], content=message.text)
    session.add(prompt)
    await state.clear()
    await message.answer("✅ Prompt сохранён")

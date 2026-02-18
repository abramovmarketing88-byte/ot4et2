"""AI admin handlers: /prompts, /ai_branches, /followups."""
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import ai_admin_menu_kb
from bot.states import BranchAdminStates, FollowupAdminStates, PromptAdminStates
from core.config import settings
from core.database.models import AIBranch, AvitoProfile, FollowupChain, FollowupStep, PromptTemplate

logger = logging.getLogger(__name__)
router = Router(name="ai_admin")


def _is_admin(user_id: int, chat_id: int | None = None) -> bool:
    admin_id = settings.ADMIN_CHAT_ID
    if admin_id is None:
        return False
    if user_id == admin_id:
        return True
    if chat_id is not None and chat_id == admin_id:
        return True
    return False


async def _save_branch_from_state(message: Message, state: FSMContext, session: AsyncSession) -> None:
    """Создать или обновить AIBranch на основе данных в FSM."""
    data = await state.get_data()
    branch_id = data.get("branch_id")
    name = data.get("name")
    avito_profile_id = data.get("avito_profile_id")
    gpt_model = data.get("gpt_model")
    system_prompt_id = data.get("system_prompt_id")
    context_retention_days = data.get("context_retention_days")
    max_messages_in_context = data.get("max_messages_in_context")
    followup_enabled = data.get("followup_enabled")

    if not all([name, avito_profile_id, gpt_model, system_prompt_id]) or followup_enabled is None:
        await message.answer("Недостаточно данных для сохранения ветки. Начните заново через /ai_branches.")
        await state.clear()
        return

    owner_id = message.from_user.id if message.from_user else 0

    if branch_id is None:
        item = AIBranch(
            owner_id=owner_id,
            name=name,
            avito_profile_id=avito_profile_id,
            gpt_model=gpt_model,
            system_prompt_id=system_prompt_id,
            context_retention_days=context_retention_days,
            max_messages_in_context=max_messages_in_context,
            followup_enabled=followup_enabled,
        )
        session.add(item)
        await state.clear()
        await message.answer("✅ AI-ветка сохранена")
    else:
        result = await session.execute(
            select(AIBranch).where(
                AIBranch.id == branch_id,
                AIBranch.owner_id == owner_id,
            )
        )
        branch = result.scalar_one_or_none()
        if not branch:
            await message.answer("Ветка не найдена или недоступна для редактирования.")
            await state.clear()
            return
        branch.name = name
        branch.avito_profile_id = avito_profile_id
        branch.gpt_model = gpt_model
        branch.system_prompt_id = system_prompt_id
        branch.context_retention_days = context_retention_days
        branch.max_messages_in_context = max_messages_in_context
        branch.followup_enabled = followup_enabled
        await state.clear()
        await message.answer("✅ AI-ветка обновлена")


@router.message(Command("prompts"))
async def cmd_prompts(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else 0, message.chat.id if message.chat else None):
        await message.answer("Доступ к AI-админке только для администратора.")
        return
    await state.clear()
    result = await session.execute(
        select(PromptTemplate).where(PromptTemplate.owner_id == message.from_user.id)
    )
    rows = list(result.scalars().all())
    if not rows:
        await message.answer(
            "Prompt templates не найдены.\n"
            "Чтобы создать: /prompts_new <scope> <name>\n"
            "scope: system|followup|summary"
        )
        return
    text = "\n".join([f"#{p.id} [{p.scope}] {p.name}" for p in rows])
    builder = InlineKeyboardBuilder()
    for p in rows:
        builder.row(
            *(  # type: ignore[arg-type]
                builder.button(
                    text=f"✏️ {p.name}",
                    callback_data=f"ai_prompt:edit:{p.id}",
                ),
                builder.button(
                    text="🗑 Удалить",
                    callback_data=f"ai_prompt:delete:{p.id}",
                ),
            )
        )
    builder.row(
        builder.button(text="➕ Новый prompt", callback_data="ai_prompt:new")  # type: ignore[arg-type]
    )
    await message.answer(f"<b>Prompt templates</b>\n{text}", reply_markup=builder.as_markup())


@router.message(Command("prompts_new"))
async def cmd_prompts_new(message: Message, state: FSMContext) -> None:
    if not _is_admin(message.from_user.id if message.from_user else 0, message.chat.id if message.chat else None):
        await message.answer("Доступ к AI-админке только для администратора.")
        return
    await state.clear()
    await state.set_state(PromptAdminStates.waiting_scope)
    await message.answer("Введите scope (system|followup|summary):")


@router.message(PromptAdminStates.waiting_scope, F.text)
async def prompts_scope(message: Message, state: FSMContext) -> None:
    scope = message.text.strip()
    if scope not in {"system", "followup", "summary"}:
        await message.answer("Допустимо: system|followup|summary")
        return
    await state.update_data(scope=scope)
    await state.set_state(PromptAdminStates.waiting_name)
    await message.answer("Введите name prompt template:")


@router.message(PromptAdminStates.waiting_name, F.text)
async def prompts_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())
    await state.set_state(PromptAdminStates.waiting_content)
    await message.answer("Отправьте текст prompt или файл .txt/.md")


@router.message(PromptAdminStates.waiting_content, F.text)
async def prompts_content_text(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    item = PromptTemplate(
        owner_id=message.from_user.id,
        name=data["name"],
        scope=data["scope"],
        content=message.text,
    )
    session.add(item)
    await state.clear()
    await message.answer(f"✅ Prompt сохранён: #{item.id or 'new'}")


@router.message(PromptAdminStates.waiting_content, F.document)
async def prompts_content_file(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not message.document or not message.bot:
        return
    filename = (message.document.file_name or "").lower()
    if not (filename.endswith(".txt") or filename.endswith(".md")):
        await message.answer("Допустимы только .txt/.md")
        return
    file = await message.bot.get_file(message.document.file_id)
    content = await message.bot.download_file(file.file_path)
    text = content.read().decode("utf-8", errors="ignore")
    data = await state.get_data()
    item = PromptTemplate(
        owner_id=message.from_user.id,
        name=data["name"],
        scope=data["scope"],
        content=text,
    )
    session.add(item)
    await state.clear()
    await message.answer("✅ Prompt из файла сохранён")


@router.message(PromptAdminStates.editing_prompt, F.text)
async def prompts_edit_text(message: Message, state: FSMContext, session: AsyncSession) -> None:
    data = await state.get_data()
    prompt_id = data.get("prompt_id")
    if not isinstance(prompt_id, int):
        await message.answer("Состояние редактирования prompt утеряно. Начните заново через /prompts.")
        await state.clear()
        return
    result = await session.execute(
        select(PromptTemplate).where(
            PromptTemplate.id == prompt_id,
            PromptTemplate.owner_id == message.from_user.id,
        )
    )
    prompt = result.scalar_one_or_none()
    if not prompt:
        await message.answer("Prompt не найден. Обновите список через /prompts.")
        await state.clear()
        return
    prompt.content = message.text
    await state.clear()
    await message.answer(f"✅ Prompt #{prompt.id} обновлён.")


@router.message(PromptAdminStates.editing_prompt, F.document)
async def prompts_edit_file(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not message.document or not message.bot:
        return
    filename = (message.document.file_name or "").lower()
    if not (filename.endswith(".txt") or filename.endswith(".md")):
        await message.answer("Допустимы только .txt/.md")
        return
    data = await state.get_data()
    prompt_id = data.get("prompt_id")
    if not isinstance(prompt_id, int):
        await message.answer("Состояние редактирования prompt утеряно. Начните заново через /prompts.")
        await state.clear()
        return
    file = await message.bot.get_file(message.document.file_id)
    content = await message.bot.download_file(file.file_path)
    text = content.read().decode("utf-8", errors="ignore")
    result = await session.execute(
        select(PromptTemplate).where(
            PromptTemplate.id == prompt_id,
            PromptTemplate.owner_id == message.from_user.id,
        )
    )
    prompt = result.scalar_one_or_none()
    if not prompt:
        await message.answer("Prompt не найден. Обновите список через /prompts.")
        await state.clear()
        return
    prompt.content = text
    await state.clear()
    await message.answer(f"✅ Prompt #{prompt.id} обновлён из файла.")


@router.callback_query(F.data == "ai_prompt:new")
async def cb_prompt_new(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else 0, callback.message.chat.id if callback.message else None):
        await callback.answer("Только админ может управлять prompt шаблонами.", show_alert=True)
        return
    await state.clear()
    await state.set_state(PromptAdminStates.waiting_scope)
    await callback.message.answer("Введите scope (system|followup|summary):")
    await callback.answer()


@router.callback_query(F.data.startswith("ai_prompt:edit:"))
async def cb_prompt_edit(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else 0, callback.message.chat.id if callback.message else None):
        await callback.answer("Только админ может управлять prompt шаблонами.", show_alert=True)
        return
    try:
        prompt_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Некорректный идентификатор prompt.", show_alert=True)
        return
    result = await session.execute(
        select(PromptTemplate).where(
            PromptTemplate.id == prompt_id,
            PromptTemplate.owner_id == callback.from_user.id,
        )
    )
    prompt = result.scalar_one_or_none()
    if not prompt:
        await callback.answer("Prompt не найден.", show_alert=True)
        return
    await state.update_data(prompt_id=prompt_id)
    await state.set_state(PromptAdminStates.editing_prompt)
    await callback.message.answer(
        f"Редактирование prompt #{prompt.id} [{prompt.scope}] {prompt.name}.\n"
        "Отправьте новый текст или файл .txt/.md."
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ai_prompt:delete:"))
async def cb_prompt_delete(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else 0, callback.message.chat.id if callback.message else None):
        await callback.answer("Только админ может управлять prompt шаблонами.", show_alert=True)
        return
    try:
        prompt_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Некорректный идентификатор prompt.", show_alert=True)
        return
    result = await session.execute(
        select(PromptTemplate).where(
            PromptTemplate.id == prompt_id,
            PromptTemplate.owner_id == callback.from_user.id,
        )
    )
    prompt = result.scalar_one_or_none()
    if not prompt:
        await callback.answer("Prompt не найден.", show_alert=True)
        return
    await state.update_data(prompt_id=prompt_id)
    await state.set_state(PromptAdminStates.confirming_delete)
    builder = InlineKeyboardBuilder()
    builder.row(
        builder.button(text="✅ Удалить", callback_data="ai_prompt:confirm_delete"),  # type: ignore[arg-type]
        builder.button(text="❌ Отмена", callback_data="ai_prompt:cancel_delete"),  # type: ignore[arg-type]
    )
    await callback.message.answer(
        f"Вы уверены, что хотите удалить prompt #{prompt.id} [{prompt.scope}] {prompt.name}?",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "ai_prompt:confirm_delete")
async def cb_prompt_confirm_delete(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else 0, callback.message.chat.id if callback.message else None):
        await callback.answer("Только админ может управлять prompt шаблонами.", show_alert=True)
        return
    data = await state.get_data()
    prompt_id = data.get("prompt_id")
    if not isinstance(prompt_id, int):
        await callback.answer("Состояние удаления prompt утеряно.", show_alert=True)
        await state.clear()
        return
    result = await session.execute(
        select(PromptTemplate).where(
            PromptTemplate.id == prompt_id,
            PromptTemplate.owner_id == callback.from_user.id,
        )
    )
    prompt = result.scalar_one_or_none()
    if not prompt:
        await callback.answer("Prompt не найден.", show_alert=True)
        await state.clear()
        return
    await session.delete(prompt)
    await state.clear()
    await callback.message.answer(f"✅ Prompt #{prompt_id} удалён.")
    await callback.answer()


@router.callback_query(F.data == "ai_prompt:cancel_delete")
async def cb_prompt_cancel_delete(callback: CallbackQuery, state: FSMContext) -> None:
    if not _is_admin(callback.from_user.id if callback.from_user else 0, callback.message.chat.id if callback.message else None):
        await callback.answer("Только админ может управлять prompt шаблонами.", show_alert=True)
        return
    await state.clear()
    await callback.answer("Удаление prompt отменено.")


@router.message(Command("ai_branches"))
async def cmd_ai_branches(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    result = await session.execute(select(AIBranch).where(AIBranch.owner_id == message.from_user.id))
    rows = list(result.scalars().all())
    if not rows:
        await message.answer("AI-ветки не найдены. Создать: /ai_branches_new")
        return
    text = "\n".join([f"#{b.id} {b.name} model={b.gpt_model} prompt={b.system_prompt_id}" for b in rows])
    builder = InlineKeyboardBuilder()
    for b in rows:
        edit_btn = builder.button(
            text=f"✏️ {b.name}",
            callback_data=f"ai_branch:edit:{b.id}",
        )
        delete_btn = builder.button(
            text="🗑 Удалить",
            callback_data=f"ai_branch:delete:{b.id}",
        )
        builder.row(edit_btn, delete_btn)
    new_btn = builder.button(text="➕ Новая ветка", callback_data="ai_branch:new")
    builder.row(new_btn)
    await message.answer(f"<b>AI branches</b>\n{text}", reply_markup=builder.as_markup())


@router.message(Command("ai_branches_new"))
async def cmd_ai_branches_new(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(BranchAdminStates.waiting_name)
    await message.answer("Введите название ветки:")


@router.message(BranchAdminStates.waiting_name, F.text)
async def branch_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())
    await state.set_state(BranchAdminStates.waiting_avito_profile_id)
    await message.answer("Введите avito_profile_id (профиль должен принадлежать вам):")


@router.message(BranchAdminStates.waiting_avito_profile_id, F.text)
async def branch_profile(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not message.text.isdigit():
        await message.answer("Введите числовой avito_profile_id")
        return
    profile_id = int(message.text)
    profile_res = await session.execute(
        select(AvitoProfile).where(
            AvitoProfile.id == profile_id,
            AvitoProfile.owner_id == message.from_user.id,
        )
    )
    if profile_res.scalar_one_or_none() is None:
        await message.answer("Профиль не найден")
        return
    await state.update_data(avito_profile_id=profile_id)
    await state.set_state(BranchAdminStates.waiting_gpt_model)
    await message.answer("Введите gpt_model: gpt-mini|gpt-mid|gpt-optimal|gpt-pro")


@router.message(BranchAdminStates.waiting_gpt_model, F.text)
async def branch_model(message: Message, state: FSMContext) -> None:
    model = message.text.strip()
    if model not in {"gpt-mini", "gpt-mid", "gpt-optimal", "gpt-pro"}:
        await message.answer("Допустимо: gpt-mini|gpt-mid|gpt-optimal|gpt-pro")
        return
    await state.update_data(gpt_model=model)
    await state.set_state(BranchAdminStates.waiting_system_prompt_id)
    await message.answer("Введите system_prompt_id:")


@router.message(BranchAdminStates.waiting_system_prompt_id, F.text)
async def branch_prompt_id(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not message.text.isdigit():
        await message.answer("Введите числовой system_prompt_id")
        return
    prompt_id = int(message.text)
    prompt_res = await session.execute(
        select(PromptTemplate).where(
            PromptTemplate.id == prompt_id,
            PromptTemplate.owner_id == message.from_user.id,
            PromptTemplate.scope == "system",
        )
    )
    if prompt_res.scalar_one_or_none() is None:
        await message.answer("Prompt template не найден или имеет неверный scope (нужно scope=system)")
        return
    await state.update_data(system_prompt_id=prompt_id)
    await state.set_state(BranchAdminStates.waiting_context_retention_days)
    await message.answer(
        "Введите context_retention_days (количество дней хранения контекста) "
        "или оставьте пустым для значения по умолчанию:"
    )


@router.message(BranchAdminStates.waiting_context_retention_days, F.text)
async def branch_context_retention_days(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw:
        await state.update_data(context_retention_days=None)
    else:
        if not raw.isdigit():
            await message.answer("Введите целое число дней или оставьте пустым.")
            return
        value = int(raw)
        if value <= 0:
            await message.answer("Число дней должно быть больше нуля или оставьте поле пустым.")
            return
        await state.update_data(context_retention_days=value)
    await state.set_state(BranchAdminStates.waiting_max_messages_in_context)
    await message.answer(
        "Введите max_messages_in_context (сколько сообщений хранить в контексте) "
        "или оставьте пустым для значения по умолчанию:"
    )


@router.message(BranchAdminStates.waiting_max_messages_in_context, F.text)
async def branch_max_messages_in_context(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw:
        await state.update_data(max_messages_in_context=None)
    else:
        if not raw.isdigit():
            await message.answer("Введите целое число сообщений или оставьте пустым.")
            return
        value = int(raw)
        if value <= 0:
            await message.answer("Число сообщений должно быть больше нуля или оставьте поле пустым.")
            return
        await state.update_data(max_messages_in_context=value)
    await state.set_state(BranchAdminStates.waiting_followup_enabled)
    await message.answer(
        "Включить followups для этой ветки? Введите yes/no (или да/нет):"
    )


@router.message(BranchAdminStates.waiting_followup_enabled, F.text)
async def branch_followup_enabled(message: Message, state: FSMContext, session: AsyncSession) -> None:
    raw = (message.text or "").strip().lower()
    if raw in {"yes", "y", "да", "true"}:
        value = True
    elif raw in {"no", "n", "нет", "false"}:
        value = False
    else:
        await message.answer("Введите yes/no (или да/нет).")
        return
    await state.update_data(followup_enabled=value)
    await _save_branch_from_state(message, state, session)


@router.callback_query(F.data == "ai_branch:new")
async def cb_branch_new(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(BranchAdminStates.waiting_name)
    await callback.message.answer("Введите название ветки:")
    await callback.answer()


@router.callback_query(F.data.startswith("ai_branch:edit:"))
async def cb_branch_edit(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    try:
        branch_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Некорректный идентификатор ветки.", show_alert=True)
        return
    result = await session.execute(
        select(AIBranch).where(
            AIBranch.id == branch_id,
            AIBranch.owner_id == callback.from_user.id,
        )
    )
    branch = result.scalar_one_or_none()
    if not branch:
        await callback.answer("Ветка не найдена.", show_alert=True)
        return
    await state.clear()
    await state.update_data(
        branch_id=branch.id,
        name=branch.name,
        avito_profile_id=branch.avito_profile_id,
        gpt_model=branch.gpt_model,
        system_prompt_id=branch.system_prompt_id,
        context_retention_days=branch.context_retention_days,
        max_messages_in_context=branch.max_messages_in_context,
        followup_enabled=branch.followup_enabled,
    )
    await state.set_state(BranchAdminStates.waiting_name)
    await callback.message.answer(
        f"Редактирование ветки #{branch.id}.\n"
        f"Текущее имя: {branch.name}\n"
        "Введите новое название ветки:"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ai_branch:delete:"))
async def cb_branch_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        branch_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Некорректный идентификатор ветки.", show_alert=True)
        return
    result = await session.execute(
        select(AIBranch).where(
            AIBranch.id == branch_id,
            AIBranch.owner_id == callback.from_user.id,
        )
    )
    branch = result.scalar_one_or_none()
    if not branch:
        await callback.answer("Ветка не найдена.", show_alert=True)
        return
    builder = InlineKeyboardBuilder()
    confirm_btn = builder.button(
        text="✅ Удалить",
        callback_data=f"ai_branch:confirm_delete:{branch.id}",
    )
    cancel_btn = builder.button(
        text="❌ Отмена",
        callback_data="ai_branch:cancel_delete",
    )
    builder.row(confirm_btn, cancel_btn)
    await callback.message.answer(
        f"Вы уверены, что хотите удалить ветку #{branch.id} {branch.name}?",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ai_branch:confirm_delete:"))
async def cb_branch_confirm_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        branch_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Некорректный идентификатор ветки.", show_alert=True)
        return
    result = await session.execute(
        select(AIBranch).where(
            AIBranch.id == branch_id,
            AIBranch.owner_id == callback.from_user.id,
        )
    )
    branch = result.scalar_one_or_none()
    if not branch:
        await callback.answer("Ветка не найдена.", show_alert=True)
        return
    await session.delete(branch)
    await callback.message.answer(f"✅ Ветка #{branch.id} удалена.")
    await callback.answer()


@router.callback_query(F.data == "ai_branch:cancel_delete")
async def cb_branch_cancel_delete(callback: CallbackQuery) -> None:
    await callback.answer("Удаление ветки отменено.")


# ─── Followup chains & steps (ai_followup:*) ─────────────────────────────────

def _chain_owner_filter(owner_id: int):
    return (
        select(FollowupChain)
        .join(AIBranch, AIBranch.id == FollowupChain.branch_id)
        .where(AIBranch.owner_id == owner_id)
    )


@router.message(Command("followups"))
async def cmd_followups(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    await _followups_list(message, session, message.from_user.id if message.from_user else 0)


async def _followups_list(message: Message, session: AsyncSession, owner_id: int) -> None:
    result = await session.execute(_chain_owner_filter(owner_id))
    rows = list(result.scalars().unique().all())
    text = "\n".join([f"#{r.id} {r.name} [{r.start_event}] active={r.is_active}" for r in rows]) if rows else "Нет цепочек."
    builder = InlineKeyboardBuilder()
    for r in rows:
        builder.row(
            builder.button(text=f"✏️ {r.name}", callback_data=f"ai_followup:chain_edit:{r.id}"),
            builder.button(text="📋 Шаги", callback_data=f"ai_followup:steps:{r.id}"),
        )
        builder.row(
            builder.button(text="🗑 Удалить", callback_data=f"ai_followup:chain_delete:{r.id}"),
        )
    builder.row(builder.button(text="➕ Новая цепочка", callback_data="ai_followup:chain_new"))
    await message.answer(f"<b>Followup chains</b>\n{text}", reply_markup=builder.as_markup())


@router.message(Command("followups_new"))
async def cmd_followups_new(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(FollowupAdminStates.waiting_branch_id)
    await message.answer("Введите branch_id (ветка должна принадлежать вам):")


@router.callback_query(F.data == "ai_followup:chain_new")
async def cb_followup_chain_new(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(FollowupAdminStates.waiting_branch_id)
    await callback.message.answer("Введите branch_id (ветка должна принадлежать вам):")
    await callback.answer()


@router.message(FollowupAdminStates.waiting_branch_id, F.text)
async def followup_chain_branch_id(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not message.text or not message.text.strip().isdigit():
        await message.answer("Введите числовой branch_id.")
        return
    branch_id = int(message.text.strip())
    res = await session.execute(
        select(AIBranch).where(AIBranch.id == branch_id, AIBranch.owner_id == message.from_user.id)
    )
    if res.scalar_one_or_none() is None:
        await message.answer("Ветка не найдена или не ваша.")
        return
    await state.update_data(branch_id=branch_id)
    await state.set_state(FollowupAdminStates.waiting_name)
    await message.answer("Введите название цепочки:")


@router.message(FollowupAdminStates.waiting_name, F.text)
async def followup_chain_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=(message.text or "").strip())
    await state.set_state(FollowupAdminStates.waiting_start_event)
    await message.answer("Введите start_event: dialog_started | no_reply | manual")


@router.message(FollowupAdminStates.waiting_start_event, F.text)
async def followup_chain_start_event(message: Message, state: FSMContext) -> None:
    ev = (message.text or "").strip()
    if ev not in {"dialog_started", "no_reply", "manual"}:
        await message.answer("Допустимо: dialog_started | no_reply | manual")
        return
    await state.update_data(start_event=ev)
    await state.set_state(FollowupAdminStates.waiting_stop_on_conversion)
    await message.answer("Останавливать при конверсии? yes/no:")


@router.message(FollowupAdminStates.waiting_stop_on_conversion, F.text)
async def followup_chain_stop_on_conversion(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip().lower()
    if raw in {"yes", "y", "да", "true"}:
        value = True
    elif raw in {"no", "n", "нет", "false"}:
        value = False
    else:
        await message.answer("Введите yes/no.")
        return
    await state.update_data(stop_on_conversion=value)
    await state.set_state(FollowupAdminStates.waiting_is_active)
    await message.answer("Цепочка активна? yes/no:")


@router.message(FollowupAdminStates.waiting_is_active, F.text)
async def followup_chain_is_active(message: Message, state: FSMContext, session: AsyncSession) -> None:
    raw = (message.text or "").strip().lower()
    if raw in {"yes", "y", "да", "true"}:
        value = True
    elif raw in {"no", "n", "нет", "false"}:
        value = False
    else:
        await message.answer("Введите yes/no.")
        return
    await state.update_data(is_active=value)
    data = await state.get_data()
    chain_id = data.get("chain_id")
    if chain_id is not None:
        res = await session.execute(
            select(FollowupChain).join(AIBranch, AIBranch.id == FollowupChain.branch_id).where(
                FollowupChain.id == chain_id, AIBranch.owner_id == message.from_user.id
            )
        )
        chain = res.scalar_one_or_none()
        if not chain:
            await message.answer("Цепочка не найдена.")
            await state.clear()
            return
        chain.branch_id = data["branch_id"]
        chain.name = data["name"]
        chain.start_event = data["start_event"]
        chain.stop_on_conversion = data["stop_on_conversion"]
        chain.is_active = value
        await state.clear()
        await message.answer("✅ Цепочка обновлена.")
    else:
        item = FollowupChain(
            branch_id=data["branch_id"],
            name=data["name"],
            start_event=data["start_event"],
            stop_on_conversion=data["stop_on_conversion"],
            is_active=value,
        )
        session.add(item)
        await state.clear()
        await message.answer("✅ Цепочка создана.")


@router.callback_query(F.data.startswith("ai_followup:chain_edit:"))
async def cb_followup_chain_edit(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    try:
        chain_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Некорректный id.", show_alert=True)
        return
    res = await session.execute(
        select(FollowupChain).join(AIBranch, AIBranch.id == FollowupChain.branch_id).where(
            FollowupChain.id == chain_id, AIBranch.owner_id == callback.from_user.id
        )
    )
    chain = res.scalar_one_or_none()
    if not chain:
        await callback.answer("Цепочка не найдена.", show_alert=True)
        return
    await state.clear()
    await state.update_data(
        chain_id=chain.id,
        branch_id=chain.branch_id,
        name=chain.name,
        start_event=chain.start_event,
        stop_on_conversion=chain.stop_on_conversion,
    )
    await state.set_state(FollowupAdminStates.waiting_branch_id)
    await callback.message.answer(f"Редактирование цепочки #{chain.id}. Введите branch_id (текущий: {chain.branch_id}):")
    await callback.answer()


@router.callback_query(F.data.startswith("ai_followup:chain_delete:"))
async def cb_followup_chain_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        chain_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Некорректный id.", show_alert=True)
        return
    res = await session.execute(
        select(FollowupChain).join(AIBranch, AIBranch.id == FollowupChain.branch_id).where(
            FollowupChain.id == chain_id, AIBranch.owner_id == callback.from_user.id
        )
    )
    chain = res.scalar_one_or_none()
    if not chain:
        await callback.answer("Цепочка не найдена.", show_alert=True)
        return
    builder = InlineKeyboardBuilder()
    builder.row(
        builder.button(text="✅ Удалить", callback_data=f"ai_followup:chain_confirm_delete:{chain.id}"),
        builder.button(text="❌ Отмена", callback_data="ai_followup:chain_cancel_delete"),
    )
    await callback.message.answer(
        f"Удалить цепочку #{chain.id} {chain.name}?",
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("ai_followup:chain_confirm_delete:"))
async def cb_followup_chain_confirm_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        chain_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Некорректный id.", show_alert=True)
        return
    res = await session.execute(
        select(FollowupChain).join(AIBranch, AIBranch.id == FollowupChain.branch_id).where(
            FollowupChain.id == chain_id, AIBranch.owner_id == callback.from_user.id
        )
    )
    chain = res.scalar_one_or_none()
    if not chain:
        await callback.answer("Цепочка не найдена.", show_alert=True)
        return
    await session.delete(chain)
    await callback.message.answer("✅ Цепочка удалена.")
    await callback.answer()


@router.callback_query(F.data == "ai_followup:chain_cancel_delete")
async def cb_followup_chain_cancel_delete(callback: CallbackQuery) -> None:
    await callback.answer("Отменено.")


@router.callback_query(F.data.startswith("ai_followup:steps:"))
async def cb_followup_steps(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        chain_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Некорректный id.", show_alert=True)
        return
    res = await session.execute(
        select(FollowupChain).join(AIBranch, AIBranch.id == FollowupChain.branch_id).where(
            FollowupChain.id == chain_id, AIBranch.owner_id == callback.from_user.id
        )
    )
    chain = res.scalar_one_or_none()
    if not chain:
        await callback.answer("Цепочка не найдена.", show_alert=True)
        return
    steps_res = await session.execute(
        select(FollowupStep).where(FollowupStep.chain_id == chain_id).order_by(FollowupStep.order_index)
    )
    steps = list(steps_res.scalars().all())
    text = "\n".join(
        [f"#{s.id} order={s.order_index} delay={s.delay_seconds}s {s.send_mode} {s.content_type}" for s in steps]
    ) if steps else "Нет шагов."
    builder = InlineKeyboardBuilder()
    for s in steps:
        builder.row(
            builder.button(text=f"✏️ #{s.id}", callback_data=f"ai_followup:step_edit:{s.id}"),
            builder.button(text="🗑", callback_data=f"ai_followup:step_delete:{s.id}"),
        )
    builder.row(builder.button(text="➕ Шаг", callback_data=f"ai_followup:step_new:{chain_id}"))
    builder.row(builder.button(text="« К цепочкам", callback_data="ai_followup:chains"))
    await callback.message.answer(f"<b>Шаги цепочки #{chain.id} {chain.name}</b>\n{text}", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "ai_followup:chains")
async def cb_followup_chains(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    await callback.message.answer("Цепочки:")
    await _followups_list(callback.message, session, callback.from_user.id if callback.from_user else 0)
    await callback.answer()


@router.callback_query(F.data.startswith("ai_followup:step_new:"))
async def cb_followup_step_new(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    try:
        chain_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Некорректный id.", show_alert=True)
        return
    res = await session.execute(
        select(FollowupChain).join(AIBranch, AIBranch.id == FollowupChain.branch_id).where(
            FollowupChain.id == chain_id, AIBranch.owner_id == callback.from_user.id
        )
    )
    if res.scalar_one_or_none() is None:
        await callback.answer("Цепочка не найдена.", show_alert=True)
        return
    await state.clear()
    await state.update_data(chain_id=chain_id, step_id=None)
    await state.set_state(FollowupAdminStates.waiting_order_index)
    await callback.message.answer("Введите order_index (целое число):")
    await callback.answer()


@router.message(FollowupAdminStates.waiting_order_index, F.text)
async def followup_step_order_index(message: Message, state: FSMContext) -> None:
    if not message.text or not message.text.strip().isdigit():
        await message.answer("Введите целое число.")
        return
    await state.update_data(order_index=int(message.text.strip()))
    await state.set_state(FollowupAdminStates.waiting_delay_seconds)
    await message.answer("Введите delay_seconds (секунды):")


@router.message(FollowupAdminStates.waiting_delay_seconds, F.text)
async def followup_step_delay_seconds(message: Message, state: FSMContext) -> None:
    if not message.text or not message.text.strip().isdigit():
        await message.answer("Введите целое число секунд.")
        return
    await state.update_data(delay_seconds=int(message.text.strip()))
    await state.set_state(FollowupAdminStates.waiting_send_mode)
    await message.answer("Введите send_mode: always | if_not_converted | if_not_converted_and_no_negative")


@router.message(FollowupAdminStates.waiting_send_mode, F.text)
async def followup_step_send_mode(message: Message, state: FSMContext) -> None:
    mode = (message.text or "").strip()
    if mode not in {"always", "if_not_converted", "if_not_converted_and_no_negative"}:
        await message.answer("Допустимо: always | if_not_converted | if_not_converted_and_no_negative")
        return
    await state.update_data(send_mode=mode)
    await state.set_state(FollowupAdminStates.waiting_content_type)
    await message.answer("Введите content_type: fixed | llm")


@router.message(FollowupAdminStates.waiting_content_type, F.text)
async def followup_step_content_type(message: Message, state: FSMContext) -> None:
    ct = (message.text or "").strip()
    if ct not in {"fixed", "llm"}:
        await message.answer("Допустимо: fixed | llm")
        return
    await state.update_data(content_type=ct)
    if ct == "fixed":
        await state.set_state(FollowupAdminStates.waiting_fixed_text)
        await message.answer("Введите fixed_text (текст сообщения):")
    else:
        await state.set_state(FollowupAdminStates.waiting_prompt_template_id)
        await message.answer("Введите prompt_template_id (scope followup или любой, ваш шаблон):")


@router.message(FollowupAdminStates.waiting_fixed_text, F.text)
async def followup_step_fixed_text(message: Message, state: FSMContext) -> None:
    await state.update_data(fixed_text=(message.text or "").strip(), prompt_template_id=None)
    await state.set_state(FollowupAdminStates.waiting_target_channel)
    await message.answer("Введите target_channel (пока только: telegram_user):")


@router.message(FollowupAdminStates.waiting_prompt_template_id, F.text)
async def followup_step_prompt_template_id(message: Message, state: FSMContext, session: AsyncSession) -> None:
    if not message.text or not message.text.strip().isdigit():
        await message.answer("Введите числовой prompt_template_id.")
        return
    pid = int(message.text.strip())
    res = await session.execute(
        select(PromptTemplate).where(
            PromptTemplate.id == pid,
            PromptTemplate.owner_id == message.from_user.id,
        )
    )
    if res.scalar_one_or_none() is None:
        await message.answer("Шаблон не найден или не ваш.")
        return
    await state.update_data(prompt_template_id=pid, fixed_text=None)
    await state.set_state(FollowupAdminStates.waiting_target_channel)
    await message.answer("Введите target_channel (пока только: telegram_user):")


@router.message(FollowupAdminStates.waiting_target_channel, F.text)
async def followup_step_target_channel(message: Message, state: FSMContext, session: AsyncSession) -> None:
    ch = (message.text or "").strip()
    if ch != "telegram_user":
        await message.answer("Пока допустимо только: telegram_user")
        return
    await state.update_data(target_channel=ch)
    data = await state.get_data()
    chain_id = data["chain_id"]
    step_id = data.get("step_id")
    if step_id is not None:
        res = await session.execute(
            select(FollowupStep).join(FollowupChain, FollowupChain.id == FollowupStep.chain_id).join(
                AIBranch, AIBranch.id == FollowupChain.branch_id
            ).where(FollowupStep.id == step_id, AIBranch.owner_id == message.from_user.id)
        )
        step = res.scalar_one_or_none()
        if not step:
            await message.answer("Шаг не найден.")
            await state.clear()
            return
        step.order_index = data["order_index"]
        step.delay_seconds = data["delay_seconds"]
        step.send_mode = data["send_mode"]
        step.content_type = data["content_type"]
        step.fixed_text = data.get("fixed_text")
        step.prompt_template_id = data.get("prompt_template_id")
        step.target_channel = ch
        await state.clear()
        await message.answer("✅ Шаг обновлён.")
    else:
        step = FollowupStep(
            chain_id=chain_id,
            order_index=data["order_index"],
            delay_seconds=data["delay_seconds"],
            send_mode=data["send_mode"],
            content_type=data["content_type"],
            fixed_text=data.get("fixed_text"),
            prompt_template_id=data.get("prompt_template_id"),
            target_channel=ch,
        )
        session.add(step)
        await state.clear()
        await message.answer("✅ Шаг создан.")


@router.callback_query(F.data.startswith("ai_followup:step_edit:"))
async def cb_followup_step_edit(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    try:
        step_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Некорректный id.", show_alert=True)
        return
    res = await session.execute(
        select(FollowupStep).join(FollowupChain, FollowupChain.id == FollowupStep.chain_id).join(
            AIBranch, AIBranch.id == FollowupChain.branch_id
        ).where(FollowupStep.id == step_id, AIBranch.owner_id == callback.from_user.id)
    )
    step = res.scalar_one_or_none()
    if not step:
        await callback.answer("Шаг не найден.", show_alert=True)
        return
    await state.clear()
    await state.update_data(
        step_id=step.id,
        chain_id=step.chain_id,
        order_index=step.order_index,
        delay_seconds=step.delay_seconds,
        send_mode=step.send_mode,
        content_type=step.content_type,
        fixed_text=step.fixed_text,
        prompt_template_id=step.prompt_template_id,
    )
    await state.set_state(FollowupAdminStates.waiting_order_index)
    await callback.message.answer(f"Редактирование шага #{step.id}. Введите order_index (текущий: {step.order_index}):")
    await callback.answer()


@router.callback_query(F.data.startswith("ai_followup:step_delete:"))
async def cb_followup_step_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        step_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Некорректный id.", show_alert=True)
        return
    res = await session.execute(
        select(FollowupStep).join(FollowupChain, FollowupChain.id == FollowupStep.chain_id).join(
            AIBranch, AIBranch.id == FollowupChain.branch_id
        ).where(FollowupStep.id == step_id, AIBranch.owner_id == callback.from_user.id)
    )
    step = res.scalar_one_or_none()
    if not step:
        await callback.answer("Шаг не найден.", show_alert=True)
        return
    builder = InlineKeyboardBuilder()
    builder.row(
        builder.button(text="✅ Удалить", callback_data=f"ai_followup:step_confirm_delete:{step.id}"),
        builder.button(text="❌ Отмена", callback_data="ai_followup:step_cancel_delete"),
    )
    await callback.message.answer(f"Удалить шаг #{step.id}?", reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data.startswith("ai_followup:step_confirm_delete:"))
async def cb_followup_step_confirm_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    try:
        step_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Некорректный id.", show_alert=True)
        return
    res = await session.execute(
        select(FollowupStep).join(FollowupChain, FollowupChain.id == FollowupStep.chain_id).join(
            AIBranch, AIBranch.id == FollowupChain.branch_id
        ).where(FollowupStep.id == step_id, AIBranch.owner_id == callback.from_user.id)
    )
    step = res.scalar_one_or_none()
    if not step:
        await callback.answer("Шаг не найден.", show_alert=True)
        return
    await session.delete(step)
    await callback.message.answer("✅ Шаг удалён.")
    await callback.answer()


@router.callback_query(F.data == "ai_followup:step_cancel_delete")
async def cb_followup_step_cancel_delete(callback: CallbackQuery) -> None:
    await callback.answer("Отменено.")


@router.callback_query(F.data == "ai_admin:prompts")
async def cb_admin_prompts(callback: CallbackQuery) -> None:
    await callback.answer("/prompts | /prompts_new")


@router.callback_query(F.data == "ai_admin:branches")
async def cb_admin_branches(callback: CallbackQuery) -> None:
    await callback.answer("/ai_branches | /ai_branches_new")


@router.callback_query(F.data == "ai_admin:followups")
async def cb_admin_followups(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    await callback.message.answer("Цепочки followup:")
    await _followups_list(callback.message, session, callback.from_user.id if callback.from_user else 0)
    await callback.answer()

"""AI admin handlers: /prompts, /ai_branches, /followups."""
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards import ai_admin_menu_kb
from bot.states import BranchAdminStates, FollowupAdminStates, PromptAdminStates
from core.database.models import AIBranch, AvitoProfile, FollowupChain, PromptTemplate

logger = logging.getLogger(__name__)
router = Router(name="ai_admin")


@router.message(Command("prompts"))
async def cmd_prompts(message: Message, session: AsyncSession, state: FSMContext) -> None:
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
    await message.answer(f"<b>Prompt templates</b>\n{text}")


@router.message(Command("prompts_new"))
async def cmd_prompts_new(message: Message, state: FSMContext) -> None:
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


@router.message(Command("ai_branches"))
async def cmd_ai_branches(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    result = await session.execute(select(AIBranch).where(AIBranch.owner_id == message.from_user.id))
    rows = list(result.scalars().all())
    if not rows:
        await message.answer("AI-ветки не найдены. Создать: /ai_branches_new")
        return
    text = "\n".join([f"#{b.id} {b.name} model={b.gpt_model} prompt={b.system_prompt_id}" for b in rows])
    await message.answer(f"<b>AI branches</b>\n{text}")


@router.message(Command("ai_branches_new"))
async def cmd_ai_branches_new(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(BranchAdminStates.waiting_name)
    await message.answer("Введите название ветки:")


@router.message(BranchAdminStates.waiting_name, F.text)
async def branch_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())
    await state.set_state(BranchAdminStates.waiting_avito_profile_id)
    await message.answer("Введите avito_profile_id:")


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
    data = await state.get_data()
    prompt_id = int(message.text)
    prompt_res = await session.execute(
        select(PromptTemplate).where(
            PromptTemplate.id == prompt_id,
            PromptTemplate.owner_id == message.from_user.id,
        )
    )
    if prompt_res.scalar_one_or_none() is None:
        await message.answer("Prompt template не найден")
        return
    item = AIBranch(
        owner_id=message.from_user.id,
        name=data["name"],
        avito_profile_id=data["avito_profile_id"],
        gpt_model=data["gpt_model"],
        system_prompt_id=prompt_id,
        context_retention_days=None,
        max_messages_in_context=None,
        followup_enabled=False,
    )
    session.add(item)
    await state.clear()
    await message.answer("✅ AI-ветка сохранена")


@router.message(Command("followups"))
async def cmd_followups(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Меню AI-админки", reply_markup=ai_admin_menu_kb())
    result = await session.execute(
        select(FollowupChain)
        .join(AIBranch, AIBranch.id == FollowupChain.branch_id)
        .where(AIBranch.owner_id == message.from_user.id)
    )
    rows = list(result.scalars().all())
    if rows:
        text = "\n".join([f"#{r.id} {r.name} [{r.start_event}] active={r.is_active}" for r in rows])
        await message.answer(f"<b>Followup chains</b>\n{text}")


@router.message(Command("followups_new"))
async def cmd_followups_new(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(FollowupAdminStates.waiting_chain_name)
    await message.answer("Введите: <branch_id>;<name>;<start_event>")


@router.message(FollowupAdminStates.waiting_chain_name, F.text)
async def followup_chain_create(message: Message, state: FSMContext, session: AsyncSession) -> None:
    parts = [p.strip() for p in message.text.split(";")]
    if len(parts) != 3 or not parts[0].isdigit():
        await message.answer("Формат: <branch_id>;<name>;<start_event>")
        return
    branch_id = int(parts[0])
    name = parts[1]
    start_event = parts[2]
    if start_event not in {"dialog_started", "no_reply", "manual"}:
        await message.answer("start_event: dialog_started|no_reply|manual")
        return
    branch_res = await session.execute(
        select(AIBranch).where(AIBranch.id == branch_id, AIBranch.owner_id == message.from_user.id)
    )
    if branch_res.scalar_one_or_none() is None:
        await message.answer("Ветка не найдена")
        return
    item = FollowupChain(
        branch_id=branch_id,
        name=name,
        is_active=True,
        start_event=start_event,
        stop_on_conversion=True,
    )
    session.add(item)
    await state.clear()
    await message.answer("✅ Followup chain сохранена")


@router.callback_query(F.data == "ai_admin:prompts")
async def cb_admin_prompts(callback: CallbackQuery) -> None:
    await callback.answer("/prompts | /prompts_new")


@router.callback_query(F.data == "ai_admin:branches")
async def cb_admin_branches(callback: CallbackQuery) -> None:
    await callback.answer("/ai_branches | /ai_branches_new")


@router.callback_query(F.data == "ai_admin:followups")
async def cb_admin_followups(callback: CallbackQuery) -> None:
    await callback.answer("/followups | /followups_new")

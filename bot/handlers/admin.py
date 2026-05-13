import asyncio

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from bot.auth import is_superadmin
from bot.config import SUPERADMIN_IDS
from shared.database import SessionLocal
from shared.models import AdminUser, Broadcast, BroadcastLog, Group, GroupLabel, Label

router = Router()


# ── FSM States ─────────────────────────────────────────────────────────────────

class BroadcastStates(StatesGroup):
    choosing_label = State()
    typing_message = State()
    confirming = State()


class AssignStates(StatesGroup):
    choosing_group = State()
    choosing_label = State()


# ── Keyboard helpers ───────────────────────────────────────────────────────────

def groups_keyboard(groups: list[Group], action: str) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            text=f"{'🟢 ' if g.is_active else '🔴 '}{g.title}",
            callback_data=f"{action}:group:{g.id}",
        )]
        for g in groups
    ]
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def labels_keyboard(labels: list[Label], action: str, extra: str = "") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            text=f"🏷 {lb.name}",
            callback_data=f"{action}:label:{lb.id}:{extra}",
        )]
        for lb in labels
    ]
    buttons.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_keyboard(yes_data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да, отправить", callback_data=yes_data),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
    ]])


# ── /groups ────────────────────────────────────────────────────────────────────

@router.message(Command("groups"), F.chat.type == "private")
async def cmd_groups(message: Message):
    with SessionLocal() as db:
        groups = db.query(Group).order_by(Group.title).all()
        if not groups:
            await message.answer("Бот ещё не добавлен ни в одну группу.")
            return
        lines = []
        for g in groups:
            status = "🟢" if g.is_active else "🔴"
            label_names = ", ".join(lb.name for lb in g.labels) or "—"
            link = f"@{g.username}" if g.username else str(g.telegram_id)
            lines.append(f"{status} <b>{g.title}</b> ({link})\n   ярлыки: {label_names}")
        await message.answer("\n\n".join(lines), parse_mode="HTML")


# ── /labels ────────────────────────────────────────────────────────────────────

@router.message(Command("labels"), F.chat.type == "private")
async def cmd_labels(message: Message):
    with SessionLocal() as db:
        labels = db.query(Label).order_by(Label.name).all()
        if not labels:
            await message.answer("Ярлыков нет. Создайте: /newlabel &lt;название&gt;", parse_mode="HTML")
            return
        lines = []
        for lb in labels:
            count = len(lb.groups)
            desc = f": {lb.description}" if lb.description else ""
            lines.append(f"🏷 <b>{lb.name}</b> — {count} групп(ы){desc}")
        await message.answer("\n".join(lines), parse_mode="HTML")


# ── /newlabel ──────────────────────────────────────────────────────────────────

@router.message(Command("newlabel"), F.chat.type == "private")
async def cmd_newlabel(message: Message):
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer("Использование: /newlabel &lt;название&gt; [описание]", parse_mode="HTML")
        return
    parts = args[1].strip().split(maxsplit=1)
    name = parts[0].lower().replace(" ", "_")
    desc = parts[1] if len(parts) > 1 else None
    with SessionLocal() as db:
        if db.query(Label).filter_by(name=name).first():
            await message.answer(f"Ярлык <b>{name}</b> уже существует.", parse_mode="HTML")
            return
        db.add(Label(name=name, description=desc))
        db.commit()
    await message.answer(f"✅ Ярлык <b>{name}</b> создан.", parse_mode="HTML")


# ── /dellabel ──────────────────────────────────────────────────────────────────

@router.message(Command("dellabel"), F.chat.type == "private")
async def cmd_dellabel(message: Message):
    args = (message.text or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Использование: /dellabel &lt;название&gt;", parse_mode="HTML")
        return
    name = args[1].strip().lower()
    with SessionLocal() as db:
        label = db.query(Label).filter_by(name=name).first()
        if not label:
            await message.answer(f"Ярлык <b>{name}</b> не найден.", parse_mode="HTML")
            return
        db.delete(label)
        db.commit()
    await message.answer(f"🗑 Ярлык <b>{name}</b> удалён.", parse_mode="HTML")


# ── /assign ────────────────────────────────────────────────────────────────────

@router.message(Command("assign"), F.chat.type == "private")
async def cmd_assign(message: Message, state: FSMContext):
    with SessionLocal() as db:
        groups = db.query(Group).filter_by(is_active=1).order_by(Group.title).all()
        if not groups:
            await message.answer("Активных групп нет.")
            return
        kb = groups_keyboard(groups, "asgn")
    await message.answer("Выберите группу для назначения ярлыка:", reply_markup=kb)
    await state.set_state(AssignStates.choosing_group)
    await state.update_data(action="assign")


# ── /unassign ──────────────────────────────────────────────────────────────────

@router.message(Command("unassign"), F.chat.type == "private")
async def cmd_unassign(message: Message, state: FSMContext):
    with SessionLocal() as db:
        groups = db.query(Group).filter_by(is_active=1).order_by(Group.title).all()
        if not groups:
            await message.answer("Активных групп нет.")
            return
        kb = groups_keyboard(groups, "unasgn")
    await message.answer("Выберите группу для снятия ярлыка:", reply_markup=kb)
    await state.set_state(AssignStates.choosing_group)
    await state.update_data(action="unassign")


@router.callback_query(F.data.startswith("asgn:group:"), AssignStates.choosing_group)
async def assign_group_chosen(call: CallbackQuery, state: FSMContext):
    group_id = int(call.data.split(":")[2])
    await state.update_data(group_id=group_id)
    with SessionLocal() as db:
        labels = db.query(Label).order_by(Label.name).all()
        if not labels:
            await call.message.edit_text("Ярлыков нет. Создайте: /newlabel")
            await state.clear()
            return
        kb = labels_keyboard(labels, "asgn", str(group_id))
    await call.message.edit_text("Выберите ярлык для назначения:", reply_markup=kb)
    await state.set_state(AssignStates.choosing_label)


@router.callback_query(F.data.startswith("unasgn:group:"), AssignStates.choosing_group)
async def unassign_group_chosen(call: CallbackQuery, state: FSMContext):
    group_id = int(call.data.split(":")[2])
    with SessionLocal() as db:
        group = db.query(Group).get(group_id)
        labels = list(group.labels) if group else []
        if not labels:
            await call.message.edit_text("У этой группы нет ярлыков.")
            await state.clear()
            return
        kb = labels_keyboard(labels, "unasgn", str(group_id))
    await call.message.edit_text("Выберите ярлык для снятия:", reply_markup=kb)
    await state.set_state(AssignStates.choosing_label)


@router.callback_query(F.data.startswith("asgn:label:"), AssignStates.choosing_label)
async def do_assign(call: CallbackQuery, state: FSMContext):
    _, _, label_id_str, group_id_str = call.data.split(":")
    label_id, group_id = int(label_id_str), int(group_id_str)
    with SessionLocal() as db:
        group = db.query(Group).get(group_id)
        label = db.query(Label).get(label_id)
        if not group or not label:
            await call.message.edit_text("Ошибка: группа или ярлык не найдены.")
            await state.clear()
            return
        exists = db.query(GroupLabel).filter_by(group_id=group_id, label_id=label_id).first()
        if exists:
            await call.message.edit_text(
                f"ℹ️ Группа <b>{group.title}</b> уже имеет ярлык <b>{label.name}</b>.",
                parse_mode="HTML",
            )
        else:
            db.add(GroupLabel(group_id=group_id, label_id=label_id))
            db.commit()
            await call.message.edit_text(
                f"✅ Ярлык <b>{label.name}</b> назначен группе <b>{group.title}</b>.",
                parse_mode="HTML",
            )
    await state.clear()


@router.callback_query(F.data.startswith("unasgn:label:"), AssignStates.choosing_label)
async def do_unassign(call: CallbackQuery, state: FSMContext):
    _, _, label_id_str, group_id_str = call.data.split(":")
    label_id, group_id = int(label_id_str), int(group_id_str)
    with SessionLocal() as db:
        group = db.query(Group).get(group_id)
        label = db.query(Label).get(label_id)
        row = db.query(GroupLabel).filter_by(group_id=group_id, label_id=label_id).first()
        if row:
            db.delete(row)
            db.commit()
            await call.message.edit_text(
                f"🗑 Ярлык <b>{label.name}</b> снят с группы <b>{group.title}</b>.",
                parse_mode="HTML",
            )
        else:
            await call.message.edit_text("Этот ярлык не был назначен группе.")
    await state.clear()


# ── /broadcast ─────────────────────────────────────────────────────────────────

@router.message(Command("broadcast"), F.chat.type == "private")
async def cmd_broadcast(message: Message, state: FSMContext):
    with SessionLocal() as db:
        labels = db.query(Label).order_by(Label.name).all()
        if not labels:
            await message.answer("Ярлыков нет. Сначала создайте: /newlabel")
            return
        kb = labels_keyboard(labels, "bcast", "")
    await message.answer("Выберите ярлык для рассылки:", reply_markup=kb)
    await state.set_state(BroadcastStates.choosing_label)


@router.callback_query(F.data.startswith("bcast:label:"), BroadcastStates.choosing_label)
async def broadcast_label_chosen(call: CallbackQuery, state: FSMContext):
    parts = call.data.split(":")
    label_id = int(parts[2])
    with SessionLocal() as db:
        label = db.query(Label).get(label_id)
        if not label:
            await call.message.edit_text("Ярлык не найден.")
            await state.clear()
            return
        group_count = len([g for g in label.groups if g.is_active])
    await state.update_data(label_id=label_id, label_name=label.name, group_count=group_count)
    await call.message.edit_text(
        f"Ярлык: <b>{label.name}</b> ({group_count} активных групп)\n\n"
        "Введите текст сообщения для рассылки.\n"
        "Поддерживается HTML: <code>&lt;b&gt;</code>, <code>&lt;i&gt;</code>, <code>&lt;a href=''&gt;</code>\n\n"
        "/cancel — отмена.",
        parse_mode="HTML",
    )
    await state.set_state(BroadcastStates.typing_message)


@router.message(BroadcastStates.typing_message, F.text)
async def broadcast_message_typed(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer("Отменено.")
        return
    data = await state.get_data()
    await state.update_data(text=message.text)
    kb = confirm_keyboard(f"bcast_confirm:{data['label_id']}")
    await message.answer(
        f"📢 <b>Предпросмотр рассылки</b>\n"
        f"Ярлык: <b>{data['label_name']}</b> | Групп: <b>{data['group_count']}</b>\n"
        f"{'─' * 30}\n{message.text}\n{'─' * 30}\n\nОтправить?",
        parse_mode="HTML",
        reply_markup=kb,
    )
    await state.set_state(BroadcastStates.confirming)


@router.callback_query(F.data.startswith("bcast_confirm:"), BroadcastStates.confirming)
async def broadcast_confirmed(call: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await state.clear()
    label_id = int(call.data.split(":")[1])
    text = data.get("text", "")
    sender = call.from_user.username or str(call.from_user.id)

    await call.message.edit_text("⏳ Отправляю рассылку...")

    with SessionLocal() as db:
        label = db.query(Label).get(label_id)
        if not label:
            await call.message.edit_text("Ярлык не найден.")
            return
        groups = [g for g in label.groups if g.is_active]
        broadcast = Broadcast(label_id=label_id, message=text, sent_by=sender)
        db.add(broadcast)
        db.flush()
        broadcast_id = broadcast.id

        ok, fail = 0, 0
        for group in groups:
            try:
                await bot.send_message(group.telegram_id, text, parse_mode="HTML")
                db.add(BroadcastLog(broadcast_id=broadcast_id, group_id=group.id, success=1))
                ok += 1
            except Exception as e:
                db.add(BroadcastLog(broadcast_id=broadcast_id, group_id=group.id, success=0, error=str(e)[:255]))
                fail += 1
            await asyncio.sleep(0.05)

        broadcast.success_count = ok
        broadcast.fail_count = fail
        db.commit()

    await call.message.edit_text(
        f"✅ Рассылка завершена!\n📨 Успешно: <b>{ok}</b>\n❌ Ошибок: <b>{fail}</b>",
        parse_mode="HTML",
    )


# ── /history ───────────────────────────────────────────────────────────────────

@router.message(Command("history"), F.chat.type == "private")
async def cmd_history(message: Message):
    with SessionLocal() as db:
        broadcasts = (
            db.query(Broadcast)
            .order_by(Broadcast.sent_at.desc())
            .limit(10)
            .all()
        )
        if not broadcasts:
            await message.answer("История рассылок пуста.")
            return
        lines = []
        for b in broadcasts:
            label_name = b.label.name if b.label else "удалён"
            preview = (b.message[:60] + "…") if len(b.message) > 60 else b.message
            dt = b.sent_at.strftime("%d.%m %H:%M")
            lines.append(
                f"📅 <b>{dt}</b> | 🏷 {label_name} | ✅{b.success_count} ❌{b.fail_count}\n"
                f"   <i>{preview}</i>"
            )
        await message.answer("\n\n".join(lines), parse_mode="HTML")


# ── Admin management (superadmin only) ────────────────────────────────────────

@router.message(Command("admins"), F.chat.type == "private")
async def cmd_admins(message: Message):
    if not is_superadmin(message.from_user.id):
        await message.answer("⛔ Только суперадминистраторы могут просматривать список.")
        return
    with SessionLocal() as db:
        db_admins = db.query(AdminUser).filter_by(is_active=1).order_by(AdminUser.added_at).all()

    lines = ["<b>👑 Суперадмины (из конфига):</b>"]
    for uid in sorted(SUPERADMIN_IDS):
        lines.append(f"  • <code>{uid}</code>")

    lines.append("\n<b>🔑 Администраторы (из БД):</b>")
    if db_admins:
        for a in db_admins:
            name = f"@{a.username}" if a.username else a.full_name or "—"
            added_by = f"@{a.added_by_name}" if a.added_by_name else str(a.added_by_id)
            lines.append(
                f"  • {name} (<code>{a.telegram_id}</code>)\n"
                f"    добавил: {added_by} | {a.added_at.strftime('%d.%m.%Y')}"
            )
    else:
        lines.append("  Нет дополнительных администраторов.")

    lines.append("\n/addadmin &lt;id&gt; — добавить\n/removeadmin &lt;id&gt; — удалить")
    await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("addadmin"), F.chat.type == "private")
async def cmd_addadmin(message: Message):
    if not is_superadmin(message.from_user.id):
        await message.answer("⛔ Только суперадминистраторы могут добавлять администраторов.")
        return

    args = (message.text or "").split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer(
            "Использование: /addadmin &lt;telegram_id&gt;\n\n"
            "Пользователь может узнать свой ID, написав боту — "
            "он получит его в сообщении об отказе в доступе.",
            parse_mode="HTML",
        )
        return

    new_id = int(args[1])

    if new_id in SUPERADMIN_IDS:
        await message.answer("Этот пользователь уже является суперадмином.")
        return

    with SessionLocal() as db:
        existing = db.query(AdminUser).filter_by(telegram_id=new_id).first()
        if existing:
            if existing.is_active:
                await message.answer(f"Пользователь <code>{new_id}</code> уже является администратором.", parse_mode="HTML")
                return
            existing.is_active = 1
            existing.added_by_id = message.from_user.id
            existing.added_by_name = message.from_user.username
        else:
            db.add(AdminUser(
                telegram_id=new_id,
                added_by_id=message.from_user.id,
                added_by_name=message.from_user.username,
            ))
        db.commit()

    await message.answer(
        f"✅ Пользователь <code>{new_id}</code> добавлен как администратор.",
        parse_mode="HTML",
    )


@router.message(Command("removeadmin"), F.chat.type == "private")
async def cmd_removeadmin(message: Message):
    if not is_superadmin(message.from_user.id):
        await message.answer("⛔ Только суперадминистраторы могут удалять администраторов.")
        return

    args = (message.text or "").split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("Использование: /removeadmin &lt;telegram_id&gt;", parse_mode="HTML")
        return

    target_id = int(args[1])

    if target_id in SUPERADMIN_IDS:
        await message.answer("⛔ Нельзя удалить суперадмина. Уберите его ID из конфига.")
        return

    with SessionLocal() as db:
        admin_user = db.query(AdminUser).filter_by(telegram_id=target_id, is_active=1).first()
        if not admin_user:
            await message.answer(f"Администратор <code>{target_id}</code> не найден.", parse_mode="HTML")
            return
        admin_user.is_active = 0
        db.commit()

    await message.answer(
        f"🗑 Пользователь <code>{target_id}</code> удалён из администраторов.",
        parse_mode="HTML",
    )


# ── Cancel ─────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "cancel")
async def cancel_callback(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("Отменено.")


@router.message(Command("cancel"), F.chat.type == "private")
async def cancel_command(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.")

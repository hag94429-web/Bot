import asyncio
import json
import os
import re
import time
import random
import string
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.filters.command import CommandStart
from aiogram.types import (
    InlineQueryResultArticle,
    InputTextMessageContent,
    LabeledPrice
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
LINK_TO_BANK = os.getenv("LINK_TO_BANK")
OWNER_IDS_RAW = os.getenv("OWNER_IDS") or os.getenv("OWNER_ID", "")
ANTI_SPAM_SECONDS = int(os.getenv("ANTI_SPAM_SECONDS", "30"))

if not API_TOKEN:
    raise ValueError("Не знайдено API_TOKEN у .env")

if not LINK_TO_BANK:
    raise ValueError("Не знайдено LINK_TO_BANK у .env")

OWNER_IDS = [int(x) for x in OWNER_IDS_RAW.split(",") if x.strip().isdigit()]
if not OWNER_IDS:
    raise ValueError("Не знайдено OWNER_IDS або OWNER_ID у .env")

USERS_FILE = "users.json"
USER_MODES_FILE = "user_modes.json"
REPLY_MAP_FILE = "reply_map.json"
PAYMENTS_FILE = "payments.json"
TEAMS_FILE = "teams.json"

STAR_PACKS = [50, 100, 250, 500]

bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
)
dp = Dispatcher()

UKRAINE_TZ = ZoneInfo("Europe/Kyiv")
last_send = {}

def load_json(file, default):
    if not os.path.exists(file):
        return default
    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

users = load_json(USERS_FILE, {})
user_modes = load_json(USER_MODES_FILE, {})
reply_map = load_json(REPLY_MAP_FILE, {})
teams = load_json(TEAMS_FILE, {})

if not isinstance(users, dict):
    users = {}

if not isinstance(user_modes, dict):
    user_modes = {}

if not isinstance(reply_map, dict):
    reply_map = {}

if not isinstance(teams, dict):
    teams = {}

def ensure_user(uid: int):
    uid_str = str(uid)
    if uid_str not in users:
        users[uid_str] = {}
        save_json(USERS_FILE, users)

def is_owner(uid: int) -> bool:
    return uid in OWNER_IDS

def is_russian(text: str) -> bool:
    if not text:
        return False
    return bool(re.search(r"[ыЫэЭъЪёЁ]", text))

def anti_spam(uid: int) -> bool:
    now = time.time()
    last = last_send.get(uid, 0)

    if now - last < ANTI_SPAM_SECONDS:
        return False

    last_send[uid] = now
    return True

def get_wait_seconds(uid: int) -> int:
    now = time.time()
    last = last_send.get(uid, 0)
    left = int(ANTI_SPAM_SECONDS - (now - last))
    return max(left, 1)

def normalize_targets(raw_targets):
    result = []
    seen = set()

    for item in raw_targets:
        item = str(item).strip()
        if not item.isdigit():
            continue
        if item in seen:
            continue
        seen.add(item)
        result.append(item)

    return result

def parse_targets(arg: str, current_user_id: int):
    arg = (arg or "").strip()
    current_user_id = str(current_user_id)

    if arg in teams:
        raw_targets = teams[arg]
        targets = normalize_targets(raw_targets)
    else:
        raw_targets = re.split(r"[,\s]+", arg)
        targets = normalize_targets(raw_targets)

    targets = [t for t in targets if t != current_user_id]
    return targets

def payment_total_stars():
    payments = load_json(PAYMENTS_FILE, [])
    if not isinstance(payments, list):
        return 0
    return sum(p.get("amount", 0) for p in payments if isinstance(p, dict))

def generate_team_key():
    while True:
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
        key = f"team_{suffix}"
        if key not in teams:
            return key

def main_menu():
    kb = ReplyKeyboardBuilder()
    kb.row(types.KeyboardButton(text="🔗 Моє посилання"))
    kb.row(types.KeyboardButton(text="⭐ Підтримати в зірках"))
    kb.row(types.KeyboardButton(text="☕ Підтримати бота"))
    kb.row(types.KeyboardButton(text="❓ Як це працює"))
    return kb.as_markup(resize_keyboard=True)

def stars_menu():
    kb = InlineKeyboardBuilder()
    for s in STAR_PACKS:
        kb.row(
            types.InlineKeyboardButton(
                text=f"⭐ {s}",
                callback_data=f"stars:{s}"
            )
        )
    return kb.as_markup()

@dp.message(CommandStart())
async def start(message: types.Message, command: CommandObject):
    ensure_user(message.from_user.id)

    if command.args:
        targets = parse_targets(command.args, message.from_user.id)

        if not targets:
            await message.answer("❌ Невірне посилання або немає коректних ID.")
            return

        user_modes[str(message.from_user.id)] = targets
        save_json(USER_MODES_FILE, user_modes)

        if len(targets) == 1:
            await message.answer(
                "🤫 Режим анонімки активовано!\n"
                "Напиши текст, надішли фото, голосове, кружок, GIF або стікер."
            )
        else:
            await message.answer(
                f"🤫 Режим анонімки активовано для {len(targets)} отримувачів!\n"
                "Напиши текст, надішли фото, голосове, кружок, GIF або стікер."
            )
    else:
        await message.answer(
            "Привіт 👋",
            reply_markup=main_menu()
        )

@dp.message(Command("createteam"))
async def create_team(message: types.Message, command: CommandObject):
    ensure_user(message.from_user.id)

    raw_args = (command.args or "").strip()
    if not raw_args:
        await message.answer(
            "❌ Використання:\n`/createteam 123456789 987654321`\n\n"
            "Або через кому:\n`/createteam 123456789,987654321`"
        )
        return

    raw_targets = re.split(r"[,\s]+", raw_args)
    targets = normalize_targets(raw_targets)

    creator_id = str(message.from_user.id)
    if creator_id not in targets:
        targets.insert(0, creator_id)

    if len(targets) < 2:
        await message.answer("❌ Потрібно мінімум 2 ID для team.")
        return

    team_key = generate_team_key()
    teams[team_key] = targets
    save_json(TEAMS_FILE, teams)

    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={team_key}"

    await message.answer(
        f"✅ Team створено: `{team_key}`\n\n"
        f"👥 Учасників: {len(targets)}\n"
        f"🔗 Спільна силка:\n`{link}`"
    )
    
@dp.message(Command("teamlink"))
async def team_link(message: types.Message, command: CommandObject):
    key = (command.args or "").strip()

    if not key:
        await message.answer("❌ Використання: `/teamlink team_xxxxxx`")
        return

    if key not in teams:
        await message.answer("❌ Такої team немає.")
        return

    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={key}"

    await message.answer(
        f"🔗 Силка для `{key}`:\n`{link}`"
    )

@dp.message(F.text == "🔗 Моє посилання")
async def my_link(message: types.Message):
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={message.from_user.id}"

    await message.answer(
        f"Твоє посилання:\n\n`{link}`",
        reply_markup=main_menu()
    )

@dp.message(F.text == "❓ Як це працює")
async def help_cmd(message: types.Message):
    await message.answer(
        "Люди пишуть тобі анонімно через посилання.\n"
        "Підтримуються текст, фото, голосові, кружки, GIF і стікери.\n"
        "Також можна робити спільні силки через teams.json або /createteam."
    )

@dp.message(F.text == "☕ Підтримати бота")
async def donate(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(
            text="Відкрити банку",
            url=LINK_TO_BANK
        )
    )

    await message.answer(
        "Дякуємо ❤️",
        reply_markup=kb.as_markup()
    )

@dp.message(F.text == "⭐ Підтримати в зірках")
async def stars(message: types.Message):
    await message.answer(
        "Обери суму ⭐",
        reply_markup=stars_menu()
    )

@dp.callback_query(F.data.startswith("stars:"))
async def stars_pay(callback: types.CallbackQuery):
    try:
        amount = int(callback.data.split(":")[1])
    except Exception:
        await callback.answer("❌ Помилка суми", show_alert=True)
        return

    if amount not in STAR_PACKS:
        await callback.answer("❌ Невірна сума", show_alert=True)
        return

    await callback.answer()

    await bot.send_invoice(
        chat_id=callback.from_user.id,
        title="Підтримка бота",
        description="Дякуємо за донат ⭐",
        payload=f"stars_{amount}",
        currency="XTR",
        prices=[LabeledPrice(label="Stars", amount=amount)]
    )

@dp.pre_checkout_query()
async def checkout(pre_checkout_query: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(F.successful_payment)
async def payment_success(message: types.Message):
    payments = load_json(PAYMENTS_FILE, [])
    if not isinstance(payments, list):
        payments = []

    payments.append({
        "user": message.from_user.id,
        "username": message.from_user.username,
        "first_name": message.from_user.first_name,
        "amount": message.successful_payment.total_amount,
        "currency": message.successful_payment.currency,
        "payload": message.successful_payment.invoice_payload,
        "date": datetime.now(UKRAINE_TZ).strftime("%Y-%m-%d %H:%M:%S")
    })

    save_json(PAYMENTS_FILE, payments)

    await message.answer("⭐ Дякуємо за підтримку!")

@dp.message(Command("stats"))
async def stats(message: types.Message):
    if not is_owner(message.from_user.id):
        return

    await message.answer(
        f"📊 Статистика\n\n"
        f"👥 Користувачів: {len(users)}\n"
        f"⭐ Донатів: {payment_total_stars()}\n"
        f"👥 Team: {len(teams)}"
    )

@dp.message(Command("payments"))
async def payments_cmd(message: types.Message):
    if not is_owner(message.from_user.id):
        return

    payments = load_json(PAYMENTS_FILE, [])
    if not isinstance(payments, list):
        payments = []

    if not payments:
        await message.answer("Донатів немає")
        return

    text = "💸 Останні донати\n\n"

    for p in payments[-10:]:
        amount = p.get("amount", 0)
        date = p.get("date", "—")
        first_name = p.get("first_name", "Без імені")
        username = p.get("username")
        username_text = f"@{username}" if username else "без username"

        text += f"⭐ {amount} — {date}\n{first_name} ({username_text})\n\n"

    await message.answer(text)

@dp.message(Command("broadcast"))
async def broadcast(message: types.Message, command: CommandObject):
    if not is_owner(message.from_user.id):
        return

    text = (command.args or "").strip()

    if not text:
        await message.answer("Напиши текст")
        return

    ok = 0
    bad = 0

    for uid in users:
        try:
            await bot.send_message(int(uid), text)
            ok += 1
        except Exception:
            bad += 1

    await message.answer(
        f"Розсилка завершена\n\n"
        f"OK: {ok}\n"
        f"BAD: {bad}"
    )

@dp.message(F.forward_origin)
async def block_forwarded(message: types.Message):
    await message.answer("❌ Переслані повідомлення не підтримуються.")

@dp.message(F.text | F.photo | F.voice | F.video_note | F.animation | F.sticker)
async def anon(message: types.Message):
    uid = str(message.from_user.id)
    ensure_user(message.from_user.id)

    text_content = message.text or message.caption

    if message.reply_to_message:
        mid = str(message.reply_to_message.message_id)

        if mid in reply_map:
            if is_russian(text_content):
                await message.reply("Пишіть українською! 🇺🇦")
                return

            target = int(reply_map[mid])

            try:
                sent = await bot.copy_message(
                    chat_id=target,
                    from_chat_id=message.chat.id,
                    message_id=message.message_id
                )
                reply_map[str(sent.message_id)] = uid
                save_json(REPLY_MAP_FILE, reply_map)
                await message.reply("Відправлено")
            except Exception:
                await message.reply("❌ Помилка відправки")

            return

    if uid not in user_modes:
        return

    if is_russian(text_content):
        await message.reply("Тільки українською 🇺🇦")
        return

    if not anti_spam(message.from_user.id):
        await message.reply(f"Зачекай {get_wait_seconds(message.from_user.id)} сек.")
        return

    targets = user_modes[uid]
    ok = 0
    bad = 0

    for t in targets:
        try:
            sent = await bot.copy_message(
                chat_id=int(t),
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )

            reply_map[str(sent.message_id)] = uid
            ok += 1
        except Exception:
            bad += 1

    save_json(REPLY_MAP_FILE, reply_map)

    user_modes.pop(uid, None)
    save_json(USER_MODES_FILE, user_modes)

    if ok > 0 and bad == 0:
        await message.answer("Надіслано", reply_markup=main_menu())
    elif ok > 0 and bad > 0:
        await message.answer(
            f"Надіслано: {ok}\nНе вдалося: {bad}",
            reply_markup=main_menu()
        )
    else:
        await message.answer(
            "❌ Не вдалося надіслати повідомлення",
            reply_markup=main_menu()
        )

@dp.inline_query()
async def inline(query: types.InlineQuery):
    ensure_user(query.from_user.id)

    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={query.from_user.id}"

    item = InlineQueryResultArticle(
        id="share",
        title="Анонімне посилання",
        input_message_content=InputTextMessageContent(
            message_text=f"Напиши мені анонімно\n{link}"
        )
    )

    await query.answer([item], cache_time=1)

async def main():
    print("Bot started")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
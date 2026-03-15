import asyncio
import json
import os
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent, LabeledPrice
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
LINK_TO_BANK = os.getenv("LINK_TO_BANK")
OWNER_IDS_RAW = os.getenv("OWNER_IDS") or os.getenv("OWNER_ID", "")
ANTI_SPAM_SECONDS = int(os.getenv("ANTI_SPAM_SECONDS", "30"))

OWNER_IDS = [int(x) for x in OWNER_IDS_RAW.split(",") if x.strip().isdigit()]

USERS_FILE = "users.json"
USER_MODES_FILE = "user_modes.json"
REPLY_MAP_FILE = "reply_map.json"
PAYMENTS_FILE = "payments.json"

STAR_PACKS = [50, 100, 250, 500]

bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
)

dp = Dispatcher()

users = {}
user_modes = {}
reply_map = {}

UKRAINE_TZ = ZoneInfo("Europe/Kyiv")

last_send = {}

# ---------- JSON ----------

def load_json(file, default):
    if not os.path.exists(file):
        return default
    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default


def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


users = load_json(USERS_FILE, {})
user_modes = load_json(USER_MODES_FILE, {})
reply_map = load_json(REPLY_MAP_FILE, {})

# ---------- UTILS ----------

def ensure_user(uid):
    if str(uid) not in users:
        users[str(uid)] = {}
        save_json(USERS_FILE, users)


def is_owner(uid):
    return uid in OWNER_IDS


def is_russian(text):
    if not text:
        return False
    return bool(re.search(r"[ыЫэЭъЪёЁ]", text))


def anti_spam(uid):
    now = time.time()
    last = last_send.get(uid, 0)

    if now - last < ANTI_SPAM_SECONDS:
        return False

    last_send[uid] = now
    return True


# ---------- UI ----------

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


# ---------- START ----------

@dp.message(Command("start"))
async def start(message: types.Message, command: CommandObject):

    ensure_user(message.from_user.id)

    if command.args:

        targets = command.args.split(",")

        user_modes[str(message.from_user.id)] = targets
        save_json(USER_MODES_FILE, user_modes)

        await message.answer(
            "🤫 Режим анонімки активовано\n"
            "Напиши повідомлення",
        )

    else:

        await message.answer(
            "Привіт 👋",
            reply_markup=main_menu()
        )


# ---------- LINK ----------

@dp.message(F.text == "🔗 Моє посилання")
async def my_link(message: types.Message):

    bot_info = await bot.get_me()

    link = f"https://t.me/{bot_info.username}?start={message.from_user.id}"

    await message.answer(
        f"Твоє посилання:\n\n`{link}`",
        reply_markup=main_menu()
    )


# ---------- HELP ----------

@dp.message(F.text == "❓ Як це працює")
async def help_cmd(message: types.Message):

    await message.answer(
        "Люди пишуть тобі анонімно через посилання."
    )


# ---------- DONATE MONO ----------

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


# ---------- STARS ----------

@dp.message(F.text == "⭐ Підтримати в зірках")
async def stars(message: types.Message):

    await message.answer(
        "Обери суму ⭐",
        reply_markup=stars_menu()
    )


@dp.callback_query(F.data.startswith("stars"))
async def stars_pay(callback: types.CallbackQuery):

    amount = int(callback.data.split(":")[1])

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

    payments.append({
        "user": message.from_user.id,
        "amount": message.successful_payment.total_amount,
        "date": datetime.now(UKRAINE_TZ).strftime("%Y-%m-%d %H:%M:%S")
    })

    save_json(PAYMENTS_FILE, payments)

    await message.answer("⭐ Дякуємо за підтримку!")


# ---------- STATS ----------

@dp.message(Command("stats"))
async def stats(message: types.Message):

    if not is_owner(message.from_user.id):
        return

    payments = load_json(PAYMENTS_FILE, [])

    stars = sum(p["amount"] for p in payments)

    await message.answer(
        f"📊 Статистика\n\n"
        f"👥 Користувачів: {len(users)}\n"
        f"⭐ Донатів: {stars}"
    )


# ---------- PAYMENTS ----------

@dp.message(Command("payments"))
async def payments(message: types.Message):

    if not is_owner(message.from_user.id):
        return

    payments = load_json(PAYMENTS_FILE, [])

    if not payments:
        await message.answer("Донатів немає")
        return

    text = "💸 Останні донати\n\n"

    for p in payments[-10:]:
        text += f"⭐ {p['amount']} — {p['date']}\n"

    await message.answer(text)


# ---------- BROADCAST ----------

@dp.message(Command("broadcast"))
async def broadcast(message: types.Message, command: CommandObject):

    if not is_owner(message.from_user.id):
        return

    text = command.args

    if not text:
        await message.answer("Напиши текст")
        return

    ok = 0
    bad = 0

    for uid in users:

        try:
            await bot.send_message(uid, text)
            ok += 1
        except:
            bad += 1

    await message.answer(
        f"Розсилка завершена\n\n"
        f"OK: {ok}\n"
        f"BAD: {bad}"
    )


# ---------- ANON ----------

@dp.message(
    F.text | F.photo | F.voice | F.video_note | F.animation | F.sticker
)
async def anon(message: types.Message):

    uid = str(message.from_user.id)

    ensure_user(message.from_user.id)

    if message.reply_to_message:

        mid = str(message.reply_to_message.message_id)

        if mid in reply_map:

            target = reply_map[mid]

            await bot.copy_message(
                chat_id=target,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )

            await message.reply("Відправлено")

            return

    if uid not in user_modes:
        return

    if not anti_spam(message.from_user.id):
        await message.reply("Зачекай трохи")
        return

    targets = user_modes[uid]

    for t in targets:

        try:

            sent = await bot.copy_message(
                chat_id=int(t),
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )

            reply_map[str(sent.message_id)] = uid

        except:
            pass

    save_json(REPLY_MAP_FILE, reply_map)

    user_modes.pop(uid)
    save_json(USER_MODES_FILE, user_modes)

    await message.answer(
        "Надіслано",
        reply_markup=main_menu()
    )


# ---------- INLINE ----------

@dp.inline_query()
async def inline(query: types.InlineQuery):

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


# ---------- MAIN ----------

async def main():

    print("Bot started")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
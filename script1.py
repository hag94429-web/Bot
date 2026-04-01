import asyncio
import os
import re
import time
import random
import string

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.filters.command import CommandObject, CommandStart
from aiogram.types import (
    InlineQueryResultArticle,
    InputTextMessageContent,
    LabeledPrice,
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

from db import (
    init_db,
    ensure_user,
    get_users_count,
    get_all_user_ids,
    delete_users,
    set_user_mode,
    get_user_mode,
    delete_user_mode,
    set_reply_target,
    get_reply_target,
    create_team,
    team_exists,
    get_team_targets,
    get_all_teams,
    get_teams_count,
    add_payment,
    get_last_payments,
    get_total_stars,
    increment_received_count,
    get_top_users,
)

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
LINK_TO_BANK = os.getenv("LINK_TO_BANK")
OWNER_IDS_RAW = os.getenv("OWNER_IDS") or os.getenv("OWNER_ID", "")
ANTI_SPAM_SECONDS = int(os.getenv("ANTI_SPAM_SECONDS", "30"))

if not API_TOKEN:
    raise ValueError("Не знайдено API_TOKEN у .env")

if not LINK_TO_BANK:
    raise ValueError("Не знайдено LINK_TO_BANK у .env")

OWNER_IDS = [int(x.strip()) for x in OWNER_IDS_RAW.split(",") if x.strip().isdigit()]
if not OWNER_IDS:
    raise ValueError("Не знайдено OWNER_IDS або OWNER_ID у .env")

STAR_PACKS = [50, 100, 250, 500]
QUESTIONS = [
    "Хто тобі подобається?",
    "Що ти про мене думаєш?",
    "Хто тебе бісить?",
    "З ким хочеш спілкуватись?",
    "Яка твоя думка про мене?",
    "Напиши мені щось приємне 🙂",
]

bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
)
dp = Dispatcher()

last_send = {}
banned_users = set()  # тут зберігатимемо забанених користувачів у пам’яті


# ================== ФУНКЦІЇ ==================
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

    if team_exists(arg):
        targets = normalize_targets(get_team_targets(arg))
    else:
        raw_targets = re.split(r"[,\s]+", arg)
        targets = normalize_targets(raw_targets)

    targets = [t for t in targets if t != current_user_id]
    return targets


def generate_team_key():
    while True:
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
        key = f"team_{suffix}"
        if not team_exists(key):
            return key


def clean_bad_users(bad_ids):
    bad_ids = [int(x) for x in bad_ids if str(x).isdigit()]
    return delete_users(bad_ids)


def main_menu():
    kb = ReplyKeyboardBuilder()
    kb.row(types.KeyboardButton(text="🔗 Моє посилання"))
    kb.row(types.KeyboardButton(text="📢 Поділитися"))
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


def ban_user(uid: int):
    banned_users.add(uid)
    delete_user_mode(uid)  # видаляємо режим анонімки якщо є
    return True


def unban_user(uid: int):
    banned_users.discard(uid)
    return True


def is_banned(uid: int):
    return uid in banned_users


# ================== КОМАНДИ ==================
@dp.message(CommandStart())
async def start(message: types.Message, command: CommandObject):
    if is_banned(message.from_user.id):
        await message.answer("❌ Ти забанений і не можеш користуватись ботом.")
        return

    ensure_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name
    )

    if command.args:
        targets = parse_targets(command.args, message.from_user.id)

        if not targets:
            await message.answer("❌ Невірне посилання або немає коректних ID.")
            return

        set_user_mode(message.from_user.id, targets)

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
        await message.answer("Привіт 👋", reply_markup=main_menu())


@dp.message(Command("ban"))
async def cmd_ban(message: types.Message, command: CommandObject):
    if not is_owner(message.from_user.id):
        await message.answer("❌ Тільки власник може банити користувачів")
        return

    raw_ids = (command.args or "").strip()
    if not raw_ids:
        await message.answer("❌ Вкажи ID користувачів через пробіл або кому")
        return

    user_ids = [x.strip() for x in re.split(r"[,\s]+", raw_ids) if x.strip().isdigit()]
    if not user_ids:
        await message.answer("❌ Немає правильних ID")
        return

    for uid in user_ids:
        ban_user(int(uid))

    await message.answer(f"✅ Заблоковано {len(user_ids)} користувачів:\n" + ", ".join(user_ids))


@dp.message(Command("unban"))
async def cmd_unban(message: types.Message, command: CommandObject):
    if not is_owner(message.from_user.id):
        await message.answer("❌ Тільки власник може розбанювати користувачів")
        return

    raw_ids = (command.args or "").strip()
    if not raw_ids:
        await message.answer("❌ Вкажи ID користувачів через пробіл або кому")
        return

    user_ids = [x.strip() for x in re.split(r"[,\s]+", raw_ids) if x.strip().isdigit()]
    if not user_ids:
        await message.answer("❌ Немає правильних ID")
        return

    for uid in user_ids:
        unban_user(int(uid))

    await message.answer(f"✅ Розблоковано {len(user_ids)} користувачів:\n" + ", ".join(user_ids))


# ================== АНІМОВАНІ ПОВІДОМЛЕННЯ ==================
@dp.message(F.text | F.photo | F.voice | F.video_note | F.animation | F.sticker)
async def anon(message: types.Message):
    uid = message.from_user.id

    if is_banned(uid):
        await message.answer("❌ Ти забанений і не можеш користуватись ботом.")
        return

    ensure_user(
        uid,
        message.from_user.username,
        message.from_user.first_name
    )

    text_content = message.text or message.caption

    targets = get_user_mode(uid)
    if not targets:
        return

    if is_russian(text_content):
        await message.reply("Тільки українською 🇺🇦")
        return

    if not anti_spam(uid):
        await message.reply(f"Зачекай {get_wait_seconds(uid)} сек.")
        return

    ok = 0
    bad = 0

    for t in targets:
        try:
            number = increment_received_count(int(t))
            prefix = f"📩 Нова анонімка #{number}"

            if message.text:
                sent = await bot.send_message(
                    chat_id=int(t),
                    text=f"{prefix}\n\n{message.text}"
                )
                set_reply_target(sent.message_id, uid)
            else:
                header = await bot.send_message(
                    chat_id=int(t),
                    text=prefix
                )

                sent = await bot.copy_message(
                    chat_id=int(t),
                    from_chat_id=message.chat.id,
                    message_id=message.message_id
                )

                set_reply_target(header.message_id, uid)
                set_reply_target(sent.message_id, uid)

            ok += 1
        except Exception:
            bad += 1

    delete_user_mode(uid)

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


# ================== INLINE ==================
@dp.inline_query()
async def inline(query: types.InlineQuery):
    ensure_user(
        query.from_user.id,
        query.from_user.username,
        query.from_user.first_name
    )

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


# ================== ГОЛОВНА ==================
async def main():
    init_db()
    print("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
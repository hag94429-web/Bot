import asyncio
import json
import os
import re

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
LINK_TO_BANK = os.getenv("LINK_TO_BANK")
OWNER_IDS_RAW = os.getenv("OWNER_IDS") or os.getenv("OWNER_ID", "")

if not API_TOKEN:
    raise ValueError("Не знайдено API_TOKEN у .env")

if not LINK_TO_BANK:
    raise ValueError("Не знайдено LINK_TO_BANK у .env")

OWNER_IDS = []
for part in OWNER_IDS_RAW.split(","):
    part = part.strip()
    if part.isdigit():
        OWNER_IDS.append(int(part))

if not OWNER_IDS:
    raise ValueError("Не знайдено OWNER_IDS або OWNER_ID у .env")

USER_MODES_FILE = "user_modes.json"
REPLY_MAP_FILE = "reply_map.json"
USERS_FILE = "users.json"

bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
)
dp = Dispatcher()


def load_json(filename: str, default):
    if not os.path.exists(filename):
        return default
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if data is not None else default
    except (json.JSONDecodeError, OSError):
        return default


def save_json(filename: str, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def ensure_user_exists(user_id: int):
    users = load_json(USERS_FILE, {})

    if not isinstance(users, dict):
        users = {}

    user_id = str(user_id)

    if user_id not in users:
        users[user_id] = {}
        save_json(USERS_FILE, users)


user_modes = load_json(USER_MODES_FILE, {})
reply_map = load_json(REPLY_MAP_FILE, {})

if not isinstance(user_modes, dict):
    user_modes = {}

if not isinstance(reply_map, dict):
    reply_map = {}


def is_russian(text: str) -> bool:
    if not text:
        return False
    return bool(re.search(r"[ыЫэЭъЪёЁ]", text))


def get_main_menu():
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="🔗 Моє посилання"))
    builder.row(types.KeyboardButton(text="☕️ Підтримати бота"))
    builder.row(types.KeyboardButton(text="❓ Як це працює"))
    return builder.as_markup(resize_keyboard=True)


@dp.message(Command("start"))
async def cmd_start(message: types.Message, command: CommandObject):
    user_id = str(message.from_user.id)

    ensure_user_exists(message.from_user.id)

    if command.args:
        target_id = command.args.strip()

        if not target_id.isdigit():
            await message.answer("❌ Невірне посилання.")
            return

        if target_id == user_id:
            await message.answer("❌ Не можна надіслати анонімку самому собі.")
            return

        user_modes[user_id] = target_id
        save_json(USER_MODES_FILE, user_modes)

        await message.answer(
            "🤫 Режим анонімки активовано!\n"
            "Напиши текст або надішли фото українською 🇺🇦"
        )
    else:
        await message.answer(
            "Привіт! Тисни на кнопки нижче 👇",
            reply_markup=get_main_menu()
        )


@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    if message.from_user.id not in OWNER_IDS:
        return

    users = load_json(USERS_FILE, {})

    if not isinstance(users, dict):
        users = {}

    users_count = len(users)

    await message.answer(
        f"📊 Статистика бота\n"
        f"👥 Користувачів: {users_count}"
    )


@dp.message(F.text == "🔗 Моє посилання")
async def send_link(message: types.Message):
    ensure_user_exists(message.from_user.id)

    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={message.from_user.id}"

    await message.answer(
        f"Твоє особисте посилання для анонімних повідомлень:\n\n`{link}`",
        reply_markup=get_main_menu()
    )


@dp.message(F.text == "☕️ Підтримати бота")
async def donate_info(message: types.Message):
    ensure_user_exists(message.from_user.id)

    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="Відкрити Банку 🏦", url=LINK_TO_BANK))

    await message.answer(
        "Дякуємо за підтримку проєкту! 🙏",
        reply_markup=builder.as_markup()
    )


@dp.message(F.text == "❓ Як це працює")
async def help_info(message: types.Message):
    ensure_user_exists(message.from_user.id)

    await message.answer(
        "Люди пишуть тобі анонімно через твоє посилання.\n"
        "Ти отримуєш повідомлення від бота і можеш відповісти на нього через Reply."
    )


@dp.inline_query()
async def inline_handler(inline_query: types.InlineQuery):
    ensure_user_exists(inline_query.from_user.id)

    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={inline_query.from_user.id}"

    item = InlineQueryResultArticle(
        id="share_link",
        title="Поділитися посиланням 🤫",
        description="Надішли друзям, щоб вони писали тобі анонімно",
        input_message_content=InputTextMessageContent(
            message_text=f"Напиши мені анонімно за цим посиланням: {link}"
        )
    )

    await inline_query.answer([item], cache_time=1)


@dp.message(F.text | F.photo)
async def handle_anonymous_content(message: types.Message):
    ensure_user_exists(message.from_user.id)

    user_id = str(message.from_user.id)
    text_content = message.caption if message.photo else message.text

    if message.reply_to_message:
        replied_message_id = str(message.reply_to_message.message_id)

        if replied_message_id in reply_map:
            if is_russian(text_content):
                await message.reply("Пишіть українською! 🇺🇦")
                return

            target_to_reply = int(reply_map[replied_message_id])

            try:
                if message.photo:
                    await bot.send_photo(
                        chat_id=target_to_reply,
                        photo=message.photo[-1].file_id,
                        caption=f"👤 *Автор відповів фотографією*\n\n{message.caption or ''}"
                    )
                else:
                    await bot.send_message(
                        chat_id=target_to_reply,
                        text=f"👤 *Автор відповів:*\n\n{message.text}"
                    )

                await message.reply("✅ Відповідь надіслана!")
            except Exception:
                await message.reply("❌ Не вдалося доставити відповідь.")
            return

    if user_id in user_modes:
        if is_russian(text_content):
            await message.reply("Тільки солов’їною! 🇺🇦")
            return

        target_id = int(user_modes[user_id])

        try:
            header = "📩 *Нова анонімка:*"

            if message.photo:
                sent_msg = await bot.send_photo(
                    chat_id=target_id,
                    photo=message.photo[-1].file_id,
                    caption=f"{header}\n\n{message.caption or ''}\n\n_Відповідай на це фото_"
                )
            else:
                sent_msg = await bot.send_message(
                    chat_id=target_id,
                    text=f"{header}\n\n{message.text}\n\n_Відповідай на це повідомлення_"
                )

            reply_map[str(sent_msg.message_id)] = user_id
            save_json(REPLY_MAP_FILE, reply_map)

            user_modes.pop(user_id, None)
            save_json(USER_MODES_FILE, user_modes)

            await message.answer("✅ Надіслано!", reply_markup=get_main_menu())

        except Exception:
            await message.answer("❌ Користувач заблокував бота або сталася помилка.")
    else:
        await message.answer(
            "Використовуй меню або своє посилання 👇",
            reply_markup=get_main_menu()
        )


async def main():
    print("Бот запущений!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
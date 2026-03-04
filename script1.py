import asyncio
import re
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.types import InlineQueryResultArticle, InputTextMessageContent

# --- НАЛАШТУВАННЯ (ОБОВ'ЯЗКОВО ЗАПОВНИ) ---
API_TOKEN = '8647337935:AAH6H4ox15OiQIuQoT5orL5yKrNL93C7XVw'  # Встав свій токен від @BotFather
LINK_TO_BANK = 'https://send.monobank.ua/jar/3ZBbXCCrnf'  # Посилання на твою Банку

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Сховища (у пам'яті)
user_modes = {}
reply_map = {}


# Функція перевірки мови (фільтр російських літер)
def is_russian(text: str):
    if not text: return False
    return bool(re.search(r'[ыЫэЭъЪёЁ]', text))


# Головне меню з кнопками
def get_main_menu():
    builder = ReplyKeyboardBuilder()
    builder.row(types.KeyboardButton(text="🔗 Моє посилання"))
    builder.row(types.KeyboardButton(text="☕️ Підтримати бота"))
    builder.row(types.KeyboardButton(text="❓ Як це працює"))
    return builder.as_markup(resize_keyboard=True)


# --- ОБРОБКА КОМАНД ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, command: CommandObject):
    if command.args:  # Якщо перейшли за посиланням
        user_modes[message.from_user.id] = command.args
        await message.answer("🤫 Режим анонімки активовано! Напиши текст або надішли фото (тільки солов'їною 🇺🇦)")
    else:
        await message.answer("Привіт! Тисни на кнопки нижче 👇", reply_markup=get_main_menu())


@dp.message(F.text == "🔗 Моє посилання")
async def send_link(message: types.Message):
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={message.from_user.id}"
    await message.answer(f"Твоє особисте посилання для анонімних повідомлень:\n\n`{link}`", parse_mode="Markdown")


@dp.message(F.text == "☕️ Підтримати бота")
async def donate_info(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="Відкрити Банку 🏦", url=LINK_TO_BANK))
    await message.answer("Дякуємо за підтримку проекту! 🙏", reply_markup=builder.as_markup())


@dp.message(F.text == "❓ Як це працює")
async def help_info(message: types.Message):
    await message.answer(
        "Люди пишуть тобі анонімно через твоє посилання. Ти отримуєш повідомлення від бота і можеш відповісти на нього (через Reply).")


# --- INLINE РЕЖИМ (ЧЕРЕЗ СОБАЧКУ) ---

@dp.inline_query()
async def inline_handler(inline_query: types.InlineQuery):
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


# --- ГОЛОВНИЙ ОБРОБНИК: ТЕКСТ ТА ФОТО ---

@dp.message(F.text | F.photo)
async def handle_anonymous_content(message: types.Message):
    user_id = message.from_user.id
    caption = message.caption if message.photo else message.text

    # 1. Якщо це відповідь (Reply) на повідомлення аноніма
    if message.reply_to_message and message.reply_to_message.message_id in reply_map:
        if is_russian(caption):
            await message.reply("Пишіть українською! 🇺🇦")
            return

        target_to_reply = reply_map[message.reply_to_message.message_id]
        try:
            if message.photo:
                await bot.send_photo(target_to_reply, message.photo[-1].file_id, caption="👤 Автор відповів фотографією")
            else:
                await bot.send_message(target_to_reply, f"👤 **Автор відповів:**\n\n{message.text}")
            await message.reply("✅ Відповідь надіслана!")
        except Exception:
            await message.reply("❌ Не вдалося доставити.")
        return

    # 2. Якщо це нова анонімка комусь
    if user_id in user_modes:
        if is_russian(caption):
            await message.reply("Тільки солов'їною! 🇺🇦")
            return

        target_id = user_modes[user_id]
        try:
            header = "📩 **Нова анонімка:**"
            if message.photo:
                sent_msg = await bot.send_photo(
                    target_id,
                    message.photo[-1].file_id,
                    caption=f"{header}\n\n{message.caption or ''}\n\n_(Відповідай на це фото)_"
                )
            else:
                sent_msg = await bot.send_message(
                    target_id,
                    f"{header}\n\n{message.text}\n\n_(Відповідай на це повідомлення)_"
                )

            reply_map[sent_msg.message_id] = user_id
            await message.answer("✅ Надіслано!", reply_markup=get_main_menu())
            del user_modes[user_id]
        except Exception:
            await message.answer("❌ Користувач заблокував бота.")
    else:
        if not message.reply_to_message:
            await message.answer("Використовуй меню або посилання 👇", reply_markup=get_main_menu())


async def main():
    print("Бот запущений! Перевірте токен у коді.")
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())
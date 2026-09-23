import asyncio
import logging
import random
import os

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

from telethon import TelegramClient, events
from telethon.sessions import StringSession

# ----------------- SOZLAMALAR -----------------
BOT_TOKEN = "8751865013:AAHqEWU3ygRg5mA4Wd1gYNaQEZB0UFaMRUw"  # BotFather'dan olingan token
API_ID = 34760616  # my.telegram.org saytidan olingan API ID (integer)
API_HASH = "1bea40adc634f0205e907f0a1873e7b8"  # my.telegram.org saytidan olingan API HASH
ADMIN_ID = 7651404790  # Sizning Telegram ID'ingiz (integer)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Ma'lumotlarni saqlash
phrases = []          # Boshida gaplar bo'lmaydi
active_clients = {}   # Ulangan userbotlar: {user_id: TelegramClient}

# FSM (Holatlar)
class AccountConnect(StatesGroup):
    waiting_for_session = State()

class AdminStates(StatesGroup):
    waiting_for_phrase = State()

# ----------------- TUGMALAR -----------------
def get_user_keyboard():
    kb = [
        [KeyboardButton(text="📱 Akkauntni ulash")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_admin_keyboard():
    kb = [
        [InlineKeyboardButton(text="📊 Statistika", callback_data="stats")],
        [InlineKeyboardButton(text="➕ Gap qo'shish", callback_data="add_phrase")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# ----------------- COMMAND HANDLERS -----------------
@dp.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "👋 **Xush kelibsiz!**\n\nAkkauntingizni botga ulash uchun pastdagi tugmani bosing:",
        reply_markup=get_user_keyboard(),
        parse_mode="Markdown"
    )

@dp.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("👑 **Admin Panel:**", reply_markup=get_admin_keyboard(), parse_mode="Markdown")

# ----------------- ADMIN PANEL -----------------
@dp.callback_query(F.data == "stats")
async def show_stats(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return
    
    msg = (
        f"📊 **BOT STATISTIKASI**\n\n"
        f"👑 **Admin ID:** `{ADMIN_ID}`\n"
        f"📱 **Ulangan akkauntlar:** `{len(active_clients)}` ta\n"
        f"💬 **Bazadagi gaplar:** `{len(phrases)}` ta\n"
        f"⚙️ **Status:** 🟢 Faol"
    )
    await call.message.edit_text(msg, reply_markup=get_admin_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data == "add_phrase")
async def add_phrase_start(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await state.set_state(AdminStates.waiting_for_phrase)
    await call.message.answer("➕ **Yangi gapni yoki premium emojili matnni yuboring:**")

@dp.message(AdminStates.waiting_for_phrase)
async def save_phrase(message: types.Message, state: FSMContext):
    phrase_text = message.text or message.caption or ""
    if phrase_text:
        phrases.append(phrase_text)
        await state.clear()
        await message.answer(
            f"✅ **Gap muvaffaqiyatli saqlandi!**\n\nJami gaplar: `{len(phrases)}` ta.",
            reply_markup=get_admin_keyboard(),
            parse_mode="Markdown"
        )
    else:
        await message.answer("❌ Matn kiritilmadi. Qaytadan yuboring:")

# ----------------- AKKAUNT ULASH (STRING SESSION) -----------------
@dp.message(F.text == "📱 Akkauntni ulash")
async def start_connect(message: types.Message, state: FSMContext):
    await state.set_state(AccountConnect.waiting_for_session)
    await message.answer(
        "📲 **Akkauntingizning Telethon String Session kodini yuboring:**\n\n"
        "💡 *String Session kodi Telegram tomonidan bloklanmaydi va parolsiz xavfsiz ulanadi.*",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )

@dp.message(AccountConnect.waiting_for_session)
async def process_session(message: types.Message, state: FSMContext):
    session_str = message.text.strip()
    
    try:
        # StringSession orqali klientni yaratish va ulash
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await client.connect()
        
        if not await client.is_user_authorized():
            await message.answer("❌ Kiritilgan String Session kodi noto'g'ri yoki yaroqsiz! Qayta kiriting:")
            await client.disconnect()
            return

        # Userbot uchun hodisalarni ulash
        setup_userbot_events(client)
        active_clients[message.from_user.id] = client

        await state.clear()
        await message.answer(
            "✅ **Akkauntingiz muvaffaqiyatli ulandi!**\n\n"
            "Endi ushbu akkaunt guruhlarda avtomatik ravishda xabarlarga va **utag** (mention/reply) qilinganda javob qaytaradi.",
            reply_markup=get_user_keyboard(),
            parse_mode="Markdown"
        )

    except Exception as e:
        await message.answer(f"❌ Ulanishda xatolik yuz berdi: `{e}`\n\nQayta urinib ko'ring yoki /start bosing.", parse_mode="Markdown")

# ----------------- USERBOT HODISALARI (GURUH VA UTAG) -----------------
def setup_userbot_events(client: TelegramClient):
    @client.on(events.NewMessage(chats=None))
    async def userbot_handler(event):
        # Faqat guruhlarda ishlashi uchun
        if not (event.is_group or event.is_channel):
            return

        # Utag (mention yoki reply) qilinganini aniqlash
        is_mentioned = event.mentioned or (event.reply_to_msg_id and event.is_private is False)
        
        if phrases:
            random_phrase = random.choice(phrases)
            
            # Agar akkauntga utag berilsa
            if is_mentioned:
                await event.reply(random_phrase)
            else:
                # Oddiy guruh xabarlariga 15% ehtimollik bilan javob qaytaradi
                if random.random() < 0.15:
                    await event.respond(random_phrase)

# ----------------- MAIN -----------------
async def main():
    logging.basicConfig(level=logging.INFO)
    print("Bot ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

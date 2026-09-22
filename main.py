import os
import asyncio
import random
import sqlite3
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from pyrogram import Client

logging.basicConfig(level=logging.INFO)

# Telegram API ma'lumotlari
API_ID = int(os.environ.get("API_ID", "34760616"))
API_HASH = os.environ.get("API_HASH", "1bea40adc634f0205e907f0a1873e7b8")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

# Baza bilan ishlash
conn = sqlite3.connect("utag_data.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    session_string TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tagged_count INTEGER DEFAULT 0
)
""")
conn.commit()

# Baza bo'sh bo'lsa standart matnlar
cursor.execute("SELECT COUNT(*) FROM messages")
if cursor.fetchone()[0] == 0:
    cursor.execute("INSERT INTO messages (text) VALUES ('oyinga keling 🎮')")
    cursor.execute("INSERT INTO messages (text) VALUES ('assalomu alaykum 👋')")
    cursor.execute("INSERT INTO stats (tagged_count) VALUES (0)")
    conn.commit()

# Conversation holatlari
PHONE, CODE, PASSWORD = range(3)
user_data_store = {}
user_clients = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if ADMIN_ID != 0 and user_id != ADMIN_ID:
        await update.message.reply_text("Sizga bu botdan foydalanishga ruxsat berilmagan.")
        return

    keyboard = [
        [InlineKeyboardButton("📱 Akkauntni Ulash", callback_data="connect_acc")],
        [InlineKeyboardButton("📊 Admin Panel", callback_data="admin_panel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Salom! U-Tag Botiga xush kelibsiz.\n\nAkkauntingizni ulash uchun tugmani bosing:",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "connect_acc":
        await query.message.reply_text("Iltimos, Telegram raqamingizni kiriting (Masalan: +998901234567):")
        return PHONE
    elif query.data == "admin_panel":
        cursor.execute("SELECT tagged_count FROM stats WHERE id = 1")
        count = cursor.fetchone()[0]
        cursor.execute("SELECT text FROM messages")
        texts = cursor.fetchall()
        text_list = "\n".join([f"- {t[0]}" for t in texts])

        panel_text = (
            f"📊 **Admin Panel**\n\n"
            f"👤 Jami chaqirilganlar: **{count}** ta\n\n"
            f"📝 **Iboralar:**\n{text_list}\n\n"
            f"➕ Yangi ibora qo'shish: `/add matn` deb yozing."
        )
        await query.message.reply_text(panel_text, parse_mode="Markdown")

async def get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    user_id = update.effective_user.id

    client = Client(f"session_{user_id}", api_id=API_ID, api_hash=API_HASH, in_memory=True)
    await client.connect()

    try:
        code_info = await client.send_code(phone)
        user_data_store[user_id] = {
            "client": client,
            "phone": phone,
            "phone_code_hash": code_info.phone_code_hash
        }
        await update.message.reply_text(" Telegram'ingizga kelgan tasdiqlash kodini kiriting:")
        return CODE
    except Exception as e:
        await update.message.reply_text(f"❌ Xatolik yuz berdi: {e}\n\nQaytadan /start bosing.")
        await client.disconnect()
        return ConversationHandler.END

async def get_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    user_id = update.effective_user.id
    data = user_data_store.get(user_id)

    if not data:
        await update.message.reply_text("Sessiya topilmadi. Qaytadan /start bosing.")
        return ConversationHandler.END

    client = data["client"]

    try:
        await client.sign_in(data["phone"], data["phone_code_hash"], code)
        session_str = await client.export_session_string()

        cursor.execute("INSERT OR REPLACE INTO users (user_id, session_string) VALUES (?, ?)", (user_id, session_str))
        conn.commit()

        await update.message.reply_text(" Akkaunt muvaffaqiyatli ulandi!\n\nEndi ixtiyoriy guruhga kirib `.az` deb yozsangiz, bot sizning nomingizdan odamlarni chaqirishni boshlaydi. To'xtatish uchun `.as` deb yozasiz.")
        await start_userbot(user_id, session_str)
        return ConversationHandler.END

    except Exception as e:
        if "TWO_STEPS" in str(e) or "PASSWORD" in str(e):
            await update.message.reply_text("🔑 2-Bosqichli parolingizni (Two-Step Verification) kiriting:")
            return PASSWORD
        else:
            await update.message.reply_text(f"❌ Kod noto'g'ri yoki xatolik: {e}")
            return ConversationHandler.END

async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    user_id = update.effective_user.id
    data = user_data_store.get(user_id)

    client = data["client"]

    try:
        await client.check_password(password)
        session_str = await client.export_session_string()

        cursor.execute("INSERT OR REPLACE INTO users (user_id, session_string) VALUES (?, ?)", (user_id, session_str))
        conn.commit()

        await update.message.reply_text("✅ Akkaunt muvaffaqiyatli ulandi!\n\nGuruhda `.az` va `.as` ishlatishingiz mumkin.")
        await start_userbot(user_id, session_str)
        return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(f"❌ Parol noto'g'ri: {e}")
        return ConversationHandler.END

async def add_phrase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        new_text = " ".join(context.args)
        cursor.execute("INSERT INTO messages (text) VALUES (?)", (new_text,))
        conn.commit()
        await update.message.reply_text(f"✅ Qo'shildi: `{new_text}`", parse_mode="Markdown")
    else:
        await update.message.reply_text("⚠️ Misol: `/add oyinga keling 🎮`")

# Userbot mantig'i (Odamlarni sizning nomingizdan tag qilish)
async def start_userbot(user_id, session_str):
    ub = Client(f"ub_{user_id}", api_id=API_ID, api_hash=API_HASH, session_string=session_str)
    
    is_tagging = {}

    @ub.on_message(filters.me & filters.command("az", prefixes="."))
    async def run_az(client, message):
        chat_id = message.chat.id
        if is_tagging.get(chat_id, False):
            return
        
        is_tagging[chat_id] = True
        await message.delete()

        cursor.execute("SELECT text FROM messages")
        custom_texts = [row[0] for row in cursor.fetchall()]

        async for member in client.get_chat_members(chat_id):
            if not is_tagging.get(chat_id, False):
                break

            if member.user.is_bot or member.user.is_self:
                continue

            status = str(member.user.status)
            if "RECENTLY" not in status and "ONLINE" not in status and "WEEKLY" not in status:
                continue

            random_text = random.choice(custom_texts)
            if member.user.username:
                tag_text = f"@{member.user.username} {random_text}"
            else:
                first_name = member.user.first_name or "Do'stim"
                tag_text = f"[{first_name}](tg://user?id={member.user.id}) {random_text}"

            try:
                await client.send_message(chat_id, tag_text)
                cursor.execute("UPDATE stats SET tagged_count = tagged_count + 1 WHERE id = 1")
                conn.commit()
                await asyncio.sleep(random.uniform(1.8, 3.0))
            except Exception:
                await asyncio.sleep(4)

        is_tagging[chat_id] = False

    @ub.on_message(filters.me & filters.command("as", prefixes="."))
    async def stop_az(client, message):
        chat_id = message.chat.id
        is_tagging[chat_id] = False
        await message.edit_text("🛑 U-tag to'xtatildi!")
        await asyncio.sleep(2)
        await message.delete()

    await ub.start()
    user_clients[user_id] = ub

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_handler, pattern="^connect_acc$")],
        states={
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_phone)],
            CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_code)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_password)],
        },
        fallbacks=[]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_phrase))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(conv_handler)

    print("Bot ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sqlite3
import logging
from datetime import date
from dotenv import load_dotenv
import httpx
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from telegram.constants import ChatAction

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SERVICE_API_KEY = os.getenv("SERVICE_API_KEY", "")
SERVICE_ENDPOINT = os.getenv("SERVICE_ENDPOINT", "")
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "@hemoo_hloom55")
DB_PATH = os.getenv("DB_PATH", "bot.db")

DEVELOPER_NAME = "ابراهيم القرشي"
BOT_NAME = "༺ 𒆜فتى قريش𒆜 ༻"

if not TELEGRAM_TOKEN:
    raise SystemExit("ضع TELEGRAM_BOT_TOKEN في ملف .env قبل التشغيل.")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        usage_date TEXT,
        usage_count INTEGER DEFAULT 0,
        subscribed INTEGER DEFAULT 0,
        plan TEXT
    );
    """)
    conn.commit()
    conn.close()

def get_user_row(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, username, usage_date, usage_count, subscribed, plan FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def upsert_user(user_id, username):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    today = date.today().isoformat()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, usage_date, usage_count) VALUES (?, ?, ? , ?)",
              (user_id, username or "", today, 0))
    conn.commit()
    conn.close()

def increment_usage(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    today = date.today().isoformat()
    c.execute("SELECT usage_date, usage_count FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    if not row:
        c.execute("INSERT INTO users (user_id, usage_date, usage_count) VALUES (?, ?, ?)", (user_id, today, 1))
    else:
        usage_date, usage_count = row
        if usage_date != today:
            c.execute("UPDATE users SET usage_date = ?, usage_count = ? WHERE user_id = ?", (today, 1, user_id))
        else:
            c.execute("UPDATE users SET usage_count = usage_count + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_usage(user_id):
    row = get_user_row(user_id)
    if not row:
        return 0
    _, _, usage_date, usage_count, subscribed, _ = row
    if usage_date != date.today().isoformat():
        return 0
    return usage_count or 0

def set_subscription(user_id, plan_name):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, username, usage_date, usage_count) VALUES (?, ?, ?, ?)",
              (user_id, "", date.today().isoformat(), 0))
    c.execute("UPDATE users SET subscribed = 1, plan = ? WHERE user_id = ?", (plan_name, user_id))
    conn.commit()
    conn.close()

FREE_DAILY_LIMIT = 5


PLANS = [
    {"id": "weekly", "title": "1W Standard - $5", "desc": "أسبوع واحد - وصول أكبر"},
    {"id": "monthly", "title": "1M Premium+ - $15", "desc": "شهر كامل - وصول موسّع"},
    {"id": "yearly", "title": "1Y Premium+ - $100", "desc": "سنة كاملة - وصول شامل"},
]

def make_subscribe_keyboard():
    buttons = []
    for p in PLANS:
        buttons.append([InlineKeyboardButton(f"{p['title']}", callback_data=f"plan:{p['id']}")])
    buttons.append([InlineKeyboardButton("إلغاء ❌", callback_data="plan:cancel")])
    return InlineKeyboardMarkup(buttons)

def make_main_keyboard():
    kb = [
        [InlineKeyboardButton("💳 اشترك", callback_data="open_subscribe"),
         InlineKeyboardButton("ℹ️ معلومات", callback_data="help_btn")],
    ]
    return InlineKeyboardMarkup(kb)

WELCOME_TEXT = (
    "أهلاً بك أيها الشرير 😈\n\n"
    "في عالمي 🌑، حيث تسقط القوانين ⚖️ والشروط 📜💥 وتبقى الأفكار السلبية 🙃 والسيئة 🧠💀 🕸️.\n\n"
    "أخبرني بما تريد مني أن أساعدك به 🦹‍♂️ وسأكون عند حسن ظنك 🎭 أيها الوغد 👿.\n\n"
    f"حدك اليومي المجاني: {FREE_DAILY_LIMIT} رسائل.\n"
    f"مطور البوت: {DEVELOPER_NAME} — تواصل للدفع أو الاستفسار: {OWNER_USERNAME}\n"
    f"بوت: {BOT_NAME}"
)

HELP_TEXT = (
    "أوامر:\n"
    "/start - بداية\n"
    "/help - مساعدة\n"
    "/subscribe - عرض باقات الاشتراك\n\n"
    "⚠️تنبيه⚠️: البوت يقدم محتوى تعليمياً فقط. لا يدعم أفعالاً غير قانونية"
)

async def call_service(prompt: str) -> str:
        
    
    if SERVICE_ENDPOINT and SERVICE_API_KEY:
        headers = {"Authorization": f"Bearer {SERVICE_API_KEY}", "Content-Type": "application/json"}
        payload = {"prompt": prompt}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(SERVICE_ENDPOINT, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            
            if isinstance(data, dict):
                return data.get("text") or data.get("result") or str(data)
            return str(data)

    
    return f"هاك يا مولاي 😈 — تلقيت عبارتك: «{prompt}»\n\nأجيبك بروح الظلال... \n\n— {DEVELOPER_NAME} | {OWNER_USERNAME}"

async def start_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user.id, user.username)
    await update.message.reply_text(WELCOME_TEXT, reply_markup=make_main_keyboard())

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)

async def subscribe_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("اختر باقة الاشتراك:", reply_markup=make_subscribe_keyboard())

async def callback_query_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "open_subscribe":
        await query.edit_message_text("اختر باقة تناسبك:", reply_markup=make_subscribe_keyboard())
        return

    if data == "help_btn":
        await query.edit_message_text(HELP_TEXT)
        return

    if data.startswith("plan:"):
        plan_id = data.split(":",1)[1]
        if plan_id == "cancel":
            await query.edit_message_text("تم الإلغاء ✅")
            return
        user = query.from_user
        plan = next((p for p in PLANS if p["id"] == plan_id), None)
        plan_title = plan["title"] if plan else plan_id
        owner_msg = (
            f"📩 طلب اشتراك جديد\n\n"
            f"المستخدم: {user.full_name} (@{user.username if user.username else 'no_username'})\n"
            f"معرّف: {user.id}\n"
            f"الباقة: {plan_title}\n\n"
            "الرجاء التواصل مع المستخدم لإتمام الدفع وتفعيل الاشتراك."
        )
        
        try:
            await ctx.bot.send_message(chat_id=OWNER_USERNAME, text=owner_msg)
        except Exception as e:
            logger.warning("تعذر إرسال رسالة لصاحب البوت: %s", e)
        await query.edit_message_text(
            f"تم إرسال طلب الاشتراك إلى صاحب البوت {OWNER_USERNAME}.\n"
            f"اختر وسيلة الدفع مع صاحب البوت ثم سيُفعّل اشتراكك يدويًا.\n\n"
            f"الباقة المختارة: {plan_title}"
        )
        return

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    upsert_user(user.id, user.username)
    row = get_user_row(user.id)
    subscribed = bool(row[4]) if row else False

    
    if not subscribed:
        usage = get_usage(user.id)
        if usage >= FREE_DAILY_LIMIT:
            await update.message.reply_text(
                f"انتهت حصتك المجانية لليوم ({FREE_DAILY_LIMIT} رسائل).\n"
                f"اضغط '💳 اشترك' للحصول على وصول أكبر."
            )
            return

    
    increment_usage(user.id)

    
    await update.message.chat.send_action(action=ChatAction.TYPING)

    text = update.message.text.strip()

    try:
        result = await call_service(text)
    except Exception as e:
        logger.exception("فشل استدعاء الخدمة")
        await update.message.reply_text("حدث خطأ أثناء المعالجة. حاول لاحقًا.")
        return

    footer = f"\n\n— تم بواسطة {DEVELOPER_NAME} | {OWNER_USERNAME}"
    reply = (result or "لا يوجد رد من الخدمة.") + footer

    MAX_SIZE = 4000
    for i in range(0, len(reply), MAX_SIZE):
        await update.message.reply_text(reply[i:i+MAX_SIZE])

def reset_daily_usage_job():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    today = date.today().isoformat()
    c.execute("UPDATE users SET usage_count = 0, usage_date = ? WHERE subscribed = 0", (today,))
    conn.commit()
    conn.close()
    logger.info("تمت إعادة ضبط الاستخدام اليومي للمستخدمين غير المشتركين.")

def main():
    init_db()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("subscribe", subscribe_command))
    app.add_handler(CallbackQueryHandler(callback_query_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    scheduler = AsyncIOScheduler()
    
    scheduler.add_job(reset_daily_usage_job, "cron", hour=0, minute=0)
    scheduler.start()

    logger.info("بوت يعمل الآن — بدء polling...")
    app.run_polling()

if __name__ == "__main__":
    main()



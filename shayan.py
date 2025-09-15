# requirements:
# pip install python-telegram-bot==20.7 apscheduler

import sqlite3
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

BOT_TOKEN = "PUT_YOUR_TOKEN_HERE"
REMINDER_HOUR = 20  # 24h format: ساعت یادآوری روزانه
REMINDER_MINUTE = 0

# --- DB setup ---
conn = sqlite3.connect("habits.db", check_same_thread=False)
c = conn.cursor()
c.execute("""CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    task TEXT,
    date TEXT,
    status TEXT
)""")
c.execute("""CREATE TABLE IF NOT EXISTS tasks (
    chat_id INTEGER,
    task TEXT
)""")
conn.commit()

# --- helpers ---
def add_task_db(chat_id, task):
    c.execute("INSERT INTO tasks(chat_id,task) VALUES(?,?)", (chat_id, task))
    conn.commit()

def get_tasks(chat_id):
    c.execute("SELECT task FROM tasks WHERE chat_id=?", (chat_id,))
    return [r[0] for r in c.fetchall()]

def record_report(chat_id, task, status):
    today = datetime.utcnow().date().isoformat()
    c.execute("INSERT INTO reports(chat_id,task,date,status) VALUES(?,?,?,?)",
              (chat_id, task, today, status))
    conn.commit()

def streak_for_task(chat_id, task):
    # ساده: تعداد روزهای پیاپی آخر که status='done'
    c.execute("SELECT date,status FROM reports WHERE chat_id=? AND task=? ORDER BY date DESC", (chat_id, task))
    rows = c.fetchall()
    if not rows: return 0
    streak = 0
    last = None
    from datetime import date, timedelta
    d = date.today()
    for r in rows:
        rec_date = datetime.fromisoformat(r[0]).date()
        if rec_date == d and r[1] == 'done':
            streak += 1
            d = d - timedelta(days=1)
        elif rec_date < d:
            break
        else:
            break
    return streak

# --- Telegram handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("سلام! من ربات عادت شمام. اول یک یا چند کار اضافه کن:\n/add <task>\nمثال: /add 30min_english")

async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    task = " ".join(context.args)
    if not task:
        await update.message.reply_text("فرمت: /add <task>")
        return
    add_task_db(chat_id, task)
    await update.message.reply_text(f"اضافه شد ✅\nوظیفه: {task}")

async def list_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    tasks = get_tasks(chat_id)
    if not tasks:
        await update.message.reply_text("هیچ کاری هنوز اضافه نشده. با /add شروع کن.")
        return
    msg = "کارهای تو:\n" + "\n".join(f"- {t}" for t in tasks)
    msg += "\n\nوقتی انجام دادی فقط نام کار رو ارسال کن یا بنویس: done <task>"
    await update.message.reply_text(msg)

async def done_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    # قبول دو فرمت: "done <task>" یا مستقیم اسم تسک
    if text.lower().startswith("done "):
        task = text[5:].strip()
    else:
        task = text
    tasks = get_tasks(chat_id)
    if task not in tasks:
        await update.message.reply_text("اون کار رو ندارم. اول با /add اضافه کن یا اسم دقیقی بنویس.")
        return
    record_report(chat_id, task, 'done')
    s = streak_for_task(chat_id, task)
    await update.message.reply_text(f"آفرین! اوکی ✅\nاستریک فعلی برای «{task}»: {s} روز 🔥")

async def missed_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # در صورت دریافت پیام‌های دیگه
    await update.message.reply_text("برای ثبت انجام‌شدن کار بنویس: done <task> یا فقط اسم کار.")

# --- scheduler: ارسال یادآوری روزانه ---
async def send_daily_reminder(app):
    # این تابع همه‌ی کاربران را می‌گردد و پیام می‌فرستد
    c.execute("SELECT DISTINCT chat_id FROM tasks")
    rows = c.fetchall()
    for r in rows:
        chat_id = r[0]
        tasks = get_tasks(chat_id)
        if not tasks: continue
        tasks_text = "\n".join(f"- {t}" for t in tasks)
        text = f"یادآوری روزانه⏰\nامروز این کارها رو داری:\n{tasks_text}\nوقتی انجام شد بنویس: done <task>"
        try:
            await app.bot.send_message(chat_id=chat_id, text=text)
        except Exception as e:
            print("send error", e)

def schedule_jobs(app):
    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: app.create_task(send_daily_reminder(app)),
                      'cron', hour=REMINDER_HOUR, minute=REMINDER_MINUTE)
    scheduler.start()

# --- main ---
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_task))
    app.add_handler(CommandHandler("tasks", list_tasks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, done_message))

    schedule_jobs(app)
    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

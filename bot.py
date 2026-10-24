import os
import csv
import io
import sqlite3
from datetime import datetime
from decimal import Decimal, InvalidOperation

from telegram import (
    Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup,
    InlineKeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {
    int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
}
DB_PATH = os.getenv("DB_PATH", "hisob_bot.db")

MENU = ReplyKeyboardMarkup(
    [
        [KeyboardButton("➕ Kirim"), KeyboardButton("➖ Chiqim")],
        [KeyboardButton("💰 Balans"), KeyboardButton("📊 Hisobot")],
        [KeyboardButton("🧾 Mening yozuvlarim"), KeyboardButton("ℹ️ Yordam")],
    ],
    resize_keyboard=True
)

AMOUNT, CURRENCY, CATEGORY, NOTE = range(4)


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                username TEXT,
                role TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN ('income','expense')),
                amount_minor INTEGER NOT NULL,
                currency TEXT NOT NULL CHECK(currency IN ('UZS','USD')),
                category TEXT NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL
            )
        """)


def user_row(user_id):
    with db() as conn:
        return conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()


def is_admin(user_id):
    return user_id in ADMIN_IDS or (
        (row := user_row(user_id)) is not None and row["role"] == "admin"
    )


def approved(user_id):
    row = user_row(user_id)
    return row is not None and row["role"] in ("admin", "employee")


def money_text(minor, currency):
    if currency == "UZS":
        return f"{minor:,.0f} so'm".replace(",", " ")
    return f"{minor / 100:,.2f} USD"


def parse_amount(raw, currency):
    cleaned = raw.strip().replace(" ", "").replace(",", ".")
    value = Decimal(cleaned)
    if value <= 0:
        raise InvalidOperation
    if currency == "UZS":
        if value != value.to_integral_value():
            raise InvalidOperation
        return int(value)
    return int((value * 100).quantize(Decimal("1")))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    now = datetime.now().isoformat(timespec="seconds")
    with db() as conn:
        existing = conn.execute("SELECT role FROM users WHERE user_id=?", (u.id,)).fetchone()
        if existing is None:
            role = "admin" if u.id in ADMIN_IDS else "pending"
            conn.execute(
                "INSERT INTO users(user_id,full_name,username,role,created_at) VALUES(?,?,?,?,?)",
                (u.id, u.full_name, u.username, role, now)
            )
        else:
            conn.execute(
                "UPDATE users SET full_name=?, username=? WHERE user_id=?",
                (u.full_name, u.username, u.id)
            )

    if is_admin(u.id):
        await update.message.reply_text(
            "Assalomu alaykum, admin! Hisob-kitob botiga xush kelibsiz.",
            reply_markup=MENU
        )
    elif approved(u.id):
        await update.message.reply_text(
            "Assalomu alaykum! Hisob-kitob botiga xush kelibsiz.",
            reply_markup=MENU
        )
    else:
        await update.message.reply_text(
            "So'rovingiz qabul qilindi. Admin sizga foydalanish huquqini bergach, botdan foydalana olasiz."
        )
        await notify_admins(context, f"Yangi foydalanuvchi ruxsat kutmoqda:\n{u.full_name}\nID: {u.id}\nUsername: @{u.username or 'yo‘q'}",
                            pending_user_id=u.id)


async def notify_admins(context, message, pending_user_id=None):
    markup = None
    if pending_user_id is not None:
        markup = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Xodim qilib tasdiqlash", callback_data=f"approve:{pending_user_id}"),
            InlineKeyboardButton("❌ Rad etish", callback_data=f"reject:{pending_user_id}")
        ]])
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(admin_id, message, reply_markup=markup)
        except Exception:
            pass


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "Botdan foydalanish:\n"
        "• ➕ Kirim — kelib tushgan pulni yozish\n"
        "• ➖ Chiqim — sarflangan pulni yozish\n"
        "• 💰 Balans — valyuta bo‘yicha umumiy qoldiq\n"
        "• 📊 Hisobot — davr bo‘yicha kirim/chiqim\n"
        "• 🧾 Mening yozuvlarim — oxirgi yozuvlaringiz\n\n"
        "Eslatma: UZS va USD alohida hisoblanadi; avtomatik konvertatsiya qilinmaydi."
    )
    await update.effective_message.reply_text(msg, reply_markup=MENU)


async def begin_transaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not approved(update.effective_user.id):
        await update.message.reply_text("Botdan foydalanish uchun admin tasdig'i kerak.")
        return ConversationHandler.END
    text = update.message.text
    context.user_data["kind"] = "income" if "Kirim" in text else "expense"
    context.user_data["kind_label"] = "Kirim" if context.user_data["kind"] == "income" else "Chiqim"
    await update.message.reply_text("Summani kiriting. Masalan: 250000 yoki 125.50")
    return AMOUNT


async def get_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["raw_amount"] = update.message.text.strip()
    await update.message.reply_text(
        "Valyutani tanlang:",
        reply_markup=ReplyKeyboardMarkup([["UZS — so'm", "USD — dollar"], ["Bekor qilish"]], resize_keyboard=True, one_time_keyboard=True)
    )
    return CURRENCY


async def get_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "Bekor qilish":
        await update.message.reply_text("Bekor qilindi.", reply_markup=MENU)
        return ConversationHandler.END
    if text.startswith("UZS"):
        currency = "UZS"
    elif text.startswith("USD"):
        currency = "USD"
    else:
        await update.message.reply_text("UZS yoki USD tugmasini tanlang.")
        return CURRENCY
    try:
        amount_minor = parse_amount(context.user_data["raw_amount"], currency)
    except (InvalidOperation, ValueError):
        await update.message.reply_text(
            "Summa noto'g'ri. UZS uchun butun son, USD uchun masalan 125.50 kiriting. Qayta summani yuboring."
        )
        return AMOUNT
    context.user_data["amount_minor"] = amount_minor
    context.user_data["currency"] = currency
    await update.message.reply_text(
        "Kategoriya yoki sababni kiriting (masalan: mahsulot, yo'l xarajati, mijoz to'lovi)."
    )
    return CATEGORY


async def get_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    category = update.message.text.strip()
    if not category or len(category) > 100:
        await update.message.reply_text("Iltimos, 1–100 belgidan iborat kategoriya kiriting.")
        return CATEGORY
    context.user_data["category"] = category
    await update.message.reply_text("Izoh kiriting yoki '-' yuboring.")
    return NOTE


async def get_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    note = update.message.text.strip()
    if note == "-":
        note = ""
    u = update.effective_user
    now = datetime.now().isoformat(sep=" ", timespec="seconds")
    kind = context.user_data["kind"]
    amount = context.user_data["amount_minor"]
    currency = context.user_data["currency"]
    category = context.user_data["category"]
    with db() as conn:
        conn.execute(
            """INSERT INTO transactions(user_id,kind,amount_minor,currency,category,note,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (u.id, kind, amount, currency, category, note, now)
        )
    await update.message.reply_text(
        f"✅ {context.user_data['kind_label']} saqlandi.\n"
        f"Summa: {money_text(amount, currency)}\n"
        f"Kategoriya: {category}\n"
        f"Izoh: {note or '—'}",
        reply_markup=MENU
    )
    for admin_id in ADMIN_IDS:
        if admin_id != u.id:
            try:
                await context.bot.send_message(
                    admin_id,
                    f"Yangi {context.user_data['kind_label'].lower()}:\n"
                    f"Xodim: {u.full_name} (ID {u.id})\n"
                    f"Summa: {money_text(amount, currency)}\n"
                    f"Kategoriya: {category}\nIzoh: {note or '—'}"
                )
            except Exception:
                pass
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Bekor qilindi.", reply_markup=MENU)
    return ConversationHandler.END


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not approved(update.effective_user.id):
        await update.message.reply_text("Admin tasdig'i kerak.")
        return
    if is_admin(update.effective_user.id):
        where, args = "", ()
        title = "Korxona umumiy balansi"
    else:
        where, args = " WHERE user_id=?", (update.effective_user.id,)
        title = "Sizning yozuvlaringiz bo'yicha balans"
    lines = [title]
    with db() as conn:
        for currency in ("UZS", "USD"):
            row = conn.execute(
                f"""SELECT
                    COALESCE(SUM(CASE WHEN kind='income' THEN amount_minor ELSE 0 END),0) AS inc,
                    COALESCE(SUM(CASE WHEN kind='expense' THEN amount_minor ELSE 0 END),0) AS exp
                    FROM transactions{where} {"AND" if where else "WHERE"} currency=?""",
                (*args, currency)
            ).fetchone()
            lines.append(
                f"\n{currency}\nKirim: {money_text(row['inc'], currency)}\n"
                f"Chiqim: {money_text(row['exp'], currency)}\n"
                f"Farq: {money_text(row['inc'] - row['exp'], currency)}"
            )
    await update.message.reply_text("\n".join(lines), reply_markup=MENU)


async def report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not approved(update.effective_user.id):
        await update.message.reply_text("Admin tasdig'i kerak.")
        return
    if is_admin(update.effective_user.id):
        where, args = "", ()
        title = "Korxona hisoboti"
    else:
        where, args = " WHERE user_id=?", (update.effective_user.id,)
        title = "Shaxsiy hisobotingiz"
    with db() as conn:
        lines = [title]
        for currency in ("UZS", "USD"):
            row = conn.execute(
                f"""SELECT
                    COALESCE(SUM(CASE WHEN kind='income' THEN amount_minor ELSE 0 END),0) AS inc,
                    COALESCE(SUM(CASE WHEN kind='expense' THEN amount_minor ELSE 0 END),0) AS exp,
                    COUNT(*) AS cnt
                    FROM transactions{where} {"AND" if where else "WHERE"} currency=?""",
                (*args, currency)
            ).fetchone()
            lines.append(f"\n{currency}: {row['cnt']} ta yozuv\nKirim: {money_text(row['inc'], currency)}\nChiqim: {money_text(row['exp'], currency)}\nFarq: {money_text(row['inc']-row['exp'], currency)}")
        if is_admin(update.effective_user.id):
            users = conn.execute("SELECT COUNT(*) AS n FROM users WHERE role='employee'").fetchone()["n"]
            pending = conn.execute("SELECT COUNT(*) AS n FROM users WHERE role='pending'").fetchone()["n"]
            lines.append(f"\nXodimlar: {users}\nRuxsat kutayotganlar: {pending}")
    await update.message.reply_text("\n".join(lines), reply_markup=MENU)


async def my_transactions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not approved(update.effective_user.id):
        await update.message.reply_text("Admin tasdig'i kerak.")
        return
    with db() as conn:
        rows = conn.execute(
            """SELECT kind, amount_minor, currency, category, note, created_at
               FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 10""",
            (update.effective_user.id,)
        ).fetchall()
    if not rows:
        await update.message.reply_text("Hozircha yozuvlar yo'q.", reply_markup=MENU)
        return
    lines = ["Oxirgi 10 ta yozuvingiz:"]
    for r in rows:
        kind = "KIRIM" if r["kind"] == "income" else "CHIQIM"
        lines.append(f"\n#{kind} | {money_text(r['amount_minor'], r['currency'])}\n{r['category']} — {r['created_at']}\n{r['note'] or ''}")
    await update.message.reply_text("\n".join(lines), reply_markup=MENU)


async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Bu buyruq faqat admin uchun.")
        return
    await update.message.reply_text(
        "Admin buyruqlari:\n"
        "/pending — ruxsat kutayotgan xodimlar\n"
        "/users — foydalanuvchilar ro'yxati\n"
        "/export — barcha yozuvlarni CSV fayl qilib olish\n"
        "/approve ID — xodimga ruxsat berish\n"
        "/disable ID — foydalanuvchini bloklash"
    )


async def pending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    with db() as conn:
        rows = conn.execute("SELECT * FROM users WHERE role='pending' ORDER BY created_at").fetchall()
    if not rows:
        await update.message.reply_text("Ruxsat kutayotgan foydalanuvchi yo'q.")
        return
    for row in rows:
        await update.message.reply_text(
            f"{row['full_name']}\nID: {row['user_id']}\nUsername: @{row['username'] or 'yo‘q'}",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve:{row['user_id']}"),
                InlineKeyboardButton("❌ Rad etish", callback_data=f"reject:{row['user_id']}")
            ]])
        )


async def users_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    with db() as conn:
        rows = conn.execute("SELECT user_id,full_name,username,role FROM users ORDER BY role,full_name").fetchall()
    lines = ["Foydalanuvchilar:"]
    lines.extend(f"{r['full_name']} | ID {r['user_id']} | @{r['username'] or 'yo‘q'} | {r['role']}" for r in rows)
    await update.message.reply_text("\n".join(lines)[:4000])


async def approve_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Foydalanish: /approve USER_ID")
        return
    uid = int(context.args[0])
    with db() as conn:
        conn.execute("UPDATE users SET role='employee' WHERE user_id=?", (uid,))
    await update.message.reply_text(f"{uid} foydalanuvchiga xodim huquqi berildi.")


async def disable_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text("Foydalanish: /disable USER_ID")
        return
    uid = int(context.args[0])
    if uid in ADMIN_IDS:
        await update.message.reply_text("Asosiy adminni bu buyruq bilan bloklab bo'lmaydi.")
        return
    with db() as conn:
        conn.execute("UPDATE users SET role='disabled' WHERE user_id=?", (uid,))
    await update.message.reply_text(f"{uid} foydalanuvchi bloklandi.")


async def approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("Bu amal faqat admin uchun.")
        return
    action, uid_text = query.data.split(":")
    uid = int(uid_text)
    with db() as conn:
        if action == "approve":
            conn.execute("UPDATE users SET role='employee' WHERE user_id=?", (uid,))
            msg = f"✅ {uid} xodim sifatida tasdiqlandi."
            try:
                await context.bot.send_message(uid, "Admin sizga botdan foydalanish huquqini berdi. /start bosing.")
            except Exception:
                pass
        else:
            conn.execute("UPDATE users SET role='disabled' WHERE user_id=?", (uid,))
            msg = f"❌ {uid} so'rovi rad etildi."
            try:
                await context.bot.send_message(uid, "Botdan foydalanish so'rovingiz rad etildi.")
            except Exception:
                pass
    await query.edit_message_text(msg)


async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Bu buyruq faqat admin uchun.")
        return
    with db() as conn:
        rows = conn.execute("""
            SELECT t.id, t.created_at, u.full_name, t.user_id, t.kind,
                   t.amount_minor, t.currency, t.category, t.note
            FROM transactions t LEFT JOIN users u ON u.user_id=t.user_id
            ORDER BY t.id
        """).fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Sana", "Xodim", "Telegram ID", "Turi", "Summa (minor units)", "Valyuta", "Kategoriya", "Izoh"])
    writer.writerows([tuple(r) for r in rows])
    data = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    data.name = "hisobot.csv"
    await update.message.reply_document(document=data, caption="Barcha kirim-chiqim yozuvlari (CSV).")


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text("Menyudan foydalaning yoki /help buyrug'ini yuboring.", reply_markup=MENU)


def main():
    if not TOKEN:
        raise SystemExit("BOT_TOKEN muhit o'zgaruvchisi kiritilmagan.")
    if not ADMIN_IDS:
        raise SystemExit("ADMIN_IDS ga kamida bitta Telegram raqamli ID kiriting.")
    init_db()
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r"^➕ Kirim$"), begin_transaction),
            MessageHandler(filters.Regex(r"^➖ Chiqim$"), begin_transaction),
        ],
        states={
            AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_amount)],
            CURRENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_currency)],
            CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_category)],
            NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_note)],
        },
        fallbacks=[CommandHandler("cancel", cancel), MessageHandler(filters.Regex(r"^Bekor qilish$"), cancel)],
        allow_reentry=True,
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("pending", pending_cmd))
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("approve", approve_cmd))
    app.add_handler(CommandHandler("disable", disable_cmd))
    app.add_handler(CommandHandler("export", export_cmd))
    app.add_handler(CallbackQueryHandler(approval_callback, pattern=r"^(approve|reject):\d+$"))
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.Regex(r"^💰 Balans$"), balance))
    app.add_handler(MessageHandler(filters.Regex(r"^📊 Hisobot$"), report))
    app.add_handler(MessageHandler(filters.Regex(r"^🧾 Mening yozuvlarim$"), my_transactions))
    app.add_handler(MessageHandler(filters.Regex(r"^ℹ️ Yordam$"), help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unknown))
    print("Hisob-kitob boti ishga tushdi.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

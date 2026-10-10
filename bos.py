import logging
import os
import sqlite3
import asyncio
from datetime import datetime
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputMediaPhoto
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Configuration & Environment Variables
BOT_TOKEN = os.getenv("8848201471:AAGHchewkhO2CI-_63R6CAJ7JsCjYFNd0lU", "")
ADMIN_ID_RAW = os.getenv("8170952537", "0")
try:
    ADMIN_ID = int(ADMIN_ID_RAW)
except ValueError:
    ADMIN_ID = 0

DB_FILE = "bot_data.db"

# Setup Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Predefined Default Custom Messages
DEFAULT_MESSAGES = {
    "welcome": (
        "Welcome to @Rayyan_Hacks Store! 🛍️\n\n"
        "Explore our latest deals, buy access keys, or raise a support ticket."
    ),
    "help": "Navigate using the menu buttons below. Contact admin for assistance.",
    "rules": (
        "📜 *Rules & Guidelines*\n\n"
        "1. Payments are manually verified by our team.\n"
        "2. Do not submit fake payment verification requests.\n"
        "3. Support responses may take up to 24 hours."
    ),
    "payment_instructions": (
        "Please send the exact amount using the QR code below.\n"
        "Once transferred, click *I Have Paid* to notify our team."
    ),
    "payment_pending": "Please Patient Over Team Scan Your Payment.\n\nRegards,\n@Rayyan_Hacks Team",
    "payment_approved": "✅ Your payment has been verified! Thank you for your purchase.",
    "payment_rejected": "❌ Your payment request was rejected.",
    "purchase_successful": "📦 Your purchase was completed successfully.",
    "support_confirmation": "🎫 Your ticket #{ticket_id} has been opened. An admin will respond shortly.",
    "unknown_command": "Unrecognized command or selection. Returning to main menu.",
    "maintenance_notice": "🛠️ The bot is currently under routine maintenance.",
}

# Key Plans Configuration
KEY_PLANS = {
    "1_day": {"title": "1 Day Key", "price": 70},
    "1_week": {"title": "1 Week Key", "price": 199},
    "1_month": {"title": "1 Month Key", "price": 389},
    "session": {"title": "Full Session Key", "price": 689},
}

# Database Initialization
def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        registration_date TEXT
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS deals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        price REAL NOT NULL,
        description TEXT,
        product_link TEXT,
        active INTEGER DEFAULT 1
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        item_title TEXT NOT NULL,
        amount REAL NOT NULL,
        status TEXT DEFAULT 'pending',
        delivery_details TEXT,
        delivery_timestamp TEXT,
        created_at TEXT NOT NULL
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payment_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        order_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        item_title TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        rejection_reason TEXT,
        created_at TEXT NOT NULL
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS support_tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        message TEXT NOT NULL,
        status TEXT DEFAULT 'Open',
        admin_reply TEXT,
        created_at TEXT NOT NULL
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS custom_messages (
        key TEXT PRIMARY KEY,
        val TEXT NOT NULL
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        val TEXT NOT NULL
    )""")
    
    # Pre-populate custom messages if missing
    for k, v in DEFAULT_MESSAGES.items():
        cursor.execute("INSERT OR IGNORE INTO custom_messages (key, val) VALUES (?, ?)", (k, v))
        
    conn.commit()
    conn.close()

def get_msg(key: str) -> str:
    conn = get_db_connection()
    row = conn.execute("SELECT val FROM custom_messages WHERE key = ?", (key,)).fetchone()
    conn.close()
    if row:
        return row["val"]
    return DEFAULT_MESSAGES.get(key, "")

def set_msg(key: str, val: str):
    conn = get_db_connection()
    conn.execute("INSERT OR REPLACE INTO custom_messages (key, val) VALUES (?, ?)", (key, val))
    conn.commit()
    conn.close()

def is_admin(user_id: int) -> bool:
    return ADMIN_ID != 0 and user_id == ADMIN_ID

# Database Helpers
def register_user(user):
    conn = get_db_connection()
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, username, first_name, registration_date) VALUES (?, ?, ?, ?)",
        (user.id, user.username, user.first_name, datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()

# Keyboards
def get_main_menu_keyboard(user_id: int):
    keyboard = [
        [InlineKeyboardButton("🛍️ Deals", callback_data="menu_deals"), InlineKeyboardButton("🔑 Buy Keys", callback_data="menu_buy_keys")],
        [InlineKeyboardButton("💳 Payment Info", callback_data="menu_payment"), InlineKeyboardButton("📦 My Purchases", callback_data="menu_purchases")],
        [InlineKeyboardButton("🎧 Customer Support", callback_data="menu_support"), InlineKeyboardButton("📜 Rules", callback_data="menu_rules")],
        [InlineKeyboardButton("📞 Contact Admin", callback_data="menu_contact")]
    ]
    if is_admin(user_id):
        keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_dashboard")])
    return InlineKeyboardMarkup(keyboard)

def get_back_keyboard(target: str = "main_menu"):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"nav_{target}")]])

def get_admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Dashboard Stats", callback_data="admin_stats"), InlineKeyboardButton("➕ Add Deal", callback_data="admin_add_deal")],
        [InlineKeyboardButton("✏️ Manage Deals", callback_data="admin_manage_deals"), InlineKeyboardButton("💳 Pending Payments", callback_data="admin_pending_payments")],
        [InlineKeyboardButton("👥 Search Users", callback_data="admin_search_users"), InlineKeyboardButton("📦 Manage Orders", callback_data="admin_manage_orders")],
        [InlineKeyboardButton("🧾 Set Payment QR", callback_data="admin_set_qr"), InlineKeyboardButton("🎧 Support Tickets", callback_data="admin_tickets")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast"), InlineKeyboardButton("⚙️ Edit Messages", callback_data="admin_edit_msgs")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="nav_main_menu")]
    ])

# Menu Handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)
    welcome_text = get_msg("welcome")
    await update.message.reply_text(welcome_text, reply_markup=get_main_menu_keyboard(user.id))

async def handle_navigation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user

    context.user_data["state"] = None  # Reset step states

    if data == "nav_main_menu":
        await query.edit_message_text(
            get_msg("welcome"),
            reply_markup=get_main_menu_keyboard(user.id)
        )
    elif data == "menu_rules":
        await query.edit_message_text(
            get_msg("rules"),
            parse_mode="Markdown",
            reply_markup=get_back_keyboard()
        )
    elif data == "menu_contact":
        conn = get_db_connection()
        admin_row = conn.execute("SELECT username FROM users WHERE user_id = ?", (ADMIN_ID,)).fetchone()
        conn.close()
        admin_handle = f"@{admin_row['username']}" if admin_row and admin_row['username'] else f"User ID: {ADMIN_ID}"
        await query.edit_message_text(
            f"📞 *Contact Administrator*\n\nYou can contact our support admin directly at: {admin_handle}",
            parse_mode="Markdown",
            reply_markup=get_back_keyboard()
        )
    elif data == "menu_payment":
        conn = get_db_connection()
        qr_row = conn.execute("SELECT val FROM settings WHERE key = 'payment_qr_file_id'").fetchone()
        conn.close()
        
        msg = f"💳 *Payment Information*\n\n{get_msg('payment_instructions')}"
        if qr_row and qr_row['val']:
            try:
                await query.message.reply_photo(
                    photo=qr_row['val'],
                    caption=msg,
                    parse_mode="Markdown",
                    reply_markup=get_back_keyboard()
                )
                await query.message.delete()
            except Exception:
                await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=get_back_keyboard())
        else:
            await query.edit_message_text(
                f"{msg}\n\n*(No QR image currently set by admin)*",
                parse_mode="Markdown",
                reply_markup=get_back_keyboard()
            )

# Deals & Key Shop
async def handle_deals_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    conn = get_db_connection()
    deals = conn.execute("SELECT * FROM deals WHERE active = 1").fetchall()
    conn.close()

    if not deals:
        await query.edit_message_text("🛍️ No active deals at the moment.", reply_markup=get_back_keyboard())
        return

    keyboard = []
    for d in deals:
        keyboard.append([InlineKeyboardButton(f"{d['title']} - ₹{d['price']}", callback_data=f"view_deal_{d['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="nav_main_menu")])

    await query.edit_message_text("🛍️ *Available Deals*\nSelect a deal to view details:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_view_deal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    deal_id = int(query.data.split("_")[2])

    conn = get_db_connection()
    deal = conn.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone()
    conn.close()

    if not deal:
        await query.edit_message_text("Deal not found or has been removed.", reply_markup=get_back_keyboard("deals"))
        return

    msg = f"🛍️ *{deal['title']}*\n\n💰 *Price:* ₹{deal['price']}\n\n📝 *Description:*\n{deal['description']}"
    keyboard = [
        [InlineKeyboardButton("🛒 Buy Now", callback_data=f"buy_deal_{deal['id']}")],
        [InlineKeyboardButton("🔙 Back", callback_data="menu_deals")]
    ]
    await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_buy_keys_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    keyboard = []
    for plan_key, plan in KEY_PLANS.items():
        keyboard.append([InlineKeyboardButton(f"{plan['title']} — ₹{plan['price']}", callback_data=f"buy_key_{plan_key}")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="nav_main_menu")])

    await query.edit_message_text("🔑 *Select Access Key Plan:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

# Checkout & Payment Request Handling
async def handle_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    data = query.data

    if data.startswith("buy_deal_"):
        deal_id = int(data.split("_")[2])
        conn = get_db_connection()
        item = conn.execute("SELECT title, price FROM deals WHERE id = ?", (deal_id,)).fetchone()
        conn.close()
        if not item:
            await query.edit_message_text("Item unavailable.", reply_markup=get_back_keyboard())
            return
        title, price = item["title"], item["price"]
    elif data.startswith("buy_key_"):
        plan_key = data.replace("buy_key_", "")
        plan = KEY_PLANS.get(plan_key)
        if not plan:
            await query.edit_message_text("Plan unavailable.", reply_markup=get_back_keyboard())
            return
        title, price = plan["title"], plan["price"]
    else:
        return

    # Check duplicate pending requests
    conn = get_db_connection()
    pending = conn.execute(
        "SELECT id FROM payment_requests WHERE user_id = ? AND item_title = ? AND status = 'pending'",
        (user.id, title)
    ).fetchone()

    if pending:
        conn.close()
        await query.edit_message_text(
            f"⚠️ You already have a pending payment verification request for *{title}*.\n\n{get_msg('payment_pending')}",
            parse_mode="Markdown",
            reply_markup=get_back_keyboard()
        )
        return

    # Create Order
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO orders (user_id, item_title, amount, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
        (user.id, title, price, now)
    )
    order_id = cursor.lastrowid
    conn.commit()

    qr_row = conn.execute("SELECT val FROM settings WHERE key = 'payment_qr_file_id'").fetchone()
    conn.close()

    context.user_data[f"checkout_{order_id}"] = {"title": title, "price": price}

    msg = (
        f"💳 *Order Summary*\n\n"
        f"📌 *Item:* {title}\n"
        f"💰 *Total Amount:* ₹{price}\n\n"
        f"{get_msg('payment_instructions')}"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ I Have Paid", callback_data=f"confirm_payment_{order_id}")],
        [InlineKeyboardButton("❌ Cancel", callback_data="nav_main_menu")]
    ])

    if qr_row and qr_row["val"]:
        try:
            await query.message.reply_photo(photo=qr_row["val"], caption=msg, parse_mode="Markdown", reply_markup=keyboard)
            await query.message.delete()
        except Exception:
            await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=keyboard)
    else:
        await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=keyboard)

async def handle_confirm_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    order_id = int(query.data.split("_")[2])

    conn = get_db_connection()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()

    if not order:
        conn.close()
        await query.edit_message_text("Order record not found.", reply_markup=get_back_keyboard())
        return

    # Prevent duplicates
    existing = conn.execute("SELECT id FROM payment_requests WHERE order_id = ? AND status = 'pending'", (order_id,)).fetchone()
    if existing:
        conn.close()
        await query.edit_message_text(get_msg("payment_pending"), reply_markup=get_back_keyboard())
        return

    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO payment_requests (user_id, order_id, amount, item_title, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)",
        (user.id, order_id, order["amount"], order["item_title"], now)
    )
    req_id = cursor.lastrowid
    conn.commit()
    conn.close()

    await query.edit_message_text(get_msg("payment_pending"), reply_markup=get_back_keyboard())

    # Notify Admin
    if ADMIN_ID != 0:
        admin_msg = (
            f"🚨 *New Payment Verification Request*\n\n"
            f"👤 *User:* {user.first_name} (@{user.username or 'N/A'})\n"
            f"🆔 *User ID:* `{user.id}`\n"
            f"🛒 *Item:* {order['item_title']}\n"
            f"💰 *Amount:* ₹{order['amount']}\n"
            f"🔢 *Order ID:* `{order_id}`"
        )
        admin_kbd = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Accept", callback_data=f"adm_pay_accept_{req_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"adm_pay_reject_{req_id}")
            ]
        ])
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg, parse_mode="Markdown", reply_markup=admin_kbd)
        except Exception as e:
            logger.error(f"Failed to notify admin: {e}")

# My Purchases
async def handle_my_purchases(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    conn = get_db_connection()
    orders = conn.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC LIMIT 10", (user.id,)).fetchall()
    conn.close()

    if not orders:
        await query.edit_message_text("📦 You have no order history yet.", reply_markup=get_back_keyboard())
        return

    text = "📦 *Your Recent Purchases*\n\n"
    for o in orders:
        status_icon = "✅" if o["status"] == "approved" else ("❌" if o["status"] == "rejected" else "⏳")
        text += f"{status_icon} *{o['item_title']}* — ₹{o['amount']}\nStatus: `{o['status']}`\n"
        if o["delivery_details"]:
            text += f"📦 *Delivery Info:* {o['delivery_details']}\n"
        text += "------------------------------\n"

    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=get_back_keyboard())

# Support Tickets
async def handle_support_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    conn = get_db_connection()
    tickets = conn.execute("SELECT * FROM support_tickets WHERE user_id = ? ORDER BY id DESC LIMIT 5", (user.id,)).fetchall()
    conn.close()

    text = "🎧 *Customer Support*\n\nClick below to create a new ticket or review past queries:\n\n"
    if tickets:
        text += "*Recent Tickets:*\n"
        for t in tickets:
            text += f"🎫 Ticket #{t['id']} — `{t['status']}`\nMessage: {t['message'][:40]}...\n"
            if t["admin_reply"]:
                text += f"💬 *Reply:* {t['admin_reply']}\n"
            text += "\n"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Open New Ticket", callback_data="support_new_ticket")],
        [InlineKeyboardButton("🔙 Back", callback_data="nav_main_menu")]
    ])
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)

async def handle_new_ticket_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["state"] = "awaiting_support_msg"
    await query.edit_message_text("📝 Please send your support query/message now:", reply_markup=get_back_keyboard("support"))

# Admin Panel Functions
async def handle_admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if not is_admin(user.id):
        await query.edit_message_text("Unauthorized access.")
        return

    await query.edit_message_text("⚙️ *Admin Dashboard*\nSelect a management option below:", parse_mode="Markdown", reply_markup=get_admin_keyboard())

async def handle_admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    conn = get_db_connection()
    tot_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    paid_users = conn.execute("SELECT COUNT(DISTINCT user_id) FROM orders WHERE status = 'approved'").fetchone()[0]
    tot_orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    pending_pay = conn.execute("SELECT COUNT(*) FROM payment_requests WHERE status = 'pending'").fetchone()[0]
    app_pay = conn.execute("SELECT COUNT(*) FROM payment_requests WHERE status = 'approved'").fetchone()[0]
    rej_pay = conn.execute("SELECT COUNT(*) FROM payment_requests WHERE status = 'rejected'").fetchone()[0]
    act_deals = conn.execute("SELECT COUNT(*) FROM deals WHERE active = 1").fetchone()[0]
    open_tickets = conn.execute("SELECT COUNT(*) FROM support_tickets WHERE status = 'Open'").fetchone()[0]
    conn.close()

    msg = (
        f"📊 *Dashboard Statistics*\n\n"
        f"👥 Total Users: `{tot_users}`\n"
        f"💎 Verified Paid Users: `{paid_users}`\n"
        f"📦 Total Orders: `{tot_orders}`\n"
        f"💳 Pending Payments: `{pending_pay}`\n"
        f"✅ Approved Payments: `{app_pay}`\n"
        f"❌ Rejected Payments: `{rej_pay}`\n"
        f"🛍️ Active Deals: `{act_deals}`\n"
        f"🎧 Open Tickets: `{open_tickets}`"
    )
    await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=get_back_keyboard("admin"))

async def handle_admin_pending_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    conn = get_db_connection()
    requests = conn.execute("SELECT * FROM payment_requests WHERE status = 'pending' ORDER BY id DESC").fetchall()
    conn.close()

    if not requests:
        await query.edit_message_text("💳 No pending payment requests.", reply_markup=get_back_keyboard("admin"))
        return

    keyboard = []
    for r in requests:
        keyboard.append([InlineKeyboardButton(f"Req #{r['id']} - ₹{r['amount']} (User: {r['user_id']})", callback_data=f"adm_view_pay_{r['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_dashboard")])

    await query.edit_message_text("💳 *Pending Payments:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_admin_view_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    req_id = int(query.data.split("_")[3])
    conn = get_db_connection()
    req = conn.execute("SELECT * FROM payment_requests WHERE id = ?", (req_id,)).fetchone()
    conn.close()

    if not req:
        await query.edit_message_text("Request not found.", reply_markup=get_back_keyboard("admin"))
        return

    msg = (
        f"💳 *Payment Verification Request #{req['id']}*\n\n"
        f"👤 *User ID:* `{req['user_id']}`\n"
        f"🛒 *Item:* {req['item_title']}\n"
        f"💰 *Amount:* ₹{req['amount']}\n"
        f"📅 *Date:* {req['created_at']}\n"
        f"Status: `{req['status']}`"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Accept", callback_data=f"adm_pay_accept_{req['id']}"), InlineKeyboardButton("❌ Reject", callback_data=f"adm_pay_reject_{req['id']}")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_pending_payments")]
    ])
    await query.edit_message_text(msg, parse_mode="Markdown", reply_markup=keyboard)

async def handle_admin_pay_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    parts = query.data.split("_")
    action = parts[2]
    req_id = int(parts[3])

    conn = get_db_connection()
    req = conn.execute("SELECT * FROM payment_requests WHERE id = ?", (req_id,)).fetchone()

    if not req or req["status"] != "pending":
        conn.close()
        await query.edit_message_text("Payment request already processed or invalid.", reply_markup=get_back_keyboard("admin"))
        return

    if action == "accept":
        conn.execute("UPDATE payment_requests SET status = 'approved' WHERE id = ?", (req_id,))
        conn.execute("UPDATE orders SET status = 'approved' WHERE id = ?", (req["order_id"],))
        conn.commit()
        conn.close()

        await query.edit_message_text(f"✅ Payment #{req_id} accepted.", reply_markup=get_back_keyboard("admin"))
        
        # Notify Buyer
        try:
            await context.bot.send_message(chat_id=req["user_id"], text=get_msg("payment_approved"))
        except Exception as e:
            logger.error(f"Buyer notification failed: {e}")

        # Prompt Delivery Setup to Admin
        kbd = InlineKeyboardMarkup([[InlineKeyboardButton("📦 Deliver Product Now", callback_data=f"adm_deliver_{req['order_id']}")]])
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📦 *Payment Approved for Order #{req['order_id']}*\nClick below to deliver the product content.",
            parse_mode="Markdown",
            reply_markup=kbd
        )

    elif action == "reject":
        conn.execute("UPDATE payment_requests SET status = 'rejected' WHERE id = ?", (req_id,))
        conn.execute("UPDATE orders SET status = 'rejected' WHERE id = ?", (req["order_id"],))
        conn.commit()
        conn.close()

        await query.edit_message_text(f"❌ Payment #{req_id} rejected.", reply_markup=get_back_keyboard("admin"))

        try:
            await context.bot.send_message(chat_id=req["user_id"], text=get_msg("payment_rejected"))
        except Exception as e:
            logger.error(f"Buyer rejection notification failed: {e}")

# Product Delivery Flow
async def handle_admin_deliver_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    order_id = int(query.data.split("_")[2])
    context.user_data["deliver_order_id"] = order_id
    context.user_data["state"] = "awaiting_delivery_content"

    await query.edit_message_text(
        f"📦 *Deliver Content for Order #{order_id}*\n\n"
        f"Please send the product message, download link, photo, or document to send to the buyer:",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard("admin")
    )

# Admin Deal Management
async def handle_admin_add_deal_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    context.user_data["state"] = "awaiting_deal_details"
    await query.edit_message_text(
        "➕ *Add New Deal*\n\nPlease enter the deal details in the following format:\n\n"
        "`Title | Price | Description | Link(optional)`\n\n"
        "Example:\n`VIP Mod Key | 499 | Access for 30 days | https://example.com`",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard("admin")
    )

async def handle_admin_manage_deals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    conn = get_db_connection()
    deals = conn.execute("SELECT * FROM deals").fetchall()
    conn.close()

    if not deals:
        await query.edit_message_text("No deals exist.", reply_markup=get_back_keyboard("admin"))
        return

    keyboard = []
    for d in deals:
        status = "🟢" if d["active"] else "🔴"
        keyboard.append([InlineKeyboardButton(f"{status} {d['title']} - ₹{d['price']}", callback_data=f"adm_toggle_deal_{d['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_dashboard")])

    await query.edit_message_text("✏️ *Manage Deals*\nClick a deal to toggle active status:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_admin_toggle_deal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    deal_id = int(query.data.split("_")[3])
    conn = get_db_connection()
    conn.execute("UPDATE deals SET active = CASE WHEN active = 1 THEN 0 ELSE 1 END WHERE id = ?", (deal_id,))
    conn.commit()
    conn.close()

    await handle_admin_manage_deals(update, context)

# Admin Settings & Features
async def handle_admin_set_qr_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    context.user_data["state"] = "awaiting_qr_photo"
    await query.edit_message_text("🧾 Please upload the new Payment QR Code photo now:", reply_markup=get_back_keyboard("admin"))

async def handle_admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    context.user_data["state"] = "awaiting_broadcast_msg"
    await query.edit_message_text("📢 Send the broadcast message text you wish to send to all users:", reply_markup=get_back_keyboard("admin"))

async def handle_admin_tickets_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    conn = get_db_connection()
    tickets = conn.execute("SELECT * FROM support_tickets WHERE status = 'Open' ORDER BY id DESC").fetchall()
    conn.close()

    if not tickets:
        await query.edit_message_text("🎧 No open support tickets.", reply_markup=get_back_keyboard("admin"))
        return

    keyboard = []
    for t in tickets:
        keyboard.append([InlineKeyboardButton(f"Ticket #{t['id']} (User: {t['user_id']})", callback_data=f"adm_reply_tkt_{t['id']}")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_dashboard")])

    await query.edit_message_text("🎧 *Open Support Tickets:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_admin_reply_ticket_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    tkt_id = int(query.data.split("_")[3])
    context.user_data["reply_ticket_id"] = tkt_id
    context.user_data["state"] = "awaiting_ticket_reply"

    conn = get_db_connection()
    tkt = conn.execute("SELECT * FROM support_tickets WHERE id = ?", (tkt_id,)).fetchone()
    conn.close()

    await query.edit_message_text(
        f"💬 *Replying to Ticket #{tkt_id}*\n\nUser Message: {tkt['message']}\n\nPlease enter your reply:",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard("admin")
    )

async def handle_admin_edit_msgs_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    keyboard = []
    for k in DEFAULT_MESSAGES.keys():
        keyboard.append([InlineKeyboardButton(f"Edit: {k}", callback_data=f"adm_editmsg_{k}")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_dashboard")])

    await query.edit_message_text("⚙️ *Edit Custom Text Messages:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_admin_edit_msg_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    msg_key = query.data.replace("adm_editmsg_", "")
    context.user_data["edit_msg_key"] = msg_key
    context.user_data["state"] = "awaiting_custom_msg_text"

    cur_val = get_msg(msg_key)
    await query.edit_message_text(
        f"⚙️ *Editing Message:* `{msg_key}`\n\n"
        f"*Current Content:*\n{cur_val}\n\n"
        f"Please send the new message text:",
        parse_mode="Markdown",
        reply_markup=get_back_keyboard("admin")
    )

# Universal Text Message Handler (State Machine)
async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text or ""
    state = context.user_data.get("state")

    # State: User submitting support query
    if state == "awaiting_support_msg":
        context.user_data["state"] = None
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO support_tickets (user_id, message, created_at) VALUES (?, ?, ?)", (user.id, text, now))
        tkt_id = cursor.lastrowid
        conn.commit()
        conn.close()

        confirmation = get_msg("support_confirmation").format(ticket_id=tkt_id)
        await update.message.reply_text(confirmation, reply_markup=get_back_keyboard())

        if ADMIN_ID != 0:
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID,
                    text=f"🎧 *New Support Ticket #{tkt_id}*\nUser: `{user.id}`\nMessage: {text}"
                )
            except Exception as e:
                logger.error(f"Failed to alert admin on ticket: {e}")
        return

    # Admin actions check
    if is_admin(user.id):
        if state == "awaiting_deal_details":
            context.user_data["state"] = None
            parts = [p.strip() for p in text.split("|")]
            if len(parts) < 3:
                await update.message.reply_text("❌ Invalid format. Please use: `Title | Price | Description | Link(optional)`", parse_mode="Markdown")
                return
            title = parts[0]
            try:
                price = float(parts[1])
            except ValueError:
                await update.message.reply_text("❌ Price must be a valid number.")
                return
            desc = parts[2]
            link = parts[3] if len(parts) > 3 else ""

            conn = get_db_connection()
            conn.execute("INSERT INTO deals (title, price, description, product_link) VALUES (?, ?, ?, ?)", (title, price, desc, link))
            conn.commit()
            conn.close()

            await update.message.reply_text(f"✅ Deal *{title}* added successfully!", parse_mode="Markdown", reply_markup=get_back_keyboard("admin"))
            return

        elif state == "awaiting_broadcast_msg":
            context.user_data["state"] = None
            conn = get_db_connection()
            users = conn.execute("SELECT user_id FROM users").fetchall()
            conn.close()

            sent, failed = 0, 0
            for u in users:
                try:
                    await context.bot.send_message(chat_id=u["user_id"], text=text)
                    sent += 1
                    await asyncio.sleep(0.05) # Rate limiting
                except Exception:
                    failed += 1

            await update.message.reply_text(f"📢 Broadcast complete.\n\n✅ Delivered: {sent}\n❌ Failed: {failed}", reply_markup=get_back_keyboard("admin"))
            return

        elif state == "awaiting_ticket_reply":
            context.user_data["state"] = None
            tkt_id = context.user_data.get("reply_ticket_id")
            
            conn = get_db_connection()
            tkt = conn.execute("SELECT * FROM support_tickets WHERE id = ?", (tkt_id,)).fetchone()
            if tkt:
                conn.execute("UPDATE support_tickets SET status = 'Replied', admin_reply = ? WHERE id = ?", (text, tkt_id))
                conn.commit()
                conn.close()
                await update.message.reply_text(f"✅ Reply sent for ticket #{tkt_id}.", reply_markup=get_back_keyboard("admin"))

                try:
                    await context.bot.send_message(chat_id=tkt["user_id"], text=f"💬 *Admin Response to Ticket #{tkt_id}:*\n\n{text}", parse_mode="Markdown")
                except Exception as e:
                    logger.error(f"Failed to deliver ticket reply to user: {e}")
            else:
                conn.close()
            return

        elif state == "awaiting_custom_msg_text":
            context.user_data["state"] = None
            msg_key = context.user_data.get("edit_msg_key")
            set_msg(msg_key, text)
            await update.message.reply_text(f"✅ Message `{msg_key}` updated successfully.", parse_mode="Markdown", reply_markup=get_back_keyboard("admin"))
            return

        elif state == "awaiting_delivery_content":
            context.user_data["state"] = None
            order_id = context.user_data.get("deliver_order_id")
            now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

            conn = get_db_connection()
            order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
            if order:
                conn.execute("UPDATE orders SET delivery_details = ?, delivery_timestamp = ? WHERE id = ?", (text, now, order_id))
                conn.commit()
                conn.close()

                await update.message.reply_text(f"✅ Product delivered for Order #{order_id}.", reply_markup=get_back_keyboard("admin"))

                try:
                    await context.bot.send_message(
                        chat_id=order["user_id"],
                        text=f"📦 *Your Purchase Delivery (Order #{order_id})*\n\n{text}",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logger.error(f"Product delivery failed: {e}")
            else:
                conn.close()
            return

    await update.message.reply_text(get_msg("unknown_command"), reply_markup=get_main_menu_keyboard(user.id))

# Photos and Attachments Handler
async def handle_photo_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    state = context.user_data.get("state")

    if is_admin(user.id) and state == "awaiting_qr_photo":
        context.user_data["state"] = None
        photo_file_id = update.message.photo[-1].file_id

        conn = get_db_connection()
        conn.execute("INSERT OR REPLACE INTO settings (key, val) VALUES ('payment_qr_file_id', ?)", (photo_file_id,))
        conn.commit()
        conn.close()

        await update.message.reply_text("✅ Payment QR code updated successfully!", reply_markup=get_back_keyboard("admin"))

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN environment variable not found. Exiting.")
        return

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", start_command))

    # Navigation Callbacks
    app.add_handler(CallbackQueryHandler(handle_navigation, pattern="^nav_"))
    app.add_handler(CallbackQueryHandler(handle_navigation, pattern="^menu_(rules|contact|payment)$"))
    app.add_handler(CallbackQueryHandler(handle_deals_menu, pattern="^menu_deals$"))
    app.add_handler(CallbackQueryHandler(handle_buy_keys_menu, pattern="^menu_buy_keys$"))
    app.add_handler(CallbackQueryHandler(handle_my_purchases, pattern="^menu_purchases$"))
    app.add_handler(CallbackQueryHandler(handle_support_menu, pattern="^menu_support$"))
    
    # Store Actions
    app.add_handler(CallbackQueryHandler(handle_view_deal, pattern="^view_deal_"))
    app.add_handler(CallbackQueryHandler(handle_checkout, pattern="^buy_(deal|key)_"))
    app.add_handler(CallbackQueryHandler(handle_confirm_payment, pattern="^confirm_payment_"))
    app.add_handler(CallbackQueryHandler(handle_new_ticket_start, pattern="^support_new_ticket$"))

    # Admin Panel Callbacks
    app.add_handler(CallbackQueryHandler(handle_admin_dashboard, pattern="^admin_dashboard$"))
    app.add_handler(CallbackQueryHandler(handle_admin_stats, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(handle_admin_pending_payments, pattern="^admin_pending_payments$"))
    app.add_handler(CallbackQueryHandler(handle_admin_view_payment, pattern="^adm_view_pay_"))
    app.add_handler(CallbackQueryHandler(handle_admin_pay_action, pattern="^adm_pay_(accept|reject)_"))
    app.add_handler(CallbackQueryHandler(handle_admin_deliver_start, pattern="^adm_deliver_"))
    app.add_handler(CallbackQueryHandler(handle_admin_add_deal_start, pattern="^admin_add_deal$"))
    app.add_handler(CallbackQueryHandler(handle_admin_manage_deals, pattern="^admin_manage_deals$"))
    app.add_handler(CallbackQueryHandler(handle_admin_toggle_deal, pattern="^adm_toggle_deal_"))
    app.add_handler(CallbackQueryHandler(handle_admin_set_qr_start, pattern="^admin_set_qr$"))
    app.add_handler(CallbackQueryHandler(handle_admin_broadcast_start, pattern="^admin_broadcast$"))
    app.add_handler(CallbackQueryHandler(handle_admin_tickets_list, pattern="^admin_tickets$"))
    app.add_handler(CallbackQueryHandler(handle_admin_reply_ticket_start, pattern="^adm_reply_tkt_"))
    app.add_handler(CallbackQueryHandler(handle_admin_edit_msgs_list, pattern="^admin_edit_msgs$"))
    app.add_handler(CallbackQueryHandler(handle_admin_edit_msg_start, pattern="^adm_editmsg_"))

    # Message Handlers
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo_messages))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))

    logger.info("Bot starting polling...")
    app.run_polling()

if __name__ == "__main__":
    main()

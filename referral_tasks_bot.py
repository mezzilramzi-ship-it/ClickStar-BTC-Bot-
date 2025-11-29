"""
referral_tasks_bot.py
TeleBot (pyTelegramBotAPI) referral + tasks bot with Firebase Realtime DB.
No daily bonus. Tasks: Visit Sites, Join Channels, Join Bots, More, Advertise.
"""

import time
import logging
from functools import wraps

import telebot
from telebot import types

import firebase_admin
from firebase_admin import credentials, db

# ------------------ CONFIG ------------------
BOT_TOKEN = "7699582484:AAF6te7oE49CgaIzOskZdQRyXMjXpoluqX4"  # <-- replace with your bot token
FIREBASE_DB_URL ="https://clickstar-btc-bot-default-rtdb.firebaseio.com/"  # <-- replace (no trailing slash)
SERVICE_ACCOUNT_FILE = "clickstar-btc-bot-firebase-adminsdk-fbsvc-e3232306d4.json"

# Points for different task types (customize)
POINTS_VISIT = 3
POINTS_JOIN_CHANNEL = 8
POINTS_JOIN_BOT = 5
POINTS_OTHER = 4

# Referral points
POINTS_FOR_REFERRAL = 10

# Admin Telegram user ids
ADMINS = {123456789}  # <-- replace with your Telegram numeric id(s)
# --------------------------------------------

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Firebase
cred = credentials.Certificate(SERVICE_ACCOUNT_FILE)
firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})
root_ref = db.reference("/")
users_ref = root_ref.child("users")
tasks_ref = root_ref.child("tasks")          # task catalog (available tasks)
completions_ref = root_ref.child("completions")  # which user completed which task
ads_ref = root_ref.child("ads")              # advertise entries

# Initialize bot
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")


# ------------------ Helpers ------------------

def require_admin(func):
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "❌ You are not an admin.")
            return
        return func(message, *args, **kwargs)
    return wrapper

def get_user(uid):
    return users_ref.child(str(uid)).get()

def create_user_if_missing(uid, username=None, first_name=None):
    uid_s = str(uid)
    if not users_ref.child(uid_s).get():
        users_ref.child(uid_s).set({
            "points": 0,
            "referrals": 0,
            "referred_by": None,
            "username": username or "",
            "first_name": first_name or "",
            "created_at": int(time.time()),
        })

def add_points(uid, amount):
    uid_s = str(uid)
    user = get_user(uid_s)
    if not user:
        create_user_if_missing(uid_s)
        user = get_user(uid_s)
    new_points = (user.get("points", 0) or 0) + amount
    users_ref.child(uid_s).update({"points": new_points})
    return new_points

def incr_referrals(uid, by=1):
    uid_s = str(uid)
    user = get_user(uid_s)
    if not user:
        create_user_if_missing(uid_s)
        user = get_user(uid_s)
    new_count = (user.get("referrals", 0) or 0) + by
    users_ref.child(uid_s).update({"referrals": new_count})
    return new_count

def build_referral_link(uid):
    # uses bot username (fetched lazily)
    try:
        username = bot.get_me().username
    except Exception:
        username = "YourBotUsername"
    return f"https://t.me/{username}?start={uid}"

def format_points_info(user_dict):
    points = user_dict.get("points", 0) or 0
    referrals = user_dict.get("referrals", 0) or 0
    return f"Points: <b>{points}</b>\nReferrals: <b>{referrals}</b>"

def seed_sample_tasks():
    """Create sample tasks if tasks list is empty. Id keys are strings."""
    existing = tasks_ref.get()
    if existing:
        return
    sample = {
        "task1": {
            "type": "visit",
            "title": "Visit Example Site",
            "description": "Open the link and view the page for a few seconds.",
            "url": "https://example.com",
            "points": POINTS_VISIT,
            "available": True
        },
        "task2": {
            "type": "join_channel",
            "title": "Join @SomePublicChannel",
            "description": "Join the channel listed and press 'I joined'.",
            "channel_username": "@SomePublicChannel",  # can be public channel username
            "points": POINTS_JOIN_CHANNEL,
            "available": True
        },
        "task3": {
            "type": "join_bot",
            "title": "Start @SomeOtherBot",
            "description": "Open the bot and press Start, then press 'Done'.",
            "bot_username": "@SomeOtherBot",
            "points": POINTS_JOIN_BOT,
            "available": True
        },
        "task4": {
            "type": "other",
            "title": "Twitter: Like a Post",
            "description": "Open the tweet and like it. Press 'Done'.",
            "url": "https://twitter.com/example/status/000",
            "points": POINTS_OTHER,
            "available": True
        }
    }
    tasks_ref.set(sample)
    logger.info("Seeded sample tasks.")


# ------------------ Bot Handlers ------------------

@bot.message_handler(commands=['start'])
def handle_start(message):
    args = message.text.split()
    user = message.from_user
    uid = str(user.id)
    username = user.username or ""
    first_name = user.first_name or ""
    create_user_if_missing(uid, username=username, first_name=first_name)

    # Referral logic
    if len(args) > 1:
        referrer_id = args[1]
        try:
            if referrer_id != uid:
                referrer = get_user(referrer_id)
                me = get_user(uid)
                # only credit if referrer exists and user has not been referred before
                if referrer and not me.get("referred_by"):
                    add_points(referrer_id, POINTS_FOR_REFERRAL)
                    incr_referrals(referrer_id, 1)
                    users_ref.child(uid).update({"referred_by": referrer_id})
                    # notify referrer
                    try:
                        bot.send_message(int(referrer_id),
                                         f"🎉 You got <b>{POINTS_FOR_REFERRAL}</b> points! @{username or first_name} joined with your link.")
                    except Exception:
                        logger.info("Could not notify referrer (dm may be blocked).")
        except Exception as e:
            logger.exception("Referral error: %s", e)

    # Build keyboard like the screenshot
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    markup.add(
        types.KeyboardButton("💻 Visit Sites"),
        types.KeyboardButton("📣 Join Channels"),
        types.KeyboardButton("🤖 Join Bots")
    )
    markup.add(
        types.KeyboardButton("😄 More"),
        types.KeyboardButton("💰 Balance"),
        types.KeyboardButton("🙌 Referrals")
    )
    markup.add(
        types.KeyboardButton("ℹ️ Info"),
    )
    # big advertise button (single)
    markup.add(types.KeyboardButton("📊 Advertise"))

    bot.send_message(message.chat.id,
                     f"Hi {first_name} 👋\n{format_points_info(get_user(uid))}\n\n"
                     f"Your referral link:\n{build_referral_link(uid)}\n\n"
                     "Share it and earn points!",
                     reply_markup=markup)

@bot.message_handler(commands=['help'])
def handle_help(message):
    bot.reply_to(message,
                 "Commands:\n/tasks - list tasks\n/points or press Balance - see balance\n/referrals - see referral info\n/advertise - create an ad\n/leaderboard - top referrers\n\nAdmins can use /addtask /removetask /addpoints /stats")

@bot.message_handler(commands=['tasks'])
def handle_tasks_cmd(message):
    show_tasks_to_user(message.chat.id, message.from_user.id)

@bot.message_handler(commands=['balance'])
def cmd_balance(message):
    uid = str(message.from_user.id)
    create_user_if_missing(uid)
    bot.reply_to(message, format_points_info(get_user(uid)))

@bot.message_handler(commands=['referrals'])
def cmd_referrals(message):
    uid = str(message.from_user.id)
    create_user_if_missing(uid)
    u = get_user(uid)
    ref_by = u.get("referred_by") or "—"
    bot.reply_to(message, f"{format_points_info(u)}\nReferred by: {ref_by}")

@bot.message_handler(commands=['leaderboard'])
def cmd_leaderboard(message):
    all_users = users_ref.get() or {}
    items = []
    for k,v in all_users.items():
        pts = v.get("points",0) or 0
        refs = v.get("referrals",0) or 0
        name = v.get("username") or v.get("first_name") or f"ID:{k}"
        items.append((k, refs, pts, name))
    items.sort(key=lambda x: (x[1], x[2]), reverse=True)
    top = items[:10]
    if not top:
        bot.reply_to(message, "No users yet.")
        return
    text = "<b>🏆 Top Referrers</b>\n\n"
    for i,(uid,refs,pts,name) in enumerate(top, start=1):
        display = f"@{name}" if not name.startswith("ID:") and not name.isdigit() else name
        text += f"{i}. {display} — {refs} refs — {pts} pts\n"
    bot.reply_to(message, text)

# Quick UI button handler (keyboard presses)
@bot.message_handler(func=lambda m: True, content_types=['text'])
def ui_buttons(message):
    txt = message.text.strip().lower()
    if txt in ("💻 visit sites", "visit sites", "visit"):
        show_tasks_filtered(message.chat.id, message.from_user.id, task_type="visit")
    elif txt in ("📣 join channels", "join channels", "channels"):
        show_tasks_filtered(message.chat.id, message.from_user.id, task_type="join_channel")
    elif txt in ("🤖 join bots", "join bots", "bots"):
        show_tasks_filtered(message.chat.id, message.from_user.id, task_type="join_bot")
    elif txt in ("😄 more", "more"):
        show_tasks_filtered(message.chat.id, message.from_user.id, task_type="other")
    elif txt in ("💰 balance", "balance", "/points", "/balance"):
        create_user_if_missing(str(message.from_user.id))
        bot.reply_to(message, format_points_info(get_user(str(message.from_user.id))))
    elif txt in ("🙌 referrals", "referrals", "/referrals"):
        cmd_referrals(message)
    elif txt in ("ℹ️ info", "info"):
        bot.reply_to(message, "This bot gives points for completing tasks. Use /tasks to list everything. Advertise to spend points.")
    elif txt in ("📊 advertise", "advertise"):
        start_ad_flow(message)
    else:
        bot.reply_to(message, "Use the keyboard or /tasks /balance /referrals /advertise")

# ---------------- Task listing & claiming ----------------

def show_tasks_to_user(chat_id, user_id):
    all_tasks = tasks_ref.get() or {}
    if not all_tasks:
        bot.send_message(chat_id, "No tasks available right now.")
        return
    text = "<b>Available Tasks</b>\n\n"
    for tid, t in all_tasks.items():
        if not t.get("available", True):
            continue
        text += f"• <b>{t.get('title')}</b> — {t.get('points')} pts\n  {t.get('description')}\n\n"
    text += "Tap a task button below to start one."
    # Provide inline keyboard with task buttons
    markup = types.InlineKeyboardMarkup()
    for tid,t in all_tasks.items():
        if not t.get("available", True):
            continue
        btn = types.InlineKeyboardButton(f"{t.get('title')} — {t.get('points')} pts", callback_data=f"task_open:{tid}")
        markup.add(btn)
    bot.send_message(chat_id, text, reply_markup=markup)

def show_tasks_filtered(chat_id, user_id, task_type=None):
    all_tasks = tasks_ref.get() or {}
    found = False
    markup = types.InlineKeyboardMarkup()
    text = f"<b>Tasks — {task_type or 'All'}</b>\n\n"
    for tid, t in all_tasks.items():
        if not t.get("available", True):
            continue
        if task_type and t.get("type") != task_type:
            continue
        found = True
        text += f"• <b>{t.get('title')}</b> — {t.get('points')} pts\n  {t.get('description')}\n\n"
        markup.add(types.InlineKeyboardButton(f"{t.get('title')} — {t.get('points')} pts", callback_data=f"task_open:{tid}"))
    if not found:
        bot.send_message(chat_id, "No tasks of this type are available right now.")
        return
    bot.send_message(chat_id, text, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("task_open:"))
def callback_task_open(call):
    task_id = call.data.split(":",1)[1]
    t = tasks_ref.child(task_id).get()
    if not t:
        bot.answer_callback_query(call.id, "Task not found.")
        return
    # Build specific UI depending on type
    ttype = t.get("type")
    text = f"<b>{t.get('title')}</b>\n\n{t.get('description')}\n\nReward: <b>{t.get('points')}</b> pts"
    markup = types.InlineKeyboardMarkup()
    # For types with URL we add a URL button
    if ttype in ("visit","other") and t.get("url"):
        markup.add(types.InlineKeyboardButton("Open Link", url=t.get("url")))
        markup.add(types.InlineKeyboardButton("I Visited ✅", callback_data=f"task_done:{task_id}"))
    elif ttype == "join_channel":
        # channel username or invite link
        ch = t.get("channel_username") or t.get("url")
        if ch:
            # URL version when looks like @username -> t.me/username
            url = ch if ch.startswith("http") else f"https://t.me/{ch.lstrip('@')}"
            markup.add(types.InlineKeyboardButton("Open Channel", url=url))
        markup.add(types.InlineKeyboardButton("I joined ✅", callback_data=f"task_done:{task_id}"))
    elif ttype == "join_bot":
        botname = t.get("bot_username") or t.get("url")
        if botname:
            url = botname if botname.startswith("http") else f"https://t.me/{botname.lstrip('@')}"
            markup.add(types.InlineKeyboardButton("Open Bot", url=url))
        markup.add(types.InlineKeyboardButton("Done ✅", callback_data=f"task_done:{task_id}"))
    else:
        # fallback
        markup.add(types.InlineKeyboardButton("Open Link", url=t.get("url","https://example.com")))
        markup.add(types.InlineKeyboardButton("Done ✅", callback_data=f"task_done:{task_id}"))

    bot.send_message(call.message.chat.id, text, reply_markup=markup)
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("task_done:"))
def callback_task_done(call):
    data = call.data.split(":",1)[1]
    tid = data
    user = call.from_user
    uid = str(user.id)

    t = tasks_ref.child(tid).get()
    if not t:
        bot.answer_callback_query(call.id, "Task not found.")
        return

    # Ensure user and completion structure
    create_user_if_missing(uid, username=user.username or "", first_name=user.first_name or "")
    user_completions = completions_ref.child(uid).get() or {}

    # Prevent double-completion of the same task
    if user_completions.get(tid):
        bot.answer_callback_query(call.id, "You already completed this task.")
        return

    # Attempt automated verification for join_channel tasks by checking membership
    verified = False
    if t.get("type") == "join_channel":
        # try to check membership if channel username provided and bot can access
        ch = t.get("channel_username")
        if ch:
            try:
                ch_id = ch.lstrip('@')
                chat_member = bot.get_chat_member(chat_id=ch_id, user_id=int(uid))
                # if status is not 'left' then member
                status = getattr(chat_member, 'status', None)
                if status and status not in ("left", "kicked"):
                    verified = True
            except Exception as ex:
                # cannot verify (private channel or bot not admin). fallback to manual confirm.
                logger.info("Could not verify membership automatically: %s", ex)

    # If other types, we cannot automatically verify visits or bot starts reliably.
    # So record as completed and award points (this is the usual approach).

    # Record completion and award points
    completions_ref.child(uid).child(tid).set({
        "task_id": tid,
        "title": t.get("title"),
        "points": t.get("points"),
        "time": int(time.time()),
        "verified": bool(verified)
    })
    add_points(uid, int(t.get("points", 0) or 0))

    # Increment global counters if you want (optional)
    # Optionally, mark task unavailable if single-use: tasks_ref.child(tid).update({"available": False})

    # Notify user
    bot.answer_callback_query(call.id, f"Task completed! You earned {t.get('points')} pts.")
    bot.send_message(call.message.chat.id, f"✅ Task completed!\nYou received <b>{t.get('points')}</b> points.\n{format_points_info(get_user(uid))}")

# ---------------- Advertise flow (simple) ----------------

def start_ad_flow(message_or_call):
    # accept both message and callback-like objects
    if isinstance(message_or_call, types.Message):
        chat_id = message_or_call.chat.id
        user = message_or_call.from_user
    else:
        chat_id = message_or_call.message.chat.id
        user = message_or_call.from_user

    uid = str(user.id)
    create_user_if_missing(uid)

    # Ask for ad text and cost (simple linear cost: 1 pt per display)
    msg = bot.send_message(chat_id, "📣 Create an advertisement.\nSend the ad text you want to publish (plain text).")
    bot.register_next_step_handler(msg, process_ad_text)

def process_ad_text(message):
    text = message.text.strip()
    if not text:
        bot.reply_to(message, "Ad text cannot be empty. Try /advertise again.")
        return
    # simple pricing: length-based cost (example)
    cost = max(10, min(500, len(text)))  # example: min 10 pts, max 500 pts
    confirm = bot.send_message(message.chat.id, f"Your ad:\n\n{text}\n\nCost: <b>{cost}</b> pts\n\nSend 'confirm' to pay and publish or 'cancel'.")
    # store temporary payload in db under ads_pending/<user_id>
    ads_ref.child("pending").child(str(message.from_user.id)).set({
        "text": text,
        "cost": cost,
        "time": int(time.time())
    })
    bot.register_next_step_handler(confirm, finalize_ad_payment)

def finalize_ad_payment(message):
    txt = message.text.strip().lower()
    uid = str(message.from_user.id)
    pending = ads_ref.child("pending").child(uid).get()
    if not pending:
        bot.reply_to(message, "No pending ad. Start with /advertise.")
        return
    if txt == "confirm":
        user = get_user(uid)
        points = user.get("points", 0) or 0
        cost = pending.get("cost", 0)
        if points < cost:
            bot.reply_to(message, f"Not enough points (You have {points}, need {cost}).")
            ads_ref.child("pending").child(uid).delete()
            return
        # Deduct and publish ad to ads list
        new_points = points - cost
        users_ref.child(uid).update({"points": new_points})
        ad_id = f"ad_{int(time.time())}_{uid}"
        ads_ref.child("published").child(ad_id).set({
            "owner": uid,
            "text": pending.get("text"),
            "cost": cost,
            "time": int(time.time())
        })
        ads_ref.child("pending").child(uid).delete()
        bot.reply_to(message, f"✅ Ad published! {cost} pts deducted.\n{format_points_info(get_user(uid))}")
        # In production you would distribute ads (e.g., show to users via broadcast or attach to tasks)
    else:
        ads_ref.child("pending").child(uid).delete()
        bot.reply_to(message, "Ad creation canceled.")

# ---------------- Admin: add/remove tasks & misc ----------------

@bot.message_handler(commands=['addtask'])
@require_admin
def cmd_addtask(message):
    # Expect a simple payload after command or ask step-by-step.
    # Format (single-line): /addtask <taskid>|<type>|<title>|<points>|<description>|<url_or_username>
    parts = message.text.split(" ",1)
    if len(parts) == 1:
        bot.reply_to(message, "Usage: /addtask <taskid>|<type>|<title>|<points>|<description>|<url_or_username>\nExample: /addtask task10|visit|Visit Site|3|Open example|https://example.com")
        return
    payload = parts[1]
    try:
        tid, ttype, title, pts, desc, link = payload.split("|",5)
    except Exception:
        bot.reply_to(message, "Invalid format. See usage.")
        return
    task_obj = {
        "type": ttype.strip(),
        "title": title.strip(),
        "description": desc.strip(),
        "points": int(pts),
        "available": True
    }
    if ttype.strip() in ("visit","other"):
        task_obj["url"] = link.strip()
    elif ttype.strip() == "join_channel":
        task_obj["channel_username"] = link.strip()
    elif ttype.strip() == "join_bot":
        task_obj["bot_username"] = link.strip()
    tasks_ref.child(tid.strip()).set(task_obj)
    bot.reply_to(message, f"Task {tid} added.")

@bot.message_handler(commands=['removetask'])
@require_admin
def cmd_removetask(message):
    parts = message.text.split()
    if len(parts) != 2:
        bot.reply_to(message, "Usage: /removetask <taskid>")
        return
    tid = parts[1]
    tasks_ref.child(tid).delete()
    bot.reply_to(message, f"Task {tid} removed.")

@bot.message_handler(commands=['addpoints'])
@require_admin
def cmd_addpoints(message):
    parts = message.text.split()
    if len(parts) != 3:
        bot.reply_to(message, "Usage: /addpoints <user_id> <amount>")
        return
    target, amt = parts[1], parts[2]
    try:
        amt = int(amt)
    except:
        bot.reply_to(message, "Amount must be integer.")
        return
    create_user_if_missing(target)
    new = add_points(target, amt)
    bot.reply_to(message, f"Added {amt} pts to {target}. New: {new}")

@bot.message_handler(commands=['stats'])
@require_admin
def cmd_stats(message):
    all_users = users_ref.get() or {}
    total_users = len(all_users)
    total_points = sum((u.get("points",0) or 0) for u in all_users.values())
    total_tasks = len(tasks_ref.get() or {})
    bot.reply_to(message, f"Users: {total_users}\nTotal points: {total_points}\nTasks: {total_tasks}")

# ---------------- Startup ----------------

if __name__ == "__main__":
    seed_sample_tasks()
    print("Referral & Tasks bot starting...")
    bot.infinity_polling(timeout=60, long_polling_timeout=60)
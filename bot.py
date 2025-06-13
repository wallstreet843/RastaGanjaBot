import logging
import json
import os
import time
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

# === CONFIG ===
TOKEN = "8114412706:AAFPevBwjZNlfhrFmVIsyXjz7K-xosMYAz0"  # Replace this
ADMIN_IDS = [7550000963]  # Replace with your Telegram user ID(s)
DATA_FILE = "hit_data.json"
BACKUP_FILE = "hit_data_backup.json"
GROUP_DATA_FILE = "group_data.json"
COOLDOWN_SECONDS = 15  # Seconds between hits per user
DAILY_RESET_HOUR = 0  # Hour when daily stats reset (0-23)

# === LOGGING ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === ACHIEVEMENTS ===
ACHIEVEMENTS = {
    "first_hit": {"name": "🌱 First Timer", "desc": "Take your first hit", "requirement": 1},
    "regular": {"name": "🔥 Regular pothead", "desc": "Reach 10 hits", "requirement": 10},
    "veteran": {"name": "💨 Veteran", "desc": "Reach 50 hits", "requirement": 50},
    "legend": {"name": "👑 Smoke Legend", "desc": "Reach 100 hits", "requirement": 100},
    "master": {"name": "🧙‍♂️ Master smoker", "desc": "Reach 250 hits", "requirement": 250},
    "godlike": {"name": "🛸 Godlike", "desc": "Reach 500 hits", "requirement": 500},
    "daily_streak_3": {"name": "📅 Consistent", "desc": "3-day streak", "requirement": 3},
    "daily_streak_7": {"name": "🗓️ Dedicated", "desc": "7-day streak", "requirement": 7},
    "daily_streak_30": {"name": "📆 Committed", "desc": "30-day streak", "requirement": 30},
    "speed_demon": {"name": "⚡ Speed Demon", "desc": "Take 10 hits in one hour", "requirement": 10},
    "group_leader": {"name": "👥 Group Leader", "desc": "#1 smoker in the group", "requirement": 1},
    "social_smoker": {"name": "🎭 Social Smoker", "desc": "Hit in 5 different groups", "requirement": 5}
}

# === DATA STORAGE ===
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.error("Corrupted data file, loading backup...")
            return load_backup()
    return {}

def load_group_data():
    if os.path.exists(GROUP_DATA_FILE):
        try:
            with open(GROUP_DATA_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.error("Corrupted group data file...")
    return {}

def load_backup():
    if os.path.exists(BACKUP_FILE):
        try:
            with open(BACKUP_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.error("Backup also corrupted, starting fresh...")
    return {}

def save_data(data):
    # Create backup before saving
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                backup_data = json.load(f)
            with open(BACKUP_FILE, "w") as f:
                json.dump(backup_data, f)
        except:
            pass
    
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def save_group_data(data):
    with open(GROUP_DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_user_entry(user_id, name):
    user_id = str(user_id)
    if user_id not in user_data:
        user_data[user_id] = {
            "name": name,
            "hits": 0,
            "last_hit": 0,
            "daily_hits": 0,
            "daily_date": "",
            "streak": 0,
            "best_streak": 0,
            "achievements": [],
            "join_date": datetime.now().isoformat(),
            "hourly_hits": [],
            "total_sessions": 0,
            "favorite_time": {},
            "groups_participated": []
        }
    else:
        user_data[user_id]["name"] = name  # Update name
    return user_data[user_id]

def get_group_entry(chat_id, chat_title):
    chat_id = str(chat_id)
    if chat_id not in group_data:
        group_data[chat_id] = {
            "title": chat_title,
            "total_hits": 0,
            "members": {},
            "daily_hits": 0,
            "daily_date": "",
            "created_date": datetime.now().isoformat(),
            "last_activity": time.time()
        }
    else:
        group_data[chat_id]["title"] = chat_title  # Update title
        group_data[chat_id]["last_activity"] = time.time()
    return group_data[chat_id]

def update_group_member(chat_id, user_id, name, hits_added=1):
    chat_id = str(chat_id)
    user_id = str(user_id)
    
    if chat_id in group_data:
        if "members" not in group_data[chat_id]:
            group_data[chat_id]["members"] = {}
        
        if user_id not in group_data[chat_id]["members"]:
            group_data[chat_id]["members"][user_id] = {
                "name": name,
                "hits": 0,
                "daily_hits": 0,
                "daily_date": "",
                "join_date": datetime.now().isoformat()
            }
        
        member = group_data[chat_id]["members"][user_id]
        member["name"] = name
        member["hits"] += hits_added
        
        # Check daily reset for group member
        today = datetime.now().strftime("%Y-%m-%d")
        if member["daily_date"] != today:
            member["daily_hits"] = 0
            member["daily_date"] = today
        member["daily_hits"] += hits_added
        
        # Update group totals
        group_data[chat_id]["total_hits"] += hits_added
        if group_data[chat_id]["daily_date"] != today:
            group_data[chat_id]["daily_hits"] = 0
            group_data[chat_id]["daily_date"] = today
        group_data[chat_id]["daily_hits"] += hits_added

def check_daily_reset(entry):
    today = datetime.now().strftime("%Y-%m-%d")
    if entry["daily_date"] != today:
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        if entry["daily_date"] == yesterday and entry["daily_hits"] > 0:
            entry["streak"] += 1
            entry["best_streak"] = max(entry["best_streak"], entry["streak"])
        elif entry["daily_date"] != yesterday:
            entry["streak"] = 1 if entry["daily_hits"] > 0 else 0
        
        entry["daily_hits"] = 0
        entry["daily_date"] = today

def check_achievements(user_id, entry, chat_id=None):
    new_achievements = []
    
    # Hit-based achievements
    for ach_id, ach in ACHIEVEMENTS.items():
        if ach_id not in entry["achievements"]:
            if ach_id.startswith("daily_streak_"):
                if entry["streak"] >= ach["requirement"]:
                    entry["achievements"].append(ach_id)
                    new_achievements.append(ach)
            elif ach_id == "speed_demon":
                # Check if user took 10 hits in last hour
                now = time.time()
                recent_hits = [h for h in entry.get("hourly_hits", []) if now - h < 3600]
                if len(recent_hits) >= 10:
                    entry["achievements"].append(ach_id)
                    new_achievements.append(ach)
            elif ach_id == "group_leader":
                # Check if user is #1 in any group
                if chat_id and str(chat_id) in group_data:
                    group = group_data[str(chat_id)]
                    if "members" in group and group["members"]:
                        top_member = max(group["members"].items(), key=lambda x: x[1]["hits"])
                        if top_member[0] == str(user_id):
                            entry["achievements"].append(ach_id)
                            new_achievements.append(ach)
            elif ach_id == "social_smoker":
                # Check if user participated in 5+ groups
                if len(entry.get("groups_participated", [])) >= 5:
                    entry["achievements"].append(ach_id)
                    new_achievements.append(ach)
            else:
                if entry["hits"] >= ach["requirement"]:
                    entry["achievements"].append(ach_id)
                    new_achievements.append(ach)
    
    return new_achievements

def is_group_chat(update: Update):
    """Check if the message is from a group chat"""
    return update.effective_chat.type in ['group', 'supergroup']

def is_private_chat(update: Update):
    """Check if the message is from a private chat"""
    return update.effective_chat.type == 'private'

user_data = load_data()
group_data = load_group_data()

# === COMMANDS ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_group_chat(update):
        # Group welcome message
        chat_title = update.effective_chat.title
        keyboard = [
            [InlineKeyboardButton("🌬️ Take a Hit", callback_data="hit")],
            [InlineKeyboardButton("🏆 Group Leaderboard", callback_data="groupboard"),
             InlineKeyboardButton("📊 My Stats", callback_data="stats")],
            [InlineKeyboardButton("🎯 Achievements", callback_data="achievements"),
             InlineKeyboardButton("❓ Help", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🌿 Rasta Ganja Bot is now active in {chat_title}! 🌿\n\n"
            "🔥 Everyone can take hits and compete!\n"
            "💨 Build your group's leaderboard!\n"
            "📈 Track individual and group progress!\n\n"
            "Wanna Grow some bud? try @Ganja_Grow_Bot",
            reply_markup=reply_markup
        )
    else:
        # Private chat welcome message
        keyboard = [
            [InlineKeyboardButton("🌬️ Take a Hit", callback_data="hit")],
            [InlineKeyboardButton("📊 My Stats", callback_data="stats"), 
             InlineKeyboardButton("🏆 Global Leaderboard", callback_data="highscore")],
            [InlineKeyboardButton("🎯 Achievements", callback_data="achievements"),
             InlineKeyboardButton("❓ Help", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "🌿 Welcome to Rasta Ganja Bot! Wa Gwan! 🌿\n\n"
            "🔥 Take hits, get high, unlock achievements!\n"
            "💨 Compete globally and in groups!\n"
            "📈 Track your progress and statistics!\n\n"
            "Add me to groups to compete with friends, Lets Get High!\n"
            "Wanna grow some bud? try @Ganja_Grow_Bot:",
            reply_markup=reply_markup
        )

async def hit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /hit command"""
    await process_hit(update, context, update.message)

async def process_hit(update: Update, context: ContextTypes.DEFAULT_TYPE, message):
    """Process hit logic for both command and button"""
    user = update.effective_user
    user_id = str(user.id)
    name = user.first_name
    chat_id = update.effective_chat.id

    now = time.time()
    entry = get_user_entry(user_id, name)
    check_daily_reset(entry)

    if now - entry["last_hit"] < COOLDOWN_SECONDS:
        remaining = int(COOLDOWN_SECONDS - (now - entry["last_hit"]))
        await message.reply_text(f"⏳ Take it easy Bro! Wait {remaining}s before your next hit.")
        return

    # Update stats
    entry["hits"] += 1
    entry["daily_hits"] += 1
    entry["last_hit"] = now
    entry["total_sessions"] += 1
    
    # Track group participation
    if is_group_chat(update):
        chat_title = update.effective_chat.title
        group_entry = get_group_entry(chat_id, chat_title)
        update_group_member(chat_id, user_id, name)
        
        # Track groups participated
        if "groups_participated" not in entry:
            entry["groups_participated"] = []
        if str(chat_id) not in entry["groups_participated"]:
            entry["groups_participated"].append(str(chat_id))
    
    # Track hourly hits for speed demon achievement
    if "hourly_hits" not in entry:
        entry["hourly_hits"] = []
    entry["hourly_hits"].append(now)
    entry["hourly_hits"] = [h for h in entry["hourly_hits"] if now - h < 3600]  # Keep only last hour
    
    # Track favorite time
    hour = datetime.now().hour
    if not entry["favorite_time"]:
        entry["favorite_time"] = {}
    entry["favorite_time"][str(hour)] = entry["favorite_time"].get(str(hour), 0) + 1

    user_data[user_id] = entry
    save_data(user_data)
    
    if is_group_chat(update):
        save_group_data(group_data)

    # Check for new achievements
    new_achievements = check_achievements(user_id, entry, chat_id if is_group_chat(update) else None)

    # Generate response
    emojis = ["💨", "🔥", "😵", "🚬", "🛸", "👽", "😶‍🌫️", "🌈", "🧠", "☁️", "🌪️", "⭐"]
    level = entry["hits"]
    emoji = random.choice(emojis)

    if is_group_chat(update):
        # Group-specific messages
        group_entry = group_data[str(chat_id)]
        group_rank = 1
        if "members" in group_entry and len(group_entry["members"]) > 1:
            sorted_members = sorted(group_entry["members"].items(), key=lambda x: x[1]["hits"], reverse=True)
            group_rank = next((i+1 for i, (uid, _) in enumerate(sorted_members) if uid == user_id), 1)
        
        messages = [
            f"{emoji} {name} took a hit! Level {level} (#{group_rank} in group)",
            f"{emoji} {name} is getting higher... Hit #{level} in {update.effective_chat.title}!",
            f"{emoji} Another one for {name}! Group rank: #{group_rank}",
            f"{emoji} {name} reached level {level}! 🏆 Group total: {group_entry['total_hits']}"
        ]
    else:
        # Private chat messages
        messages = [
            f"{emoji} {name} took a massive hit and is floating at level {level}! Hungry yet?",
            f"{emoji} {name} puffed again... that's hit #{level}!",
            f"{emoji} Another one for {name}. Level {level} high now!",
            f"{emoji} {name} is climbing the clouds... level {level} ☁️"
        ]

    response = random.choice(messages)
    
    if entry["daily_hits"] == 1:
        response += f"\n🌅 First hit of the day! Wake & Bake! Current streak: {entry['streak']} days"
    
    if new_achievements:
        response += "\n\n🎉 NEW ACHIEVEMENT(S) UNLOCKED! 🎉\n"
        for ach in new_achievements:
            response += f"{ach['name']}: {ach['desc']}\n"

    await message.reply_text(response)

async def groupboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /groupboard command"""
    await process_groupboard(update, context, update.message)

async def process_groupboard(update: Update, context: ContextTypes.DEFAULT_TYPE, message):
    """Process group leaderboard"""
    if not is_group_chat(update):
        await message.reply_text("🚫 This command only works in groups! Use /highscore for global rankings.")
        return
    
    chat_id = str(update.effective_chat.id)
    chat_title = update.effective_chat.title
    
    if chat_id not in group_data or "members" not in group_data[chat_id]:
        await message.reply_text("🚫 No hits recorded in this group yet!")
        return
    
    members = group_data[chat_id]["members"]
    sorted_members = sorted(members.items(), key=lambda x: x[1]["hits"], reverse=True)[:10]
    
    text = f"🏆 {chat_title} Leaderboard 🏆\n\n"
    medals = ["🥇", "🥈", "🥉"]
    
    for i, (uid, member_info) in enumerate(sorted_members, 1):
        medal = medals[i-1] if i <= 3 else f"{i}."
        daily_info = f" (Today: {member_info.get('daily_hits', 0)})" if member_info.get('daily_hits', 0) > 0 else ""
        text += f"{medal} {member_info['name']} — {member_info['hits']} hits{daily_info}\n"
    
    group_info = group_data[chat_id]
    text += f"\n📊 Group Stats:\n"
    text += f"💨 Total Group Hits: {group_info['total_hits']}\n"
    text += f"📅 Today's Group Hits: {group_info.get('daily_hits', 0)}\n"
    text += f"👥 Active Members: {len(members)}"
    
    keyboard = [
        [InlineKeyboardButton("📅 Daily Group Board", callback_data="dailygroup")],
        [InlineKeyboardButton("🌍 Global Leaderboard", callback_data="highscore")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await message.reply_text(text, reply_markup=reply_markup)

async def dailygroup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /dailygroup command"""
    await process_dailygroup(update, context, update.message)

async def process_dailygroup(update: Update, context: ContextTypes.DEFAULT_TYPE, message):
    """Process daily group leaderboard"""
    if not is_group_chat(update):
        await message.reply_text("🚫 This command only works in groups!")
        return
    
    chat_id = str(update.effective_chat.id)
    chat_title = update.effective_chat.title
    today = datetime.now().strftime("%Y-%m-%d")
    
    if chat_id not in group_data or "members" not in group_data[chat_id]:
        await message.reply_text("🚫 No hits recorded in this group yet!")
        return
    
    members = group_data[chat_id]["members"]
    daily_members = [(uid, info) for uid, info in members.items() 
                    if info.get("daily_date") == today and info.get("daily_hits", 0) > 0]
    
    if not daily_members:
        await message.reply_text("📅 No hits recorded in this group today yet!")
        return
    
    sorted_daily = sorted(daily_members, key=lambda x: x[1]["daily_hits"], reverse=True)[:10]
    
    text = f"📅 {chat_title} Daily Board ({today})\n\n"
    for i, (uid, member_info) in enumerate(sorted_daily, 1):
        text += f"{i}. {member_info['name']} — {member_info['daily_hits']} hits today\n"
    
    await message.reply_text(text)

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command"""
    await process_stats(update, context, update.message)

async def process_stats(update: Update, context: ContextTypes.DEFAULT_TYPE, message):
    """Process stats logic for both command and button"""
    user_id = str(update.effective_user.id)
    name = update.effective_user.first_name
    
    if user_id not in user_data:
        await message.reply_text("🚫 No data found. Take your first hit with /hit!")
        return
    
    entry = user_data[user_id]
    check_daily_reset(entry)
    
    # Calculate favorite time
    fav_time = "Not enough data"
    if entry.get("favorite_time"):
        fav_hour = max(entry["favorite_time"], key=entry["favorite_time"].get)
        fav_time = f"{fav_hour}:00-{int(fav_hour)+1}:00"
    
    # Calculate global rank
    sorted_users = sorted(user_data.items(), key=lambda x: x[1]["hits"], reverse=True)
    global_rank = next((i+1 for i, (uid, _) in enumerate(sorted_users) if uid == user_id), "N/A")
    
    # Calculate group rank if in group
    group_rank = "N/A"
    if is_group_chat(update):
        chat_id = str(update.effective_chat.id)
        if chat_id in group_data and "members" in group_data[chat_id]:
            sorted_members = sorted(group_data[chat_id]["members"].items(), 
                                  key=lambda x: x[1]["hits"], reverse=True)
            group_rank = next((i+1 for i, (uid, _) in enumerate(sorted_members) if uid == user_id), "N/A")
    
    join_date = entry.get("join_date", "Unknown")
    if join_date != "Unknown":
        try:
            join_date = datetime.fromisoformat(join_date).strftime("%Y-%m-%d")
        except:
            join_date = "Unknown"
    
    stats_text = f"📊 {name}'s Statistics 📊\n\n"
    stats_text += f"🔥 Total Hits: {entry['hits']}\n"
    stats_text += f"📅 Daily Hits: {entry['daily_hits']}\n"
    stats_text += f"⚡ Current Streak: {entry['streak']} days\n"
    stats_text += f"🏆 Best Streak: {entry['best_streak']} days\n"
    stats_text += f"🌍 Global Rank: #{global_rank}\n"
    
    if is_group_chat(update):
        stats_text += f"👥 Group Rank: #{group_rank}\n"
    
    stats_text += f"🎯 Achievements: {len(entry['achievements'])}/{len(ACHIEVEMENTS)}\n"
    stats_text += f"📱 Total Sessions: {entry['total_sessions']}\n"
    stats_text += f"🕐 Favorite Time: {fav_time}\n"
    stats_text += f"👥 Groups Joined: {len(entry.get('groups_participated', []))}\n"
    stats_text += f"📆 Member Since: {join_date}\n\n"
    stats_text += "💨 Keep hitting to climb the ranks, Smoke up!"

    keyboard = []
    if is_group_chat(update):
        keyboard.append([InlineKeyboardButton("🏆 Group Board", callback_data="groupboard")])
    keyboard.append([InlineKeyboardButton("🎯 View Achievements", callback_data="achievements")])
    keyboard.append([InlineKeyboardButton("🌍 Global Board", callback_data="highscore")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(stats_text, reply_markup=reply_markup)

async def achievements_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /achievements command"""
    await process_achievements(update, context, update.message)

async def process_achievements(update: Update, context: ContextTypes.DEFAULT_TYPE, message):
    """Process achievements logic for both command and button"""
    user_id = str(update.effective_user.id)
    name = update.effective_user.first_name
    
    if user_id not in user_data:
        await message.reply_text("🚫 No data found. Take your first hit with /hit!")
        return
    
    entry = user_data[user_id]
    user_achievements = entry.get("achievements", [])
    
    text = f"🎯 {name}'s Achievements ({len(user_achievements)}/{len(ACHIEVEMENTS)})\n\n"
    
    for ach_id, ach in ACHIEVEMENTS.items():
        if ach_id in user_achievements:
            text += f"✅ {ach['name']}: {ach['desc']}\n"
        else:
            text += f"⬜ {ach['name']}: {ach['desc']}\n"
    
    await message.reply_text(text)

async def highscore_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /highscore command"""
    await process_highscore(update, context, update.message)

async def process_highscore(update: Update, context: ContextTypes.DEFAULT_TYPE, message):
    """Process highscore logic for both command and button"""
    top = sorted(user_data.items(), key=lambda x: x[1]["hits"], reverse=True)[:15]
    if not top:
        await message.reply_text("🚫 No highs recorded yet.")
        return

    text = "🌍 Global Top 15 Highest 🌍\n\n"
    medals = ["🥇", "🥈", "🥉"]
    
    for i, (uid, info) in enumerate(top, 1):
        medal = medals[i-1] if i <= 3 else f"{i}."
        streak_info = f" 🔥{info.get('streak', 0)}" if info.get('streak', 0) > 0 else ""
        text += f"{medal} {info['name']} — {info['hits']} hits{streak_info}\n"
    
    keyboard = []
    if is_group_chat(update):
        keyboard.append([InlineKeyboardButton("👥 Group Board", callback_data="groupboard")])
    keyboard.append([InlineKeyboardButton("📅 Daily Global", callback_data="daily")])
    keyboard.append([InlineKeyboardButton("📊 My Stats", callback_data="stats")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(text, reply_markup=reply_markup)

async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /daily command"""
    await process_daily(update, context, update.message)

async def process_daily(update: Update, context: ContextTypes.DEFAULT_TYPE, message):
    """Process daily logic for both command and button"""
    today = datetime.now().strftime("%Y-%m-%d")
    daily_stats = {}
    
    for uid, entry in user_data.items():
        if entry.get("daily_date") == today and entry.get("daily_hits", 0) > 0:
            daily_stats[uid] = entry
    
    if not daily_stats:
        await message.reply_text("📅 No hits recorded globally today yet!")
        return
    
    sorted_daily = sorted(daily_stats.items(), key=lambda x: x[1]["daily_hits"], reverse=True)
    
    text = f"📅 Global Daily Leaderboard ({today})\n\n"
    for i, (uid, entry) in enumerate(sorted_daily[:10], 1):
        streak_emoji = "🔥" if entry["streak"] > 0 else ""
        text += f"{i}. {entry['name']} — {entry['daily_hits']} hits {streak_emoji}\n"
    
    await message.reply_text(text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    await process_help(update, context, update.message)

async def process_help(update: Update, context: ContextTypes.DEFAULT_TYPE, message):
    """Process help logic for both command and button"""
    if is_group_chat(update):
        help_text = """🌿 Ganja Bot Group Commands 🌿

**Basic Commands:**
/hit - Take a hit (15s cooldown)
/stats - View your detailed statistics
/mylevel - Quick level check
/achievements - View your achievements

**Group Leaderboards:**
/groupboard - This group's leaderboard
/dailygroup - Today's group leaderboard
/highscore - Global leaderboard
/daily - Global daily leaderboard

**Features:**
🔥 Group competitions and rankings
🎯 Individual achievements system
📊 Detailed group and personal stats
🏆 Multiple leaderboards (group & global)
💨 Interactive buttons and menus

**Group Benefits:**
👥 Compete with group members
📈 Track group progress
🏆 Group-specific achievements
🎭 Social smoking experience

Type /start to see the main menu!"""
    else:
        help_text = """🌿 Ganja Bot Commands 🌿

**Basic Commands:**
/hit - Take a hit (15s cooldown)
/stats - View your detailed statistics
/mylevel - Quick level check
/achievements - View your achievements

**Leaderboards:**
/highscore - Global leaderboard
/daily - Global daily leaderboard

**Group Features:**
Add me to groups to compete with friends!
- Group leaderboards
- Group achievements
- Social competitions

**Admin Commands:**
/resetleaderboard - Reset all data (admin only)
/backup - Create data backup (admin only)

**Features:**
🔥 Daily streaks and challenges
🎯 Achievement system with rewards
📊 Detailed statistics tracking
🏆 Multiple leaderboards
💨 Interactive buttons and menus
👥 Group competitions

Type /start to see the main menu!"""
    
    await message.reply_text(help_text)

async def mylevel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    name = update.effective_user.first_name
    
    if user_id not in user_data:
        await update.message.reply_text("🚫 No data found. Take your first hit with /hit!")
        return
    
    entry = user_data[user_id]
    hits = entry["hits"]
    daily = entry.get("daily_hits", 0)
    streak = entry.get("streak", 0)
    
    response = f"🧠 {name}, you're level {hits} high!\n"
    response += f"📅 Today: {daily} hits\n"
    response += f"🔥 Streak: {streak} days"
    
    if is_group_chat(update):
        chat_id = str(update.effective_chat.id)
        if chat_id in group_data and "members" in group_data[chat_id]:
            sorted_members = sorted(group_data[chat_id]["members"].items(), 
                                  key=lambda x: x[1]["hits"], reverse=True)
            group_rank = next((i+1 for i, (uid, _) in enumerate(sorted_members) if uid == user_id), "N/A")
            response += f"\n👥 Group Rank: #{group_rank}"
    
    await update.message.reply_text(response)

async def reset_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("🚫 You're not allowed to reset the leaderboard.")
        return

    # Create backup before reset
    backup_data = {"users": user_data.copy(), "groups": group_data.copy()}
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"reset_backup_{timestamp}.json"
    
    with open(backup_filename, "w") as f:
        json.dump(backup_data, f, indent=2)

    user_data.clear()
    group_data.clear()
    save_data(user_data)
    save_group_data(group_data)
    await update.message.reply_text(f"🧹 All leaderboards have been reset!\n📁 Backup saved as: {backup_filename}")

async def backup_data_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("🚫 Admin only command.")
        return
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"manual_backup_{timestamp}.json"
    
    backup_data = {"users": user_data, "groups": group_data}
    with open(backup_filename, "w") as f:
        json.dump(backup_data, f, indent=2)
    
    total_users = len(user_data)
    total_groups = len(group_data)
    total_hits = sum(entry["hits"] for entry in user_data.values())
    
    await update.message.reply_text(
        f"💾 Backup created: {backup_filename}\n"
        f"👥 Users: {total_users}\n"
        f"🏘️ Groups: {total_groups}\n"
        f"💨 Total Hits: {total_hits}"
    )

# === CALLBACK HANDLERS ===
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all button callbacks"""
    query = update.callback_query
    await query.answer()  # Acknowledge the callback
    
    # Get the callback data
    callback_data = query.data
    
    try:
        if callback_data == "hit":
            await process_hit(update, context, query.message)
        elif callback_data == "stats":
            await process_stats(update, context, query.message)
        elif callback_data == "highscore":
            await process_highscore(update, context, query.message)
        elif callback_data == "achievements":
            await process_achievements(update, context, query.message)
        elif callback_data == "daily":
            await process_daily(update, context, query.message)
        elif callback_data == "help":
            await process_help(update, context, query.message)
        elif callback_data == "groupboard":
            await process_groupboard(update, context, query.message)
        elif callback_data == "dailygroup":
            await process_dailygroup(update, context, query.message)
        else:
            await query.message.reply_text("❌ Unknown button pressed!")
            
    except Exception as e:
        logger.error(f"Button callback error: {e}")
        await query.message.reply_text("❌ Something went wrong! Try again.")

# === MAIN FUNCTION ===
def main():
    try:
        app = ApplicationBuilder().token(TOKEN).build()

        # Command handlers
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("hit", hit_command))
        app.add_handler(CommandHandler("stats", stats_command))
        app.add_handler(CommandHandler("mylevel", mylevel))
        app.add_handler(CommandHandler("highscore", highscore_command))
        app.add_handler(CommandHandler("achievements", achievements_command))
        app.add_handler(CommandHandler("daily", daily_command))
        app.add_handler(CommandHandler("groupboard", groupboard_command))
        app.add_handler(CommandHandler("dailygroup", dailygroup_command))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("resetleaderboard", reset_leaderboard))
        app.add_handler(CommandHandler("backup", backup_data_command))
        
        # Callback handler for inline buttons
        app.add_handler(CallbackQueryHandler(button_callback))

        print("🚬 Rasta Ganja Bot is now online for groups and private chats!")
        print("📊 Features: Group competitions, individual stats, achievements")
        print("👥 Group Features: Group leaderboards, group achievements, social competitions")
        print("🔧 Admin commands: /resetleaderboard, /backup")
        print("🎯 All interactive buttons are functional!")
        
        # Use run_polling() directly without asyncio.run()
        app.run_polling()
        
    except Exception as e:
        print(f"❌ Error starting bot: {e}")
        logger.error(f"Bot startup error: {e}")

# === RUN ===
if __name__ == "__main__":
    main()

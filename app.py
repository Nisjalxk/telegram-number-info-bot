import os
import re
import json
import requests
from flask import Flask, request
from telegram import Bot, Update
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, filters

BOT_TOKEN = os.environ.get("8196241430:AAHRogpStbeGymFsB76ZPQtHAxisGyr178w")
ADMIN_USER_ID = int(os.environ.get("8002918777", "6922440700"))  # Your Telegram user ID as admin

MOBILE_API_URL = "https://yourmobileapi.com/search?number={}"
EMAIL_API_URL = "https://youremailapi.com/search?email={}"

DATA_FILE = "data.json"

app = Flask(__name__)
bot = Bot(token=BOT_TOKEN)
dispatcher = Dispatcher(bot, None, workers=0, use_context=True)

PHONE_PATTERN = re.compile(r'^\+?\d{7,15}$')
EMAIL_PATTERN = re.compile(r'^[\w\.-]+@[\w\.-]+\.\w+$')

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    else:
        return {"users": {}}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)

data = load_data()

def is_blacklisted(user_id):
    user = data["users"].get(str(user_id))
    return user and user.get("blacklisted", False)

def add_user(user_id, referred_by=None):
    user_id = str(user_id)
    if user_id not in data["users"]:
        data["users"][user_id] = {"credits": 0, "referred_by": referred_by, "blacklisted": False}
        if referred_by and referred_by != user_id and referred_by in data["users"]:
            data["users"][referred_by]["credits"] = data["users"][referred_by].get("credits", 0) + 1
        save_data(data)

def start(update, context):
    user_id = update.message.from_user.id
    args = context.args
    ref = args[0] if args else None

    add_user(user_id, referred_by=ref)
    credits = data["users"][str(user_id)]["credits"]

    msg = (
        f"Welcome! You have {credits} credits.\n"
        "Each search costs 1 credit.\n"
        "Refer others to get 1 credit each: send this link:\n"
        f"https://t.me/{context.bot.username}?start={user_id}\n\n"
        "To buy more credits, contact @YourAdminUsername."
    )

    update.message.reply_text(msg)

def show_credits(update, context):
    user_id = update.message.from_user.id
    if str(user_id) not in data["users"]:
        add_user(user_id)
    credits = data["users"][str(user_id)]["credits"]
    update.message.reply_text(f"You have {credits} credits.")

def handle_message(update, context):
    user_id = update.message.from_user.id
    if is_blacklisted(user_id):
        update.message.reply_text("You are blacklisted and cannot use this bot.")
        return

    user_id_str = str(user_id)
    if user_id_str not in data["users"]:
        add_user(user_id)
    user_credits = data["users"][user_id_str]["credits"]

    if user_credits < 1:
        update.message.reply_text(
            "You have no credits left! Please contact @YourAdminUsername to purchase more credits."
        )
        return

    user_input = update.message.text.strip()

    if PHONE_PATTERN.match(user_input):
        api_url = MOBILE_API_URL.format(user_input)
        response = requests.get(api_url)
        if response.status_code == 200:
            data_resp = response.json()
            reply = f"Mobile info for {user_input}:\n{data_resp}"
            data["users"][user_id_str]["credits"] -= 1
            save_data(data)
        else:
            reply = "Sorry, couldn't retrieve mobile info."
    elif EMAIL_PATTERN.match(user_input):
        api_url = EMAIL_API_URL.format(user_input)
        response = requests.get(api_url)
        if response.status_code == 200:
            data_resp = response.json()
            reply = f"Email info for {user_input}:\n{data_resp}"
            data["users"][user_id_str]["credits"] -= 1
            save_data(data)
        else:
            reply = "Sorry, couldn't retrieve email info."
    else:
        reply = "Please send a valid phone number or email."

    update.message.reply_text(reply)

def admin_add_credits(update, context):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        update.message.reply_text("You are not authorized to use this command.")
        return

    args = context.args
    if len(args) != 2:
        update.message.reply_text("Usage: /addcredits <user_id> <amount>")
        return

    target_user, amount = args
    try:
        amount = int(amount)
        if amount <= 0:
            raise ValueError
    except ValueError:
        update.message.reply_text("Amount must be a positive integer.")
        return

    if target_user not in data["users"]:
        update.message.reply_text("User not found.")
        return

    data["users"][target_user]["credits"] = data["users"][target_user].get("credits", 0) + amount
    save_data(data)
    update.message.reply_text(f"Added {amount} credits to user {target_user}.")

def admin_deduct_credits(update, context):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        update.message.reply_text("You are not authorized to use this command.")
        return

    args = context.args
    if len(args) != 2:
        update.message.reply_text("Usage: /deductcredits <user_id> <amount>")
        return

    target_user, amount = args
    try:
        amount = int(amount)
        if amount <= 0:
            raise ValueError
    except ValueError:
        update.message.reply_text("Amount must be a positive integer.")
        return

    if target_user not in data["users"]:
        update.message.reply_text("User not found.")
        return

    current_credits = data["users"][target_user].get("credits", 0)
    if current_credits < amount:
        update.message.reply_text(f"User only has {current_credits} credits, cannot deduct {amount}.")
        return

    data["users"][target_user]["credits"] = current_credits - amount
    save_data(data)
    update.message.reply_text(f"Deducted {amount} credits from user {target_user}.")

def admin_blacklist(update, context):
    user_id = update.message.from_user.id
    if user_id != ADMIN_USER_ID:
        update.message.reply_text("You are not authorized to use this command.")
        return

    args = context.args
    if len(args) != 2:
        update.message.reply_text("Usage: /blacklist <user_id> <on/off>")
        return

    target_user, action = args
    if target_user not in data["users"]:
        update.message.reply_text("User not found.")
        return

    if action.lower() == "on":
        data["users"][target_user]["blacklisted"] = True
        save_data(data)
        update.message.reply_text(f"User {target_user} is blacklisted.")
    elif action.lower() == "off":
        data["users"][target_user]["blacklisted"] = False
        save_data(data)
        update.message.reply_text(f"User {target_user} is removed from blacklist.")
    else:
        update.message.reply_text("Action must be 'on' or 'off'.")

dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("credits", show_credits))
dispatcher.add_handler(CommandHandler("addcredits", admin_add_credits))
dispatcher.add_handler(CommandHandler("deductcredits", admin_deduct_credits))
dispatcher.add_handler(CommandHandler("blacklist", admin_blacklist))
dispatcher.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), bot)
    dispatcher.process_update(update)
    return "ok"

@app.route("/")
def index():
    return "Bot is running!"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

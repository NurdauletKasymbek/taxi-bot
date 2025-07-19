
import telebot
from telebot import types
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from config import *

bot = telebot.TeleBot(BOT_TOKEN)

# Google Sheets setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("creds.json", scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SHEET_ID)
drivers_ws = sheet.worksheet(DRIVERS_SHEET)
requests_ws = sheet.worksheet(REQUESTS_SHEET)

# User state tracking
user_state = {}
user_data = {}
pending_requests = {}

# Main menu keyboard
def main_menu_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("Такси шақыру", "Серіктес болу")
    markup.add("📞 Қолдау қызметі")
    return markup

@bot.message_handler(commands=['start'])
def start(msg):
    cid = msg.chat.id
    user_state[cid] = None
    user_data[cid] = {}
    bot.send_message(cid, "Қош келдіңіз! Қызмет түрін таңдаңыз:", reply_markup=main_menu_keyboard())

@bot.message_handler(func=lambda msg: True)
def universal_handler(msg):
    cid = msg.chat.id
    text = msg.text.strip()

    # Stop all previous state
    user_state[cid] = None
    user_data[cid] = {}

    if text == "Такси шақыру":
        user_state[cid] = "waiting_name"
        bot.send_message(cid, "Атыңызды енгізіңіз:", reply_markup=main_menu_keyboard())
    elif user_state.get(cid) == "waiting_name":
        user_data[cid] = {"name": text}
        user_state[cid] = "waiting_phone"
        bot.send_message(cid, "Телефон нөміріңіз:", reply_markup=main_menu_keyboard())
    elif user_state.get(cid) == "waiting_phone":
        user_data[cid]["phone"] = text
        user_state[cid] = "waiting_from"
        bot.send_message(cid, "Қай жерден алып кету керек?", reply_markup=main_menu_keyboard())
    elif user_state.get(cid) == "waiting_from":
        user_data[cid]["from"] = text
        user_state[cid] = "waiting_to"
        bot.send_message(cid, "Қайда барасыз?", reply_markup=main_menu_keyboard())
    elif user_state.get(cid) == "waiting_to":
        user_data[cid]["to"] = text
        user_state[cid] = "waiting_time"
        bot.send_message(cid, "Қай уақытта (мысалы: 18:00 22.07.2025):", reply_markup=main_menu_keyboard())
    elif user_state.get(cid) == "waiting_time":
        user_data[cid]["time"] = text
        user_state[cid] = None

        info = user_data[cid]
        order_id = cid
        pending_requests[order_id] = {"accepted": False}

        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("Қабылдаймын", callback_data=f"accept_{order_id}"),
            types.InlineKeyboardButton("Қабылдамаймын", callback_data="ignore")
        )

        order_text = (
            "🚕 Жаңа тапсырыс!

"
            f"Аты: {info['name']}
"
            f"Телефон: {info['phone']}
"
            f"Алып кету: {info['from']}
"
            f"Бару: {info['to']}
"
            f"Уақыты: {info['time']}"
        )

        sent = bot.send_message(DRIVER_GROUP_ID, order_text, reply_markup=markup)
        pending_requests[order_id]["message_id"] = sent.message_id
        bot.send_message(cid, "🚗 Жүргізуші іздестірілуде...", reply_markup=main_menu_keyboard())

    elif text == "Серіктес болу":
        user_state[cid] = "reg_name"
        bot.send_message(cid, "Атыңызды енгізіңіз:", reply_markup=main_menu_keyboard())
    elif user_state.get(cid) == "reg_name":
        user_data[cid] = {"name": text}
        user_state[cid] = "reg_phone"
        bot.send_message(cid, "Телефон нөміріңіз:", reply_markup=main_menu_keyboard())
    elif user_state.get(cid) == "reg_phone":
        user_data[cid]["phone"] = text
        user_state[cid] = "reg_number"
        bot.send_message(cid, "Көлік номеріңіз:", reply_markup=main_menu_keyboard())
    elif user_state.get(cid) == "reg_number":
        user_data[cid]["number"] = text
        user_state[cid] = "reg_car"
        bot.send_message(cid, "Көлік маркасы:", reply_markup=main_menu_keyboard())
    elif user_state.get(cid) == "reg_car":
        user_data[cid]["car"] = text
        user_state[cid] = None

        data = user_data[cid]
        drivers_ws.append_row([
            str(cid),
            data["name"],
            data["phone"],
            data["number"],
            data["car"]
        ])

        bot.send_message(cid, "🎉 Сіз жүргізуші ретінде тіркелдіңіз! Енді @kasymbekoffnr аккаунтына жазыңыз — сізді топқа қосу үшін.", reply_markup=main_menu_keyboard())

    elif text == "📞 Қолдау қызметі":
        bot.send_message(cid, "📞 Қолдау қызметі: @kasymbekoffnr", reply_markup=main_menu_keyboard())

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data.startswith("accept_"):
        order_id = int(call.data.split("_")[1])
        if pending_requests.get(order_id, {}).get("accepted"):
            bot.answer_callback_query(call.id, "Бұл тапсырыс қабылданған.")
            return

        driver_id = call.from_user.id
        driver_info = get_driver_by_id(driver_id)
        if not driver_info:
            bot.answer_callback_query(call.id, "Сіз тіркелмегенсіз.")
            return

        pending_requests[order_id]["accepted"] = True
        pending_requests[order_id]["driver_id"] = driver_id

        client_info = user_data.get(order_id)
        if client_info:
            requests_ws.append_row([
                str(order_id),
                client_info['name'],
                client_info['to'],
                client_info['phone'],
                client_info['time'],
                str(driver_id),
                driver_info['name'],
                driver_info['phone'],
                driver_info['number'],
                driver_info['car']
            ])

            bot.send_message(order_id, (
                f"✅ Жүргізуші табылды!

"
                f"Аты-жөні: {driver_info['name']}
"
                f"Тел: {driver_info['phone']}
"
                f"Көлік: {driver_info['car']}
"
                f"Нөмірі: {driver_info['number']}"
            ), reply_markup=main_menu_keyboard())

            bot.send_message(driver_id, (
                f"🚖 Сіз клиентті алдыңыз!

"
                f"Аты: {client_info['name']}
"
                f"Тел: {client_info['phone']}
"
                f"Алып кету: {client_info['from']}
"
                f"Бару: {client_info['to']}
"
                f"Уақыты: {client_info['time']}"
            ))

            bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=None
            )

        bot.answer_callback_query(call.id, "Сіз тапсырысты қабылдадыңыз.")
    elif call.data == "ignore":
        bot.answer_callback_query(call.id, "Рақмет, қабылдамадыңыз.")

def get_driver_by_id(tid):
    all_data = drivers_ws.get_all_records()
    for row in all_data:
        if str(row["Telegram ID"]) == str(tid):
            return {
                "name": row["Аты-жөні"],
                "phone": row["Телефон"],
                "number": row["Көлік номері"],
                "car": row["Көлік маркасы"]
            }
    return None

bot.infinity_polling()

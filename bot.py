import telebot
from telebot import types
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from config import *

bot = telebot.TeleBot(BOT_TOKEN)

# Google Sheets setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/creds.json", scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SHEET_ID)
drivers_ws = sheet.worksheet(DRIVERS_SHEET)
requests_ws = sheet.worksheet(REQUESTS_SHEET)

# Global states
user_state = {}
user_data = {}
pending_requests = {}

COMMAND_BUTTONS = ["Такси шақыру", "Серіктес болу", "📞 Қолдау қызметі"]

def main_menu_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("Такси шақыру", "Серіктес болу")
    markup.add("📞 Қолдау қызметі")
    return markup

def reset_user(cid):
    user_state[cid] = None
    user_data[cid] = {}
    bot.clear_step_handler_by_chat_id(cid)

@bot.message_handler(commands=['start'])
def start(msg):
    cid = msg.chat.id
    reset_user(cid)
    bot.send_message(cid, "Қош келдіңіз! Қызмет түрін таңдаңыз:", reply_markup=main_menu_keyboard())

@bot.message_handler(func=lambda msg: True)
def main_handler(msg):
    cid = msg.chat.id
    text = msg.text

    if text == "📞 Қолдау қызметі":
        return support(msg)
    elif text == "Такси шақыру":
        return start_taxi_flow(msg)
    elif text == "Серіктес болу":
        return start_driver_registration(msg)
    else:
        # Егер күтіліп жатқан step бар болса, өңдеу
        if user_state.get(cid) in step_handlers:
            return step_handlers[user_state[cid]](msg)
        else:
            bot.send_message(cid, "Түсінбедім, төмендегі батырмалардың бірін таңдаңыз:", reply_markup=main_menu_keyboard())

# Қолдау қызметі
def support(msg):
    cid = msg.chat.id
    reset_user(cid)
    bot.send_message(cid, "📞 Қолдау қызметі: @kasymbekoffnr", reply_markup=main_menu_keyboard())

# ---------------- Такси шақыру ------------------

def start_taxi_flow(msg):
    cid = msg.chat.id
    reset_user(cid)
    user_state[cid] = "waiting_name"
    bot.send_message(cid, "Атыңызды енгізіңіз:", reply_markup=main_menu_keyboard())

def handle_name(msg):
    cid = msg.chat.id
    user_data[cid]['name'] = msg.text
    user_state[cid] = "waiting_phone"
    bot.send_message(cid, "Телефон нөміріңіз:", reply_markup=main_menu_keyboard())

def handle_phone(msg):
    cid = msg.chat.id
    user_data[cid]['phone'] = msg.text
    user_state[cid] = "waiting_from"
    bot.send_message(cid, "Қай жерден алып кету керек?", reply_markup=main_menu_keyboard())

def handle_from(msg):
    cid = msg.chat.id
    user_data[cid]['from'] = msg.text
    user_state[cid] = "waiting_to"
    bot.send_message(cid, "Қайда барасыз?", reply_markup=main_menu_keyboard())

def handle_to(msg):
    cid = msg.chat.id
    user_data[cid]['to'] = msg.text
    user_state[cid] = "waiting_time"
    bot.send_message(cid, "Қай уақытта (мысалы: 18:00 22.07.2025):", reply_markup=main_menu_keyboard())

def handle_time(msg):
    cid = msg.chat.id
    user_data[cid]['time'] = msg.text
    order_id = cid
    pending_requests[order_id] = {
        "accepted": False,
        "client_info": user_data[cid]  # Клиент деректерін сақтап қойдық
    }

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("Қабылдаймын", callback_data=f"accept_{order_id}"),
        types.InlineKeyboardButton("Қабылдамаймын", callback_data="ignore")
    )

    info = user_data[cid]
    order_text = (
        "🚕 Жаңа тапсырыс!\n\n"
        f"Аты: {info['name']}\n"
        f"Телефон: {info['phone']}\n"
        f"Алып кету: {info['from']}\n"
        f"Бару: {info['to']}\n"
        f"Уақыты: {info['time']}"
    )

    sent = bot.send_message(DRIVER_GROUP_ID, order_text, reply_markup=markup)
    pending_requests[order_id]["message_id"] = sent.message_id
    pending_requests[order_id]["chat_id"] = sent.chat.id  # Қай топқа жіберілгенін сақтау

    bot.send_message(cid, "🚗 Жүргізуші іздестірілуде...", reply_markup=main_menu_keyboard())
    reset_user(cid)


# ---------------- Серіктес болу ------------------

def start_driver_registration(msg):
    cid = msg.chat.id
    reset_user(cid)
    user_state[cid] = "reg_name"
    bot.send_message(cid, "Атыңызды жазыңыз:", reply_markup=main_menu_keyboard())

def ask_driver_phone(msg):
    cid = msg.chat.id
    user_data[cid]['name'] = msg.text
    user_state[cid] = "reg_phone"
    bot.send_message(cid, "Телефон нөміріңіз:", reply_markup=main_menu_keyboard())

def ask_driver_number(msg):
    cid = msg.chat.id
    user_data[cid]['phone'] = msg.text
    user_state[cid] = "reg_number"
    bot.send_message(cid, "Көлік номеріңіз:", reply_markup=main_menu_keyboard())

def ask_driver_car(msg):
    cid = msg.chat.id
    user_data[cid]['number'] = msg.text
    user_state[cid] = "reg_car"
    bot.send_message(cid, "Көлік маркасы:", reply_markup=main_menu_keyboard())

def finish_driver_registration(msg):
    cid = msg.chat.id
    user_data[cid]['car'] = msg.text
    user_state[cid] = None

    data = user_data[cid]
    drivers_ws.append_row([
        str(cid),
        data['name'],
        data['phone'],
        data['number'],
        data['car']
    ])

    bot.send_message(cid,
        "🎉 Сіз жүргізуші ретінде тіркелдіңіз!\n"
        "Енді @kasymbekoffnr аккаунтына жазыңыз — сізді топқа қосу үшін.",
        reply_markup=main_menu_keyboard()
    )
    reset_user(cid)

# Step handler mapping
step_handlers = {
    "waiting_name": handle_name,
    "waiting_phone": handle_phone,
    "waiting_from": handle_from,
    "waiting_to": handle_to,
    "waiting_time": handle_time,
    "reg_name": ask_driver_phone,
    "reg_phone": ask_driver_number,
    "reg_number": ask_driver_car,
    "reg_car": finish_driver_registration,
}

# ---------------- Callback ------------------

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

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    if call.data.startswith("accept_"):
        order_id = int(call.data.split("_")[1])

        if pending_requests.get(order_id, {}).get("accepted"):
            return bot.answer_callback_query(call.id, "Бұл тапсырыс қабылданған.")

        driver_id = call.from_user.id
        driver_info = get_driver_by_id(driver_id)
        if not driver_info:
            return bot.answer_callback_query(call.id, "Сіз тіркелмегенсіз.")

        # Тапсырысты бекіту
        pending_requests[order_id]["accepted"] = True
        pending_requests[order_id]["driver_id"] = driver_id

        client_info = pending_requests[order_id].get("client_info")
        if client_info:
            # Sheets-ке жазу
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

            # Клиентке жүргізуші дерегін жіберу
            bot.send_message(order_id, (
                f"✅ Жүргізуші табылды!\n\n"
                f"Аты-жөні: {driver_info['name']}\n"
                f"Тел: {driver_info['phone']}\n"
                f"Көлік: {driver_info['car']}\n"
                f"Нөмірі: {driver_info['number']}"
            ), reply_markup=main_menu_keyboard())

            # Жүргізушіге клиент дерегін жіберу
            bot.send_message(driver_id, (
                f"🚖 Сіз клиентті алдыңыз!\n\n"
                f"Аты: {client_info['name']}\n"
                f"Тел: {client_info['phone']}\n"
                f"Алып кету: {client_info['from']}\n"
                f"Бару: {client_info['to']}\n"
                f"Уақыты: {client_info['time']}"
            ))

            # Чаттан тапсырыс хабарламасын жою
            try:
                bot.delete_message(
                    chat_id=pending_requests[order_id]["chat_id"],
                    message_id=pending_requests[order_id]["message_id"]
                )
            except:
                pass

        bot.answer_callback_query(call.id, "Сіз тапсырысты қабылдадыңыз.")

    elif call.data == "ignore":
        bot.answer_callback_query(call.id, "Рақмет, қабылдамадыңыз.")


bot.infinity_polling()

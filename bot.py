import telebot
from telebot import types
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from config import *

bot = telebot.TeleBot(BOT_TOKEN)

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/creds.json", scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SHEET_ID)
drivers_ws = sheet.worksheet(DRIVERS_SHEET)
requests_ws = sheet.worksheet(REQUESTS_SHEET)

user_data = {}
pending_requests = {}

@bot.message_handler(commands=['start'])
def start(msg):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Такси шақыру", "Серіктес болу")
    bot.send_message(msg.chat.id, "Қош келдіңіз! Қызмет түрін таңдаңыз:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "Такси шақыру")
def taxi_request(msg):
    user_data[msg.chat.id] = {}
    bot.send_message(msg.chat.id, "Атыңызды енгізіңіз:")
    bot.register_next_step_handler(msg, ask_phone)

def ask_phone(msg):
    user_data[msg.chat.id]['name'] = msg.text
    bot.send_message(msg.chat.id, "Телефон нөміріңіз:")
    bot.register_next_step_handler(msg, ask_from)

def ask_from(msg):
    user_data[msg.chat.id]['phone'] = msg.text
    bot.send_message(msg.chat.id, "Қай жерден алып кету керек?")
    bot.register_next_step_handler(msg, ask_to)

def ask_to(msg):
    user_data[msg.chat.id]['from'] = msg.text
    bot.send_message(msg.chat.id, "Қайда барасыз?")
    bot.register_next_step_handler(msg, ask_time)

def ask_time(msg):
    user_data[msg.chat.id]['to'] = msg.text
    bot.send_message(msg.chat.id, "Қай уақытта (мысалы: 17:00 17.07.2025):")
    bot.register_next_step_handler(msg, confirm_order)

def confirm_order(msg):
    user_data[msg.chat.id]['time'] = msg.text
    order_id = msg.chat.id
    pending_requests[order_id] = {"accepted": False}

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("Қабылдаймын", callback_data=f"accept_{order_id}"),
        types.InlineKeyboardButton("Қабылдамаймын", callback_data="ignore")
    )

    order_text = (
        "Жаңа тапсырыс!\n\n"
        f"Аты: {user_data[order_id]['name']}\n"
        f"Телефон: {user_data[order_id]['phone']}\n"
        f"Алып кету: {user_data[order_id]['from']}\n"
        f"Баратын жері: {user_data[order_id]['to']}\n"
        f"Уақыты: {user_data[order_id]['time']}"
    )

    msg_sent = bot.send_message(DRIVER_GROUP_ID, order_text, reply_markup=markup)
    pending_requests[order_id]["message_id"] = msg_sent.message_id

    cancel_markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    cancel_markup.add("Тапсырыстан бас тарту")
    bot.send_message(order_id, "Жүргізуші іздестірілуде...", reply_markup=cancel_markup)

@bot.message_handler(func=lambda m: "бас тарту" in m.text.lower())
def cancel_order(msg):
    user_data.pop(msg.chat.id, None)
    bot.send_message(msg.chat.id, "Тапсырысыңыз жойылды.", reply_markup=types.ReplyKeyboardRemove())

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
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

        # 1. Клиентке жүргізуші дерегін жіберу
        bot.send_message(order_id, (
            f"Жүргізуші табылды!\n\n"
            f"Аты-жөні: {driver_info['name']}\n"
            f"Тел: {driver_info['phone']}\n"
            f"Көлік: {driver_info['car']}\n"
            f"Нөмірі: {driver_info['number']}"
        ), reply_markup=types.ReplyKeyboardRemove())

        # 2. Жүргізушіге клиент туралы жеке хабарлама
        bot.send_message(driver_id, (
            f"Сіз клиентті алдыңыз!\n\n"
            f"Аты: {client_info['name']}\n"
            f"Телефон: {client_info['phone']}\n"
            f"Алып кету: {client_info['from']}\n"
            f"Баратын жері: {client_info['to']}\n"
            f"Уақыты: {client_info['time']}"
        ))

        # 3. Топтағы хабарламадан кнопканы алып тастау
        bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=None
        )

        bot.answer_callback_query(call.id, "Сіз тапсырысты қабылдадыңыз.")
    elif call.data == "ignore":
        bot.answer_callback_query(call.id, "Рақмет, қабылдамадыңыз.")

@bot.message_handler(func=lambda m: m.text == "Серіктес болу")
def driver_register(msg):
    bot.send_message(msg.chat.id, "Атыңыз кім?")
    bot.register_next_step_handler(msg, ask_driver_phone)

def ask_driver_phone(msg):
    user_data[msg.chat.id] = {'name': msg.text}
    bot.send_message(msg.chat.id, "Телефон нөміріңіз:")
    bot.register_next_step_handler(msg, ask_driver_car_number)

def ask_driver_car_number(msg):
    user_data[msg.chat.id]['phone'] = msg.text
    bot.send_message(msg.chat.id, "Көлік номеріңіз:")
    bot.register_next_step_handler(msg, ask_driver_car_model)

def ask_driver_car_model(msg):
    user_data[msg.chat.id]['number'] = msg.text
    bot.send_message(msg.chat.id, "Көлік маркасы:")
    bot.register_next_step_handler(msg, finish_driver_register)

def finish_driver_register(msg):
    data = user_data[msg.chat.id]
    data['car'] = msg.text
    drivers_ws.append_row([
        str(msg.chat.id),
        data['name'],
        data['phone'],
        data['number'],
        data['car']
    ])
    bot.send_message(msg.chat.id, "Сіз жүргізуші ретінде тіркелдіңіз!", reply_markup=types.ReplyKeyboardRemove())

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

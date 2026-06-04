import sqlite3
import logging
import os
import sys
import asyncio
from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, timedelta
from aiogram.filters import Command, StateFilter
from dotenv import load_dotenv
from database import DB_PATH, get_connection

load_dotenv()

API_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID_RAW = os.getenv('ADMIN_ID')
if not API_TOKEN:
    sys.exit("Missing required BOT_TOKEN in .env")
try:
    ADMIN_ID = int(ADMIN_ID_RAW or "")
except ValueError:
    sys.exit("Missing or invalid required ADMIN_ID in .env")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
router = Router()

class Form(StatesGroup):
    select_service = State()
    select_date = State()
    select_time = State()

def init_db():
    conn = get_connection()
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS service_time_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id INTEGER NOT NULL,
            time_slot TEXT NOT NULL,
            UNIQUE(service_id, time_slot),
            FOREIGN KEY(service_id) REFERENCES services(id) ON DELETE CASCADE
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            date TEXT,
            time TEXT,
            service_id INTEGER,
            FOREIGN KEY(service_id) REFERENCES services(id)
        )
    ''')

    conn.commit()
    conn.close()

init_db()

def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📅 Записаться")],
            [KeyboardButton(text="📋 Мои записи")],
            [KeyboardButton(text="🗑 Удалить запись")],
            [KeyboardButton(text="❓ Помощь")],
        ],
        resize_keyboard=True,
    )

def service_keyboard(services):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{name} — {price}₽", callback_data=f"service_{sid}")]
            for sid, name, price in services
        ] + [[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]]
    )

def date_keyboard(today):
    rows = [
        [InlineKeyboardButton(text=(today + timedelta(days=i)).strftime('%Y-%m-%d'),
                              callback_data=f"date_{(today + timedelta(days=i)).strftime('%Y-%m-%d')}")]
        for i in range(2, 7)
    ]
    rows.append([
        InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_service"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="cancel"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def time_keyboard(available):
    rows = []
    for i in range(0, len(available), 3):
        rows.append([
            InlineKeyboardButton(text=t, callback_data=f"time_{t}")
            for t in available[i:i + 3]
        ])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_date")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def user_delete_keyboard(rows):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{date} {time}", callback_data=f"delete_{booking_id}")]
            for booking_id, date, time in rows
        ] + [[InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]]
    )

@router.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Добро пожаловать! Выберите действие:", reply_markup=main_menu())

@router.message(F.text.in_(["📅 Записаться", "📋 Мои записи", "🗑 Удалить запись", "❓ Помощь"]))
async def reset_state_on_menu(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()

    if message.text == "📅 Записаться":
        await cmd_book(message, state)
    elif message.text == "📋 Мои записи":
        await my_bookings(message)
    elif message.text == "🗑 Удалить запись":
        await delete_booking_start(message)
    elif message.text == "❓ Помощь":
        await message.answer("Выберите действие из меню или напишите мне, если нужна помощь.", reply_markup=main_menu())

@router.message(F.text == "📅 Записаться")
async def cmd_book(message: types.Message, state: FSMContext):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, name, price FROM services ORDER BY name")
    services = c.fetchall()
    conn.close()

    if not services:
        await message.answer("Пока нет доступных услуг. Обратитесь к администратору.")
        return

    kb = service_keyboard(services)

    await message.answer("Выберите услугу:", reply_markup=kb)
    await state.set_state(Form.select_service)

@router.callback_query(F.data == "cancel")
async def cancel_handler(call: CallbackQuery, state: FSMContext):
    await state.clear()

    await bot.edit_message_text(chat_id=call.message.chat.id,
                                message_id=call.message.message_id,
                                text="Действие отменено. Главное меню:",
                                reply_markup=None)
    await bot.send_message(call.message.chat.id, "Выберите действие:", reply_markup=main_menu())

@router.callback_query(StateFilter(Form.select_service), F.data.startswith("service_"))
async def service_chosen(call: CallbackQuery, state: FSMContext):
    service_id = int(call.data.split("service_")[1])
    await state.update_data(service_id=service_id)

    today = datetime.today()
    kb = date_keyboard(today)

    await bot.edit_message_text(chat_id=call.message.chat.id,
                                message_id=call.message.message_id,
                                text="Выберите дату для записи:",
                                reply_markup=kb)
    await state.set_state(Form.select_date)

@router.callback_query(StateFilter(Form.select_date), F.data == "back_to_service")
async def back_to_service(call: CallbackQuery, state: FSMContext):
    await state.update_data(date=None)
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, name, price FROM services ORDER BY name")
    services = c.fetchall()
    conn.close()

    kb = service_keyboard(services)

    await bot.edit_message_text(chat_id=call.message.chat.id,
                                message_id=call.message.message_id,
                                text="Выберите услугу:",
                                reply_markup=kb)
    await state.set_state(Form.select_service)

@router.callback_query(StateFilter(Form.select_date), F.data.startswith("date_"))
async def date_chosen(call: CallbackQuery, state: FSMContext):
    date = call.data.split("date_")[1]
    data = await state.get_data()
    service_id = data.get("service_id")
    await state.update_data(date=date)

    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT time_slot FROM service_time_slots WHERE service_id=?", (service_id,))
    all_slots = [row[0] for row in c.fetchall()]

    if not all_slots:
        await bot.edit_message_text(chat_id=call.message.chat.id,
                                    message_id=call.message.message_id,
                                    text="Для выбранной услуги не настроены временные слоты. Обратитесь к администратору.")
        await state.clear()
        return

    c.execute("SELECT time FROM bookings WHERE date=?", (date,))
    booked = {row[0] for row in c.fetchall()}
    conn.close()

    available = [t for t in all_slots if t not in booked]
    if not available:
        await bot.edit_message_text(chat_id=call.message.chat.id,
                                    message_id=call.message.message_id,
                                    text=f"Все слоты заняты на {date}. Выберите другую дату.")
        await state.clear()
        return

    kb = time_keyboard(available)

    await bot.edit_message_text(chat_id=call.message.chat.id,
                                message_id=call.message.message_id,
                                text=f"Вы выбрали дату: {date}\nТеперь выберите время:",
                                reply_markup=kb)
    await state.set_state(Form.select_time)

@router.callback_query(StateFilter(Form.select_time), F.data == "back_to_date")
async def back_to_date(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()
    service_id = data.get("service_id")

    if not service_id:
        await call.message.answer("Ошибка: услуга не найдена.")
        return

    await state.update_data(date=None)

    today = datetime.today()
    kb = date_keyboard(today)

    try:
        await bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Выберите дату для записи:",
            reply_markup=kb
        )
        await state.set_state(Form.select_date)
    except Exception as e:
        await call.message.answer("Ошибка возврата к дате.")
        print("Ошибка при возврате к дате:", e)


@router.callback_query(StateFilter(Form.select_time), F.data.startswith("time_"))
async def time_chosen(call: CallbackQuery, state: FSMContext):
    await call.answer()
    time = call.data.split("_",1)[1]
    data = await state.get_data()
    date = data["date"]
    service_id = data["service_id"]
    user_id = call.from_user.id
    username = call.from_user.username or "—"

    conn = get_connection()
    c = conn.cursor()

    # Ограничение: не более 2 записей в день
    c.execute("SELECT COUNT(*) FROM bookings WHERE user_id=? AND date=?", (user_id, date))
    if c.fetchone()[0] >= 2:
        await call.message.answer("⚠️ Вы уже достигли лимита (2 записи в день).")
        conn.close()
        return

    # Ограничение: не более 1 записи на то же время
    c.execute("SELECT COUNT(*) FROM bookings WHERE user_id=? AND date=? AND time=?", (user_id, date, time))
    if c.fetchone()[0] > 0:
        await call.message.answer("⚠️ Вы уже записаны на это время.")
        conn.close()
        return

    c.execute("SELECT name, price FROM services WHERE id=?", (service_id,))
    row = c.fetchone()
    if not row:
        await call.message.answer("Ошибка: услуга не найдена.")
        conn.close()
        return
    service_name, price = row

    c.execute("INSERT INTO bookings (user_id, username, date, time, service_id) VALUES (?, ?, ?, ?, ?)",
              (user_id, username, date, time, service_id))
    conn.commit()
    conn.close()

    reply_text = (
        f"✅ Вы успешно записались!\n\n"
        f"🧾 Услуга: {service_name}\n"
        f"📅 Дата: {date}\n"
        f"🕒 Время: {time}\n\n"
        f"💰 Стоимость: {price} ₽\n"
        f"📲 Оплата по номеру телефона:\n"
        f"💳 +79781707090\n"
        f"Получатель: Анна Е.\n\n"
        f"❗ После оплаты, пожалуйста, пришлите скрин/чек оплаты"
    )

    try:
        await bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=reply_text,
            reply_markup=None
        )
    except Exception:
        await call.message.answer(reply_text)

    await bot.send_message(ADMIN_ID,
        f"📢 Новая запись:\n"
        f"👤 @{username}\n"
        f"📅 {date} 🕒 {time}\n"
        f"📚 Сервис: {service_name}"
    )

    await state.clear()

@router.message(F.text == "📋 Мои записи")
async def my_bookings(message: types.Message):
    user_id = message.from_user.id
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT b.id, b.date, b.time, s.name
        FROM bookings b
        LEFT JOIN services s ON b.service_id = s.id
        WHERE b.user_id = ?
        ORDER BY b.date, b.time
    ''', (user_id,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        await message.answer("У вас нет записей.", reply_markup=main_menu())
        return

    text = "Ваши записи:\n"
    for r in rows:
        text += f"ID: {r[0]} — {r[3]}, {r[1]} в {r[2]}\n"
    await message.answer(text, reply_markup=main_menu())

@router.message(F.text == "🗑 Удалить запись")
async def delete_booking_start(message: types.Message):
    user_id = message.from_user.id
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, date, time FROM bookings WHERE user_id=?", (user_id,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        await message.answer("У вас нет записей для удаления.", reply_markup=main_menu())
        return

    kb = user_delete_keyboard(rows)

    await message.answer("Выберите запись для удаления:", reply_markup=kb)

@router.callback_query(F.data.startswith("delete_"))
async def delete_booking_confirm(call: CallbackQuery):
    booking_id = int(call.data.split("delete_")[1])
    user_id = call.from_user.id

    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM bookings WHERE id=? AND user_id=?", (booking_id, user_id))
    conn.commit()
    deleted = c.rowcount
    conn.close()

    if deleted:
        await call.answer("Запись удалена", show_alert=True)
        await call.message.edit_text("Запись удалена.", reply_markup=main_menu())
    else:
        await call.answer("Не удалось удалить запись", show_alert=True)

@router.message(Command("admin"))
async def admin_list_bookings(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        await message.reply("⛔ У вас нет доступа к этой команде.")
        return

    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT b.username, b.date, b.time, s.name
        FROM bookings b
        LEFT JOIN services s ON b.service_id = s.id
        ORDER BY b.date, b.time
    ''')
    rows = c.fetchall()
    conn.close()

    if not rows:
        await message.answer("📭 Записей нет.")
        return

    text = "📋 Все записи:\n\n"
    for row in rows:
        username = row[0] or "—"
        service = row[3] or "—"
        text += f"👤 @{username}\n📚 Услуга: {service}\n📅 {row[1]} 🕒 {row[2]}\n\n"

    await message.answer(text)

@router.message(Command("admin_b"))
async def view_bookings(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT b.id, b.username, b.date, b.time, s.name 
        FROM bookings b 
        JOIN services s ON b.service_id = s.id 
        ORDER BY b.date, b.time
    """)
    records = c.fetchall()
    conn.close()

    if not records:
        await message.answer("Нет активных записей.")
        return

    for record in records:
        bid, username, date, time, service = record
        text = (f"📚 Услуга: {service}\n"
                f"👤 Пользователь: @{username}\n"
                f"📅 Дата: {date} 🕒 Время: {time}")

        kb = InlineKeyboardMarkup(
            inline_keyboard=[[
                InlineKeyboardButton(text="❌ Удалить", callback_data=f"booking:delete:{bid}")
            ]]
        )

        await message.answer(text, reply_markup=kb)

@router.callback_query(F.data.startswith("booking:delete:"))
async def delete_booking(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("Нет доступа", show_alert=True)
        return

    booking_id = call.data.split(":")[-1]

    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM bookings WHERE id=?", (booking_id,))
    conn.commit()
    conn.close()

    await call.message.edit_text("✅ Запись удалена.")
    await call.answer("Удалено.")

# === ХРАНЕНИЕ ПОЛЬЗОВАТЕЛЕЙ ДЛЯ РАССЫЛКИ ===

def save_user(user_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)''')
    c.execute('''INSERT OR IGNORE INTO users (user_id) VALUES (?)''', (user_id,))
    conn.commit()
    conn.close()

# === СОСТОЯНИЯ ДЛЯ РАССЫЛКИ ===

class BroadcastState(StatesGroup):
    waiting_for_content = State()

@router.message(Command("send_post"))
async def start_broadcast(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас нет доступа к этой команде.")
        return
    await message.answer("✉️ Пришлите сообщение, фото или видео для рассылки:")
    await state.set_state(BroadcastState.waiting_for_content)

@router.message(StateFilter(BroadcastState.waiting_for_content))
async def process_broadcast_content(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Нет доступа.")
        return

    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = [row[0] for row in c.fetchall()]
    conn.close()

    sent = 0
    for uid in users:
        try:
            if message.content_type == "text":
                await bot.send_message(uid, message.text)
            elif message.content_type == "photo":
                await bot.send_photo(uid, message.photo[-1].file_id, caption=message.caption or "")
            elif message.content_type == "video":
                await bot.send_video(uid, message.video.file_id, caption=message.caption or "")
            else:
                continue
            sent += 1
        except Exception:
            continue

    await message.answer(f"✅ Рассылка завершена. Успешно отправлено {sent} пользователям.")
    await state.clear()

# === ПЕРЕСЫЛКА ВСЕХ СООБЩЕНИЙ И ФАЙЛОВ АДМИНУ ===
def is_not_command(message: types.Message) -> bool:
    return not (message.text and message.text.startswith("/"))

@router.message(StateFilter(None), is_not_command)
async def forward_all_to_admin(message: types.Message, state: FSMContext):
    save_user(message.from_user.id)

    if message.from_user.id == ADMIN_ID:
        return

    username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
    header = f"📨 Сообщение от {username} (ID: {message.from_user.id})\n\n"

    try:
        if message.content_type == "text":
            await bot.send_message(ADMIN_ID, header + message.text)
        elif message.content_type == "photo":
            await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=header + (message.caption or ""))
        elif message.content_type == "video":
            await bot.send_video(ADMIN_ID, message.video.file_id, caption=header + (message.caption or ""))
        elif message.content_type == "document":
            await bot.send_document(ADMIN_ID, message.document.file_id, caption=header + (message.caption or ""))
        else:
            await bot.send_message(ADMIN_ID, header + f"Прислано сообщение типа {message.content_type}")
    except Exception as e:
        logging.error(f"Ошибка пересылки админу: {e}")

async def main():
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())

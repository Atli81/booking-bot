import sqlite3
import threading
import os
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.abspath(os.getenv('DATABASE_PATH') or os.path.join(PROJECT_DIR, 'database.db'))
_lock = threading.Lock()

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

class Database:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        with self.get_conn() as conn:
            c = conn.cursor()
            c.execute('''
                CREATE TABLE IF NOT EXISTS services (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
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
                    FOREIGN KEY(service_id) REFERENCES services(id),
                    UNIQUE(date, time)
                )
            ''')
            conn.commit()

    @contextmanager
    def get_conn(self):
        with _lock:  # для потокобезопасности
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA foreign_keys=ON")
            try:
                yield conn
            finally:
                conn.close()

    # Получить услуги
    def get_services(self):
        with self.get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT id, name, price FROM services ORDER BY name")
            return c.fetchall()

    # Добавить услугу
    def add_service(self, name, price):
        with self.get_conn() as conn:
            c = conn.cursor()
            c.execute("INSERT INTO services (name, price) VALUES (?, ?)", (name, price))
            conn.commit()

    # Удалить услугу
    def delete_service(self, service_id):
        with self.get_conn() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM services WHERE id=?", (service_id,))
            conn.commit()

    # Получить слоты по услуге
    def get_slots(self, service_id):
        with self.get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT id, time_slot FROM service_time_slots WHERE service_id=? ORDER BY time_slot", (service_id,))
            return c.fetchall()

    # Добавить слот
    def add_slot(self, service_id, time_slot):
        with self.get_conn() as conn:
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO service_time_slots (service_id, time_slot) VALUES (?, ?)", (service_id, time_slot))
            conn.commit()

    # Удалить слот
    def delete_slot(self, slot_id):
        with self.get_conn() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM service_time_slots WHERE id=?", (slot_id,))
            conn.commit()

    # Получить записи (все)
    def get_bookings(self):
        with self.get_conn() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT b.id, b.username, b.date, b.time, s.name
                FROM bookings b
                LEFT JOIN services s ON b.service_id = s.id
                ORDER BY b.date, b.time
            ''')
            return c.fetchall()

    # Получить записи пользователя
    def get_user_bookings(self, user_id):
        with self.get_conn() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT b.id, b.date, b.time, s.name
                FROM bookings b
                LEFT JOIN services s ON b.service_id = s.id
                WHERE b.user_id=?
                ORDER BY b.date, b.time
            ''', (user_id,))
            return c.fetchall()

    # Добавить запись с защитой от гонок
    def add_booking(self, user_id, username, date, time, service_id):
        with self.get_conn() as conn:
            c = conn.cursor()
            try:
                c.execute("BEGIN")
                # Проверяем занятость по дате и времени
                c.execute("SELECT COUNT(*) FROM bookings WHERE date=? AND time=?", (date, time))
                if c.fetchone()[0] > 0:
                    conn.rollback()
                    return False
                c.execute(
                    "INSERT INTO bookings (user_id, username, date, time, service_id) VALUES (?, ?, ?, ?, ?)",
                    (user_id, username, date, time, service_id)
                )
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                return False

    # Удалить запись по id и user_id (безопасно)
    def delete_user_booking(self, booking_id, user_id):
        with self.get_conn() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM bookings WHERE id=? AND user_id=?", (booking_id, user_id))
            conn.commit()
            return c.rowcount > 0

    # Удалить запись по id (админ)
    def delete_booking(self, booking_id):
        with self.get_conn() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM bookings WHERE id=?", (booking_id,))
            conn.commit()

    # Получить слоты для услуги
    def get_service_slots(self, service_id):
        return self.get_slots(service_id)

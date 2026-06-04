from flask import Flask, render_template, request, redirect, url_for, session, flash
import os
from database import Database
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

db = Database()

ADMIN_LOGIN = os.getenv('ADMIN_LOGIN')
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD')
FLASK_HOST = os.getenv('FLASK_HOST', '127.0.0.1')
FLASK_PORT = int(os.getenv('FLASK_PORT', '8000'))
FLASK_DEBUG = os.getenv('FLASK_DEBUG', '0').lower() in ('1', 'true', 'yes', 'on')

def login_required(func):
    from functools import wraps
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get('logged_in'):
            flash("Пожалуйста, войдите в систему.", "warning")
            return redirect(url_for('login'))
        return func(*args, **kwargs)
    return wrapper

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        login_ = request.form.get('login')
        password = request.form.get('password')
        if login_ == ADMIN_LOGIN and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            flash("Вы успешно вошли.", "success")
            return redirect(url_for('admin_panel'))
        else:
            flash("Неверный логин или пароль.", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("Вы вышли из системы.", "info")
    return redirect(url_for('login'))

@app.route('/admin')
@login_required
def admin_panel():
    services = db.get_services()
    bookings = db.get_bookings()
    return render_template('admin.html', services=services, bookings=bookings)

@app.route('/admin/service/add', methods=['POST'])
@login_required
def add_service():
    name = request.form.get('name')
    price = request.form.get('price')
    if name and price:
        try:
            price_val = float(price)
            db.add_service(name, price_val)
            flash("Услуга добавлена.", "success")
        except Exception:
            flash("Ошибка при добавлении услуги.", "danger")
    else:
        flash("Заполните все поля.", "warning")
    return redirect(url_for('admin_panel'))

@app.route('/admin/service/delete/<int:service_id>')
@login_required
def delete_service(service_id):
    db.delete_service(service_id)
    flash("Услуга удалена.", "info")
    return redirect(url_for('admin_panel'))

@app.route('/admin/service/<int:service_id>/slots', methods=['GET', 'POST'])
@login_required
def manage_slots(service_id):
    if request.method == 'POST':
        time_slot = request.form.get('time_slot')
        if time_slot:
            try:
                db.add_slot(service_id, time_slot)
                flash("Слот добавлен.", "success")
            except Exception:
                flash("Ошибка при добавлении слота.", "danger")
        else:
            flash("Введите время слота.", "warning")
        return redirect(url_for('manage_slots', service_id=service_id))

    slots = db.get_slots(service_id)
    return render_template('slots.html', service_id=service_id, slots=slots)

@app.route('/admin/service/<int:service_id>/slots/delete/<int:slot_id>')
@login_required
def delete_slot(service_id, slot_id):
    db.delete_slot(slot_id)
    flash("Слот удалён.", "info")
    return redirect(url_for('manage_slots', service_id=service_id))

@app.route('/admin/booking/delete/<int:booking_id>')
@login_required
def delete_booking(booking_id):
    db.delete_booking(booking_id)
    flash("Запись удалена.", "info")
    return redirect(url_for('admin_panel'))

if __name__ == '__main__':
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)


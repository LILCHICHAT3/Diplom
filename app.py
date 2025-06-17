from flask import Flask, render_template, url_for, Response, request, jsonify, redirect, send_file, make_response, \
    flash, abort
import base64
from sqlalchemy import text
from flask import current_app
from flask import send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import InputRequired, Length, ValidationError
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import create_engine, Column, String, Integer, DateTime, inspect,  LargeBinary
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from flask_cors import CORS
from db_manager import DatabaseManager  # Импортируем класс из db_manager
from datetime import datetime, timedelta
import asyncio
import subprocess
import sys
import secrets
import re
import glob
import random
import base64
import json
import os
from datetime import datetime, timedelta
import logging
from io import StringIO, BytesIO
import io
from time import sleep
from apscheduler.schedulers.background import BackgroundScheduler


app = Flask(__name__, template_folder="templates")

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///statistic.db'
db = SQLAlchemy(app)

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
CORS(app)
# Генерация и установка секретного ключа
app.config['SECRET_KEY'] = secrets.token_hex(16)
# Настройка для Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Параметры администратора
ADMIN_USERNAME = 'admin_user'
ADMIN_PASSWORD = generate_password_hash('123')  # Хешируем пароль


class admin_rools(db.Model):    
    id = db.Column(db.Integer, primary_key=True)  # Уникальный идентификатор
    penalty_days = db.Column(db.String(400), nullable=False)  # Дни наказания
    time_cleaning = db.Column(db.String(20), nullable=False)  # Время уборки (в минутах или других единицах)
    key = db.Column(db.String(100), nullable=False)  # Ключ
    dormitory = db.Column(db.String(400), nullable=False)

    def __repr__(self):
        return f'<admin_rools {self.id}>'


class head_of_hostel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(400), nullable=False)
    password = db.Column(db.String(400), nullable=False)
    number_of_dormitory = db.Column(db.String(100), nullable=False)
    number_of_floor = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(100), nullable=False)

    def __repr__(self):
        return f'<head_of_hostel {self.id}>'

class students(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(400), nullable=False)
    full_name = db.Column(db.String(400), nullable=False)
    number_of_room = db.Column(db.String(400), nullable=False)
    head = db.Column(db.String(100), nullable=False)
    photos = db.Column(LargeBinary, nullable=True)
    date_of_cleaning = db.Column(DateTime, nullable=True)
    status = db.Column(db.String(100), nullable=True)
    notification_sent = db.Column(db.Integer, default=0, nullable=False)

    def __repr__(self):
        return f'<students {self.id}>'

class Photo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    photo = db.Column(LargeBinary, nullable=False)

    def __repr__(self):
        return f'<Photo {self.id}>'


db_manager = DatabaseManager(db, admin_rools, head_of_hostel, students)  # Передаем модель

# Create db
with app.app_context():
    db.create_all()

def check_student_cleaning_status():
    with app.app_context():  # Устанавливаем контекст приложения
        students_list = students.query.all()  # Получаем всех студентов
        admin_settings = admin_rools.query.first()
        penalty_days = admin_settings.penalty_days if admin_settings else 0

        for student in students_list:
            # Игнорируем студентов с пустой датой уборки
            if student.date_of_cleaning is None or student.date_of_cleaning == '':
                print(f"Пропускаем {student.full_name}: дата уборки отсутствует.")
                continue  # Пропускаем текущую итерацию

            # Отладочные сообщения
            print(f"Проверяем {student.full_name}: статус = {student.status}, дата уборки = {student.date_of_cleaning}")

            # Если статус 'Нет уборки', пустой или None, устанавливаем штраф
            if student.status is None or student.status == 'Нет уборки' or student.status == '' or student.status == 'Ожидает подтверждения':
                # Проверяем, если прошло 10 секунд с момента уборки
                if datetime.now() > student.date_of_cleaning + timedelta(seconds=3600):  # 10 секунд
                    print(f"Устанавливаем штраф для {student.full_name}.")
                    # Обновляем статус на "Штраф"
                    student.status = 'Штраф'
                    db.session.commit()
                else:
                    print(f"У {student.full_name} еще не прошло 10 секунд.")
            else:
                print(f"Статус для {student.full_name} уже установлен: {student.status}")

scheduler = BackgroundScheduler()
scheduler.add_job(check_student_cleaning_status, 'interval', seconds=10)  # Проверять каждые 10 секунд
scheduler.start()



class AdminUser(UserMixin):
    def __init__(self, username):
        self.username = username

    def get_id(self):
        return self.username  # Можно использовать username как идентификатор


@login_manager.user_loader
def load_user(user_id):
    return AdminUser(user_id)


class LoginForm(FlaskForm):
    username = StringField('Имя пользователя', validators=[InputRequired()])
    password = PasswordField('Пароль', validators=[InputRequired()])
    submit = SubmitField('Войти')


@app.route('/login', methods=['GET', 'POST'])
def admin_login():
    form = LoginForm()
    if form.validate_on_submit():
        # Проверка супер администратора
        if (form.username.data == ADMIN_USERNAME and
                check_password_hash(ADMIN_PASSWORD, form.password.data)):
            admin_user = AdminUser(form.username.data)
            login_user(admin_user)
            return redirect(url_for('admin_dashboard'))

        # Проверка старосты
        head = head_of_hostel.query.filter_by(full_name=form.username.data).first()
        if head and check_password_hash(head.password, form.password.data):
            if head.status == 'declined':  # Проверяем статус
                flash('Ваш статус еще не подтвержден. Пожалуйста, обратитесь к администратору.', 'error')
                return redirect(url_for('admin_login'))

            # Вход для старосты
            admin_user = AdminUser(head.full_name)  # Используем имя старосты как идентификатор
            login_user(admin_user)
            return redirect(url_for('head_dashboard'))

        flash('Неверное имя пользователя или пароль')
    return render_template('admin_login.html', form=form)


@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def admin_dashboard():
    # Получаем список общежитий и настройки уборки
    dormitories = db_manager.get_dormitories()
    admin_role = admin_rools.query.first()

    # Проверяем, существует ли запись в admin_rools
    if admin_role is None:
        # Создаем новую запись с нулевыми значениями
        admin_role = admin_rools(
            penalty_days='0',
            time_cleaning='09:00',
            key='',
            dormitory=''
        )
        db.session.add(admin_role)
        db.session.commit()

    # Получаем список старост
    heads_of_hostel = db_manager.get_heads_of_hostel()

    if request.method == 'POST':
        # Получаем данные из формы
        dormitory_input = request.form.get('dormitory')
        key = request.form.get('key')
        time_cleaning = request.form.get('time_cleaning')
        penalty_days = request.form.get('penalty_days', type=int)

        # Разбиваем строку общежитий на список
        dormitories = [dorm.strip() for dorm in dormitory_input.split(',')]

        # Запись или обновление в базе данных
        db_manager.add_or_update_dormitory(penalty_days, time_cleaning, key, dormitories)
        flash('Настройки успешно сохранены!')

    # Извлекаем данные о токене, времени уборки и штрафе
    cleaning_settings = {
        'key': admin_role.key,
        'time_cleaning': admin_role.time_cleaning,
        'penalty_days': admin_role.penalty_days
    }

    return render_template('admin_dashboard.html', dormitories=dormitories, cleaning_settings=cleaning_settings,
                           heads_of_hostel=heads_of_hostel)

@app.route('/delete_student/<int:student_id>', methods=['POST'])
@login_required
def delete_student(student_id):
    student = students.query.get_or_404(student_id)

    # Удаляем связанные фото
    Photo.query.filter_by(student_id=student.id).delete()

    # Удаляем самого студента
    db.session.delete(student)
    db.session.commit()

    flash('Студент успешно удален!')
    return redirect(url_for('head_dashboard'))


@app.route('/delete_head/<int:head_id>', methods=['POST'])
@login_required
def delete_head(head_id):
    db_manager.delete_head_and_students(head_id)
    flash('Староста и связанные с ним студенты удалены!')
    return redirect(url_for('admin_dashboard'))


@app.route('/update_head_status/<int:id>', methods=['POST'])
@login_required
def update_head_status(id):
    head = head_of_hostel.query.get_or_404(id)  # Получаем старосту по ID
    # Изменяем статус
    head.status = 'accepted' if head.status == 'declined' else 'declined'
    db.session.commit()  # Сохраняем изменения в базе данных
    flash(f'Статус старосты "{head.full_name}" успешно обновлен на "{head.status}"!')
    return redirect(url_for('admin_dashboard'))


@app.route('/delete_dormitory', methods=['POST'])
@login_required
def delete_dormitory():
    dormitory_name = request.form.get('dormitory_name')

    # Передаем необходимые аргументы в экземпляр DatabaseManager
    db_manager = DatabaseManager(db, admin_rools,head_of_hostel, students)  # Создаем экземпляр DatabaseManager с обоими аргументами

    # Вызываем метод для удаления общежития
    db_manager.delete_dormitory(dormitory_name)
    flash(f'Общежитие "{dormitory_name}" успешно удалено!')
    return redirect(url_for('admin_dashboard'))


@app.route('/logout')
@login_required
def admin_logout():
    logout_user()
    return redirect(url_for('admin_login'))


@app.route('/register', methods=['GET', 'POST'])
def admin_register():
    if request.method == 'POST':
        # Получаем данные из формы
        full_name = request.form.get('full_name')
        password = request.form.get('password')
        number_of_dormitory = request.form.get('number_of_dormitory')
        number_of_floor = request.form.get('number_of_floor')

        # Создаем новый объект старосты
        new_head = head_of_hostel(
            full_name=full_name,
            password=generate_password_hash(password),  # Не забудьте хэшировать пароль
            number_of_dormitory=number_of_dormitory,
            number_of_floor=number_of_floor,
            status='declined'  # Устанавливаем статус в declined
        )

        # Сохраняем нового старосту в базе данных
        db.session.add(new_head)
        db.session.commit()
        flash('Староста успешно зарегистрирован!')

        return redirect(url_for('admin_login'))  # Перенаправляем на страницу логина

        # Получаем список общежитий для выпадающего списка
    dormitories = db_manager.get_dormitories()
    print(dormitories)
    return render_template('admin_register.html', dormitories=dormitories)


@app.route('/view_photos/<int:student_id>')
@login_required
def view_photos(student_id):
    # upload_photos_from_temp(student_id)
    photos = Photo.query.filter_by(student_id=student_id).order_by(Photo.id.desc()).limit(3).all()  # Получаем последние три фото для данного студента
    return render_template('view_photos.html', photos=photos)

@app.template_filter('b64encode')
def b64encode_filter(data):
    if data is not None:
        return base64.b64encode(data).decode('utf-8')
    return ''


@app.route('/update_student_status/<int:student_id>', methods=['POST'])
@login_required
def update_student_status(student_id):
    student = students.query.get_or_404(student_id)

    # Всегда выставляем статус "Убрался" и сбрасываем флаг
    student.status = 'Убрался'
    student.notification_sent = 0

    db.session.commit()
    flash('Уборка подтверждена! Статус обновлен на "Убрался".')
    return redirect(url_for('head_dashboard'))



@app.route('/cancel_student_cleanup/<int:student_id>', methods=['POST'])
@login_required
def cancel_student_cleanup(student_id):
    # Прямой SQL-запрос для сброса статуса и notification_sent
    sql = text("UPDATE students SET status = 'Нет уборки', notification_sent = 0 WHERE id = :student_id")
    db.session.execute(sql, {'student_id': student_id})
    db.session.commit()

    flash('Уборка отменена!')
    return redirect(url_for('head_dashboard'))


@app.route('/head_dashboard')
@login_required
def head_dashboard():
    # Получаем информацию о старосте
    head = head_of_hostel.query.filter_by(full_name=current_user.username).first()
    if not head:
        flash('Староста не найден!')
        return redirect(url_for('admin_dashboard'))

    # Получаем список студентов, которые принадлежат данному старосте
    students_list = students.query.filter_by(head=head.full_name).all()

    # Получаем время уборки и штрафы из admin_rools
    admin_settings = admin_rools.query.first()
    cleaning_time = admin_settings.time_cleaning if admin_settings else '09:00'
    penalty_days = int(admin_settings.penalty_days) if admin_settings and admin_settings.penalty_days.isdigit() else 0

    # Формируем текущую дату и время
    current_datetime = datetime.now()
    current_date = current_datetime.date()

    # Проверка: одна комната или нет
    unique_rooms = set(student.number_of_room for student in students_list)
    one_room_only = len(unique_rooms) == 1

    # Проверяем, убрались ли все
    all_cleaned = all(student.status == 'Убрался' for student in students_list)

    for index, student in enumerate(students_list):
        # Если штраф – устанавливаем ближайшие даты
        if student.status == 'Штраф':
            for day in range(penalty_days):
                cleaning_date = current_date + timedelta(days=day)
                student.date_of_cleaning = datetime.combine(cleaning_date, datetime.strptime(cleaning_time, '%H:%M').time())

        elif student.status == 'Убрался':
            if one_room_only:
                # Если одна комната – не сбрасываем статус, просто двигаем дату на 24 часа вперёд от текущей
                next_cleaning = current_datetime + timedelta(days=1)
                student.date_of_cleaning = datetime.combine(next_cleaning.date(), datetime.strptime(cleaning_time, '%H:%M').time())
            else:
                # Если все убрались – сбрасываем статус
                if all_cleaned and student.notification_sent == 1:
                    student.status = None
                    student.notification_sent = 0
                student.date_of_cleaning = datetime.combine(current_date + timedelta(days=index), datetime.strptime(cleaning_time, '%H:%M').time())

        elif not student.date_of_cleaning or student.date_of_cleaning == '':
            # Если дата пустая – установить по расписанию
            student.date_of_cleaning = datetime.combine(current_date + timedelta(days=index), datetime.strptime(cleaning_time, '%H:%M').time())

    db.session.commit()

    return render_template(
        'head_dashboard.html',
        head=head,
        students=students_list,
        cleaning_time=cleaning_time,
        penalty_days=penalty_days
    )


# Перенаправление на страницу входа, если не авторизован
@app.before_request
def before_request():
    if not current_user.is_authenticated:
        if request.endpoint not in ['admin_login', 'admin_register']:
            return redirect(url_for('admin_login'))


# def upload_photos_from_temp(student_id):
#     # Путь к папке, где хранятся фотографии
#     temp_folder = os.path.join(current_app.root_path, 'temp')  # Путь к папке temp
#
#     # Перебираем все файлы в папке
#     for filename in os.listdir(temp_folder):
#         file_path = os.path.join(temp_folder, filename)
#
#         # Проверяем, что это файл и имеет допустимое расширение
#         if os.path.isfile(file_path):
#             with open(file_path, 'rb') as file:
#                 photo_data = file.read()  # Читаем содержимое файла
#
#                 # Создаем новый объект Photo и сохраняем его в базу данных
#                 new_photo = Photo(student_id=student_id, photo=photo_data)
#                 db.session.add(new_photo)
#
#     db.session.commit()  # Сохраняем изменения в базе данных






if __name__ == '__main__':
    app.run(debug=False, port=9678)

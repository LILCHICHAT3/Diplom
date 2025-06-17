import os
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Путь к базе данных
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'statistic.db')


# Функция для получения токена из базы данных
def get_bot_token():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT key FROM admin_rools WHERE id = 1")  # Предполагается, что id = 1
    token = cursor.fetchone()[0]
    conn.close()
    return token


# Функция для отправки уведомлений о уборке
async def send_reminders(application):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    current_time = datetime.now()
    today = current_time.date()

    cursor.execute("SELECT id, user_id, date_of_cleaning, status, notification_sent FROM students")
    students = cursor.fetchall()

    for student in students:
        student_id = student[0]
        user_id = student[1]
        date_of_cleaning_str = student[2]
        status = student[3]
        notification_sent = student[4]

        if not date_of_cleaning_str:
            continue

        date_of_cleaning = datetime.strptime(date_of_cleaning_str.split('.')[0], '%Y-%m-%d %H:%M:%S')
        cleaning_date = date_of_cleaning.date()

        # Условие: дата сегодня, статус не "Штраф/Убрался", и уведомление еще не отправлено
        if cleaning_date == today and status not in ('Ожидает подтверждения', 'Штраф', 'Убрался') and notification_sent == 0:
            try:
                user_ids = [uid.strip() for uid in str(user_id).split(',') if uid.strip().isdigit()]
                for uid in user_ids:
                    await application.bot.send_message(
                        chat_id=int(uid),
                        text="Напоминание: сегодня вам нужно убраться. Пожалуйста, пришлите до 3 фотографий уборки."
                    )
                # Ставим статус и помечаем, что уведомление отправлено
                cursor.execute("UPDATE students SET status = 'Ожидает подтверждения', notification_sent = 1 WHERE id = ?", (student_id,))
            except Exception as e:
                print(f"Ошибка при отправке напоминания студенту {user_id}: {e}")

    conn.commit()
    conn.close()




# Функция-обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Добрый день, я бот, помогающий вам не забыть об уборке. Пожалуйста, укажите номер вашей комнаты, просто отправив его."
    )


# Функция-обработчик текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()

    # Если регистрация уже завершена — ничего не делать
    if context.user_data.get('registration_complete'):
        return

    # Если номер комнаты еще не указан
    if 'room_number' not in context.user_data:
        print(f"Получен номер комнаты: {text} от пользователя с ID: {user_id}")
        context.user_data['room_number'] = text

        # Запрашиваем старосту
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT full_name FROM head_of_hostel")
        heads = cursor.fetchall()
        conn.close()

        if heads:
            keyboard = [[InlineKeyboardButton(head[0], callback_data=head[0]) for head in heads]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("Пожалуйста, выберите вашего старосту:", reply_markup=reply_markup)
        else:
            await update.message.reply_text("Нет доступных старост.")

    # Если номер комнаты указан и староста выбран — это ФИО
    elif 'selected_head' in context.user_data:
        await handle_full_name(update, context)

    else:
        await update.message.reply_text("Сначала выберите старосту, затем введите ваше ФИО.")


# Функция-обработчик выбора старосты
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    selected_head = query.data
    # Сохраняем выбранного старосту
    context.user_data['selected_head'] = selected_head

    room_number = context.user_data.get('room_number')
    print(f"Выбранная комната: {room_number}, староста: {selected_head}")

    if room_number:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM students WHERE number_of_room = ?", (room_number,))
        existing_record = cursor.fetchone()

        if existing_record:
            user_ids = existing_record[1]
            new_user_ids = f"{user_ids},{update.effective_user.id}"
            cursor.execute("UPDATE students SET user_id = ?, head = ? WHERE number_of_room = ?",
                           (new_user_ids, selected_head, room_number))
        else:
            full_name = context.user_data.get('full_name', 'Не указано')
            cursor.execute("INSERT INTO students (user_id, full_name, head, number_of_room, notification_sent) VALUES (?, ?, ?, ?, ?)",
                           (update.effective_user.id, full_name, selected_head, room_number, 0))
        conn.commit()
        conn.close()

        await query.edit_message_text(
            text=f"Вы выбрали старосту: {selected_head}. Пожалуйста, введите ваше ФИО."
        )
    else:
        await query.edit_message_text(text="Сначала укажите номер комнаты.")



# Функция-обработчик ФИО
async def handle_full_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    full_name = update.message.text.strip()
    room_number = context.user_data.get('room_number')
    selected_head = context.user_data.get('selected_head')

    print(f"Получено ФИО: {full_name} от пользователя с ID: {user_id}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM students WHERE number_of_room = ? AND head = ?", (room_number, selected_head))
    existing_record = cursor.fetchone()

    if existing_record:
        user_ids = existing_record[1]
        new_user_ids = f"{user_ids},{user_id}"
        existing_full_name = existing_record[2]
        updated_full_name = f"{existing_full_name}, {full_name}"
        cursor.execute("UPDATE students SET user_id = ?, full_name = ? WHERE number_of_room = ? AND head = ?",
                       (new_user_ids, updated_full_name, room_number, selected_head))
    else:
        cursor.execute("INSERT INTO students (user_id, full_name, head, number_of_room) VALUES (?, ?, ?, ?)",
                       (user_id, full_name, selected_head, room_number))

    conn.commit()
    conn.close()

    # Очистка контекста, чтобы бот не спрашивал заново старосту
    context.user_data.clear()
    context.user_data['registration_complete'] = True

    await update.message.reply_text(
        f"Поздравляю! Вы успешно зарегистрировались. Теперь вам будут приходить напоминания об уборках."
    )


# Функция-обработчик получения фото

async def handle_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id  # Получаем ID пользователя, который отправил фото
    if update.message.photo:  # Проверяем, что сообщение содержит фотографию
        # Получаем ID последнего загруженного фото
        photo_file = await update.message.photo[-1].get_file()

        # Используем правильный метод для загрузки фото
        photo_data = await photo_file.download_as_bytearray()

        # Сохраняем фото в БД
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Получаем все user_id, которые могут быть у этого пользователя
        cursor.execute("SELECT id, status FROM students WHERE user_id LIKE ?", (f"%{user_id}%",))
        users = cursor.fetchall()

        # Флаг для проверки статуса
        waiting_for_confirmation = False
        student_id_to_save = None

        # Проверяем статус для каждого user_id
        for user in users:
            student_id = user[0]  # ID студента
            status = user[1]
            if status == 'Ожидает подтверждения':
                waiting_for_confirmation = True
                student_id_to_save = student_id  # Сохраняем ID студента для дальнейшего использования
                break

        if waiting_for_confirmation and student_id_to_save is not None:
            # Добавляем фото в таблицу
            cursor.execute("INSERT INTO photo (student_id, photo) VALUES (?, ?)", (student_id_to_save, photo_data))
            conn.commit()  # Не забываем зафиксировать изменения
            await update.message.reply_text("Спасибо за фото уборки! Ожидайте, пока староста их подтвердит.")
        else:
            await update.message.reply_text("У вас нет активного запроса на подтверждение уборки.")

        conn.close()


# Функция для отправки сообщения об успешной уборке
async def check_cleaning_status(application):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT id, user_id, status, notification_sent FROM students")
    students = cursor.fetchall()

    for student in students:
        student_id = student[0]
        user_id = student[1]
        status = student[2]
        notification_sent = student[3]

        # Только если статус 'Убрался' и уведомление еще не отправлено
        if status == 'Убрался' and notification_sent == 0:
            try:
                user_ids = [uid.strip() for uid in user_id.split(',') if uid.strip().isdigit()]
                for uid in user_ids:
                    await application.bot.send_message(
                        chat_id=int(uid),
                        text="Ваш староста подтвердил уборку. Спасибо за соблюдение чистоты!"
                    )
                    print(f"Уведомление отправлено пользователю с ID: {uid}")

                # После отправки помечаем как отправленное
                cursor.execute("UPDATE students SET notification_sent = 1 WHERE id = ?", (student_id,))
            except Exception as e:
                print(f"Ошибка при отправке уведомления student_id={student_id}: {e}")

    conn.commit()
    conn.close()






# Основная функция для запуска бота
def main():
    token = get_bot_token()
    bot_application = ApplicationBuilder().token(token).build()  # Создание приложения



    # Добавляем обработчики и запускаем бот
    bot_application.add_handler(CommandHandler("start", start))
    bot_application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    bot_application.add_handler(CallbackQueryHandler(button))
    bot_application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_full_name))
    bot_application.add_handler(MessageHandler(filters.PHOTO, handle_photos))

    # Запускаем отправку уведомлений о уборке
    scheduler = AsyncIOScheduler()  # Используем AsyncIOScheduler
    scheduler.add_job(send_reminders, 'interval', seconds=1, args=[bot_application])
    scheduler.add_job(check_cleaning_status, 'interval', seconds=5, args=[bot_application])
    # Проверяем каждую секунду и 5
    scheduler.start()

    bot_application.run_polling()  # Запуск бота

if __name__ == '__main__':
    main()

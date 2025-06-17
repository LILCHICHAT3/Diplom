from flask_sqlalchemy import SQLAlchemy


class DatabaseManager:
    def __init__(self, db, model, head_of_hostel, students):
        self.db = db
        self.model = model
        self.head_of_hostel = head_of_hostel
        self.students = students

    def get_heads_of_hostel(self):
        return self.head_of_hostel.query.all()  # Получаем всех старост из таблицы

    def add_or_update_dormitory(self, penalty_days, time_cleaning, key, dormitories):
        admin_role = self.model.query.first()

        admin_role.key = key
        admin_role.time_cleaning = time_cleaning
        admin_role.penalty_days = penalty_days
        admin_role.dormitory = ','.join(dormitories)
        print(admin_role.dormitory)  # Сохраняем все общежития в одну строку
        print("ff", admin_role.time_cleaning)
        self.db.session.commit()

    def get_dormitories(self):
        admin_role = self.model.query.first()
        return admin_role.dormitory.split(',') if admin_role else []

    def delete_dormitory(self, dormitory_name):
        admin_role = self.model.query.first()
        if admin_role:
            dormitories = admin_role.dormitory.split(',')
            if dormitory_name in dormitories:
                dormitories.remove(dormitory_name)
                admin_role.dormitory = ','.join(dormitories)
                self.db.session.commit()

    def delete_head_and_students(self, head_id):
        head = self.head_of_hostel.query.get(head_id)
        if head:
            # Удаляем студентов, у которых head совпадает с ФИО старосты
            self.students.query.filter_by(head=head.full_name).delete()

            # Удаляем самого старосту
            self.db.session.delete(head)
            self.db.session.commit()

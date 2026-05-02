# services/parser_service.py
import requests
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from database.schema import (
    Student, Department, Speciality, Profile, StudentApplication,
    StudyLevel, StudyForm, StudyBasis,
    ApplicationStatus, StudentStatus, ContactStatus, PriorContact
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Конфигурация ---
API_URL = "https://lka.isu.ru/x/getProcessor"

# Правильные заголовки из браузера
HEADERS = {
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
    'Referer': 'https://isu.ru/',
    'User-Agent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Mobile Safari/537.36',
    'sec-ch-ua': '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
    'sec-ch-ua-mobile': '?1',
    'sec-ch-ua-platform': '"Android"',
}

# Конфигурация групп для парсинга
GROUPS_CONFIG = [
    {
        "uid": "8d51d4c6-134e-11f0-8122-82761dd90eed",
        "name": "Разработка",
        "department_name": "Информатика и вычислительная техника",
        "speciality_name": "Прикладная информатика",
        "profile_name": "Прикладная информатика в разработке",
        "study_level": "Бакалавриат",
        "study_form": "Очная",
        "study_basis": "Бюджетная основа"
    },
    {
        "uid": "8d51d4dd-134e-11f0-8122-82761dd90eed",
        "name": "Дизайн",
        "department_name": "Факультет бизнес-коммуникаций и информатики",
        "speciality_name": "Прикладная информатика",
        "profile_name": "Прикладная информатика в дизайне",
        "study_level": "Бакалавриат",
        "study_form": "Очная",
        "study_basis": "Бюджетная основа"
    }
]


class ParserService:
    """Сервис для парсинга данных абитуриентов - поддержка множественных заявлений"""

    def __init__(self, db: Session):
        self.db = db

        # Статистика по всем группам
        self.all_stats = {
            "groups": {},
            "total": {
                "students_updated": 0,
                "students_skipped": 0,
                "students_created": 0,
                "errors": 0
            }
        }

    def _get_or_create_department(self, department_name: str, faculty_name: str = None) -> Optional[Department]:
        """Получает или создает направление"""
        department = self.db.query(Department).filter(
            Department.name == department_name
        ).first()

        if not department:
            logger.info(f"➕ Создание нового направления: {department_name}")
            department = Department(
                code=department_name[:10].upper().replace(" ", "_"),
                name=department_name,
                faculty=faculty_name or department_name
            )
            self.db.add(department)
            self.db.flush()
            logger.info(f"✅ Создано направление с ID: {department.id}")

        return department

    def _get_or_create_speciality(self, speciality_name: str, department_id: int, code: str = None) -> Optional[
        Speciality]:
        """Получает или создает специальность"""
        speciality = self.db.query(Speciality).filter(
            Speciality.name == speciality_name,
            Speciality.department_id == department_id
        ).first()

        if not speciality:
            logger.info(f"➕ Создание новой специальности: {speciality_name}")
            speciality = Speciality(
                code=code or speciality_name[:10].upper().replace(" ", "_"),
                name=speciality_name,
                department_id=department_id
            )
            self.db.add(speciality)
            self.db.flush()
            logger.info(f"✅ Создана специальность с ID: {speciality.id}")

        return speciality

    def _get_or_create_profile(self, profile_name: str, speciality_id: int) -> Optional[Profile]:
        """Получает или создает профиль"""
        profile = self.db.query(Profile).filter(
            Profile.name == profile_name,
            Profile.speciality_id == speciality_id
        ).first()

        if not profile:
            logger.info(f"➕ Создание нового профиля: {profile_name}")
            profile = Profile(
                name=profile_name,
                speciality_id=speciality_id,
                code=profile_name[:10].upper().replace(" ", "_")
            )
            self.db.add(profile)
            self.db.flush()
            logger.info(f"✅ Создан профиль с ID: {profile.id}")

        return profile

    def fetch_group_data(self, group_uid: str) -> Optional[Dict[str, Any]]:
        """Получает данные для конкурсной группы"""
        payload = {
            "processor": "rating_getListAbiturients",
            "КонкурснаяГруппа": {
                "type": "CatalogRef",
                "catalog": "КонкурсныеГруппы",
                "uid": group_uid
            }
        }

        try:
            logger.info(f"📤 Запрос для группы {group_uid}")

            json_payload = json.dumps(payload, ensure_ascii=False)
            response = requests.post(
                API_URL,
                headers=HEADERS,
                data=json_payload.encode('utf-8'),
                timeout=30
            )

            response.raise_for_status()
            data = response.json()

            if data.get('state') == 'ok':
                logger.info(f"✅ Получено {len(data.get('data', []))} абитуриентов")
                return data
            else:
                logger.error(f"❌ Ошибка API: {data.get('state')}")
                return None

        except Exception as e:
            logger.error(f"❌ Ошибка запроса: {e}")
            return None

    def map_application_status(self, status_name: str) -> Optional[ApplicationStatus]:
        """Маппинг статуса заявления"""
        mapping = {
            "Подано": ApplicationStatus.PENDING,
            "Принято": ApplicationStatus.ACCEPTED,
            "Отказано": ApplicationStatus.REJECTED,
            "Оплачено": ApplicationStatus.PAID,
            "Зачислен": ApplicationStatus.ACCEPTED
        }
        return mapping.get(status_name)

    def _get_full_name(self, item: Dict) -> str:
        """Извлекает полное имя из данных API"""
        # Пробуем разные варианты
        name = item.get('ФИО')
        if name:
            return name

        name = item.get('АбитуриентФИО')
        if name:
            return name

        # Составляем из частей
        last_name = item.get('Фамилия', '')
        first_name = item.get('Имя', '')
        middle_name = item.get('Отчество', '')

        if last_name or first_name:
            return f"{last_name} {first_name} {middle_name}".strip()

        return f"Студент {item.get('Абитуриент', '')}"

    def update_or_create_application(self, item: Dict, group_config: Dict, student: Student) -> Optional[
        StudentApplication]:
        """Обновляет или создает заявление студента на конкретную специальность"""
        try:
            # Получаем или создаем связанные записи
            department = self._get_or_create_department(
                group_config['department_name'],
                group_config.get('faculty_name')
            )

            speciality = self._get_or_create_speciality(
                group_config['speciality_name'],
                department.id
            )

            profile = self._get_or_create_profile(
                group_config['profile_name'],
                speciality.id
            )

            # Ищем существующее заявление
            application = self.db.query(StudentApplication).filter(
                StudentApplication.student_id == student.id,
                StudentApplication.department_id == department.id,
                StudentApplication.speciality_id == speciality.id,
                StudentApplication.profile_id == profile.id
            ).first()

            is_new = False
            if not application:
                logger.debug(f"   ➕ Создание заявления на {group_config['profile_name']}")
                is_new = True
                application = StudentApplication(
                    student_id=student.id,
                    department_id=department.id,
                    speciality_id=speciality.id,
                    profile_id=profile.id
                )
                self.db.add(application)
                self.db.flush()

            # Обновляем конкурсную информацию
            # Место в конкурсе
            position = item.get('Место') or item.get('Место в конкурсе')
            if position is not None:
                try:
                    application.position = int(position)
                except (ValueError, TypeError):
                    pass

            # Приоритет
            priority = item.get('Приоритет')
            if priority is not None:
                try:
                    application.priority = int(priority)
                except (ValueError, TypeError):
                    pass

            # Участие в конкурсе
            participation = item.get('Участие в конкурсе')
            if participation is not None:
                application.participation = participation == 'Да'

            # Основной конкурс
            is_main_contest = item.get('ОсновнойКонкурс')
            if is_main_contest is not None:
                application.is_main_contest = is_main_contest == 'Да'

            # Статус заявления
            status_data = item.get('СостояниеЗаявления', {})
            status_name = status_data.get('name') if isinstance(status_data, dict) else status_data
            if not status_name:
                status_name = item.get('Состояние заявления')

            app_status = self.map_application_status(status_name)
            if app_status:
                application.application_status = app_status

            # Согласие на зачисление
            consent = item.get('Согласие на зачисление') or item.get('СогласиеНаЗачисление')
            application.consent_status = consent == 'Да' if consent else False

            # Сумма баллов
            total_score = None
            if item.get('СуммаБаллов') is not None:
                total_score = item.get('СуммаБаллов')
            elif item.get('Сумма баллов') is not None:
                total_score = item.get('Сумма баллов')
            elif item.get('БалловЗаВИ') is not None or item.get('БалловЗаИД') is not None:
                exam_score = item.get('БалловЗаВИ', 0)
                id_score = item.get('БалловЗаИД', 0)
                total_score = exam_score + id_score

            if total_score is not None:
                try:
                    application.total_score = int(total_score)
                except (ValueError, TypeError):
                    logger.warning(f"⚠️ Не удалось преобразовать баллы: {total_score}")

            # Дополнительные поля
            application.main_contest_other = item.get('ОсновнойКонкурсДругое')
            application.higher_priority_other = item.get('ВысшийПриоритетДругое')
            application.updated_at = datetime.utcnow()

            return application, is_new

        except Exception as e:
            logger.error(f"❌ Ошибка обработки заявления: {e}")
            import traceback
            traceback.print_exc()
            return None, False

    def update_or_create_student(self, item: Dict, group_config: Dict) -> Optional[Student]:
        """Обновляет существующего или создает нового студента"""
        try:
            # Получаем ID абитуриента
            russian_id = item.get('Абитуриент') or item.get('УникальныйКодПоступающего')
            if not russian_id:
                logger.warning("⚠️ Нет ID абитуриента")
                return None

            # Ищем студента
            student = self.db.query(Student).filter(
                Student.russian_student_id == int(russian_id)
            ).first()

            # Если студент не найден - создаем нового
            is_new_student = False
            if not student:
                logger.info(f"➕ Создание нового студента с ID {russian_id}")
                is_new_student = True
                student = Student(
                    russian_student_id=int(russian_id),
                    full_name=self._get_full_name(item),
                    status=StudentStatus.ACTIVE,
                    contact_status=ContactStatus.NEW
                )
                self.db.add(student)
                self.db.flush()
            else:
                # Обновляем ФИО если оно изменилось
                current_name = self._get_full_name(item)
                if student.full_name != current_name and current_name != f"Студент {russian_id}":
                    student.full_name = current_name

            logger.info(f"{'🆕 Создание' if is_new_student else '🔄 Обновление'} студента ID {russian_id}")

            # Обновляем или создаем заявление на эту специальность
            application, is_new_application = self.update_or_create_application(item, group_config, student)

            if application:
                if is_new_application:
                    logger.debug(f"   ✅ Добавлено заявление на {group_config['profile_name']}")
                else:
                    logger.debug(
                        f"   ✅ Обновлено заявление на {group_config['profile_name']} (место: {application.position})")

            # Обновляем общую информацию студента (если нужно)
            student.imported_at = datetime.utcnow()
            student.updated_at = datetime.utcnow()

            self.db.commit()
            self.db.refresh(student)

            return student, is_new_student

        except Exception as e:
            logger.error(f"❌ Ошибка обработки студента {russian_id if 'russian_id' in locals() else 'unknown'}: {e}")
            import traceback
            traceback.print_exc()
            self.db.rollback()
            return None, False

    def calculate_group_statistics(self, group_config: Dict) -> Dict[str, Any]:
        """Рассчитывает статистику по группе на основе заявлений"""
        try:
            # Получаем department, speciality, profile по названиям
            department = self.db.query(Department).filter(
                Department.name == group_config['department_name']
            ).first()

            if not department:
                return self._empty_statistics()

            speciality = self.db.query(Speciality).filter(
                Speciality.name == group_config['speciality_name'],
                Speciality.department_id == department.id
            ).first()

            if not speciality:
                return self._empty_statistics()

            profile = self.db.query(Profile).filter(
                Profile.name == group_config['profile_name'],
                Profile.speciality_id == speciality.id
            ).first()

            # Базовый запрос - ищем заявления
            query = self.db.query(StudentApplication).filter(
                StudentApplication.department_id == department.id,
                StudentApplication.speciality_id == speciality.id
            )

            if profile:
                query = query.filter(StudentApplication.profile_id == profile.id)

            applications = query.all()

            # Подсчет статистики
            total_applications = len(applications)

            # Подавшие документы (статус не PENDING или есть баллы)
            applications_submitted = len([
                a for a in applications
                if a.application_status != ApplicationStatus.PENDING or a.total_score
            ])

            # Поступившие (зачисленные)
            enrolled = len([a for a in applications if a.application_status == ApplicationStatus.ACCEPTED])

            # Баллы
            scores = [a.total_score for a in applications if a.total_score and a.total_score > 0]
            avg_score = sum(scores) / len(scores) if scores else 0
            min_score = min(scores) if scores else 0
            max_score = max(scores) if scores else 0

            return {
                "total_applications": total_applications,
                "applications_submitted": applications_submitted,
                "enrolled": enrolled,
                "average_score": round(avg_score, 2),
                "min_score": min_score,
                "max_score": max_score
            }

        except Exception as e:
            logger.error(f"❌ Ошибка расчета статистики: {e}")
            return self._empty_statistics()

    def _empty_statistics(self) -> Dict[str, Any]:
        """Пустая статистика"""
        return {
            "total_applications": 0,
            "applications_submitted": 0,
            "enrolled": 0,
            "average_score": 0,
            "min_score": 0,
            "max_score": 0
        }

    def run_parser(self) -> Dict:
        """Запускает парсинг для всех настроенных групп"""
        logger.info("=" * 60)
        logger.info("🚀 ЗАПУСК ПАРСЕРА АБИТУРИЕНТОВ")
        logger.info("=" * 60)

        for group_config in GROUPS_CONFIG:
            logger.info(f"\n📌 Парсинг группы: {group_config['name']}")
            logger.info(f"   Профиль: {group_config['profile_name']}")
            logger.info("-" * 40)

            group_stats = {
                "students_updated": 0,
                "students_created": 0,
                "students_skipped": 0,
                "applications_created": 0,
                "applications_updated": 0,
                "errors": 0
            }

            # Получаем данные
            data = self.fetch_group_data(group_config['uid'])
            if not data or 'data' not in data:
                logger.error(f"❌ Нет данных для группы {group_config['name']}")
                continue

            students_data = data['data']
            logger.info(f"📊 В API: {len(students_data)} абитуриентов")

            # Обрабатываем каждого студента
            for i, item in enumerate(students_data, 1):
                try:
                    student, is_new = self.update_or_create_student(item, group_config)
                    if student:
                        if is_new:
                            group_stats["students_created"] += 1
                        else:
                            group_stats["students_updated"] += 1
                    else:
                        group_stats["students_skipped"] += 1
                except Exception as e:
                    logger.error(f"❌ Ошибка при обработке студента: {e}")
                    group_stats["errors"] += 1
                    self.db.rollback()

                if i % 50 == 0:
                    logger.info(f"⏳ Обработано {i}/{len(students_data)}...")

            # Рассчитываем статистику по группе
            group_statistics = self.calculate_group_statistics(group_config)

            # Сохраняем статистику группы
            self.all_stats["groups"][group_config['name']] = {
                "config": group_config,
                "parser_stats": group_stats,
                "statistics": group_statistics
            }

            # Обновляем общую статистику
            self.all_stats["total"]["students_updated"] += group_stats["students_updated"]
            self.all_stats["total"]["students_created"] += group_stats["students_created"]
            self.all_stats["total"]["students_skipped"] += group_stats["students_skipped"]
            self.all_stats["total"]["errors"] += group_stats["errors"]

            # Выводим статистику по группе
            logger.info(f"\n📊 СТАТИСТИКА ГРУППЫ '{group_config['name']}':")
            logger.info(f"   Создано студентов: {group_stats['students_created']}")
            logger.info(f"   Обновлено студентов: {group_stats['students_updated']}")
            logger.info(f"   Пропущено: {group_stats['students_skipped']}")
            logger.info(f"   Ошибок: {group_stats['errors']}")
            logger.info(f"\n📈 АНАЛИТИКА ПО ГРУППЕ:")
            logger.info(f"   Всего заявлений: {group_statistics['total_applications']}")
            logger.info(f"   Подало документы: {group_statistics['applications_submitted']}")
            logger.info(f"   Поступило (зачислено): {group_statistics['enrolled']}")
            logger.info(f"   Средний балл: {group_statistics['average_score']}")
            logger.info(f"   Минимальный балл: {group_statistics['min_score']}")
            logger.info(f"   Максимальный балл: {group_statistics['max_score']}")

            # Коммитим изменения после каждой группы
            self.db.commit()

        # Итоговая статистика
        logger.info("\n" + "=" * 60)
        logger.info("📊 ИТОГОВАЯ СТАТИСТИКА ПО ВСЕМ ГРУППАМ:")
        logger.info(f"   Всего создано студентов: {self.all_stats['total']['students_created']}")
        logger.info(f"   Всего обновлено студентов: {self.all_stats['total']['students_updated']}")
        logger.info(f"   Всего пропущено: {self.all_stats['total']['students_skipped']}")
        logger.info(f"   Всего ошибок: {self.all_stats['total']['errors']}")
        logger.info("=" * 60)

        return self.all_stats


def run_parser_once():
    """Запуск парсера для тестирования"""
    from database.database import SessionLocal

    db = SessionLocal()
    try:
        parser = ParserService(db)
        stats = parser.run_parser()
        return stats
    finally:
        db.close()


if __name__ == "__main__":
    run_parser_once()
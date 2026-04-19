# services/parser_service.py
import requests
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from database.schema import (
    Student, Department, Speciality, Profile,
    StudyLevel, StudyForm, StudyBasis,
    ApplicationStatus, StudentStatus, ContactStatus
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Конфигурация ---
API_URL = "https://pk.isu.ru/x/getProcessor"

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

# UID конкурсной группы из API
GROUP_UID = "8d51d4dd-134e-11f0-8122-82761dd90eed"


class ParserService:
    """Сервис для парсинга данных абитуриентов - ТОЛЬКО ОБНОВЛЕНИЕ"""

    def __init__(self, db: Session):
        self.db = db
        self.stats = {
            "students_updated": 0,
            "students_skipped": 0,
            "errors": 0
        }

        # Данные о группе будут загружены из БД
        self.group_info = None
        self._load_group_info()

    def _load_group_info(self):
        """Загружает информацию о группе из базы данных по названиям"""
        try:
            # Ищем направление по названию
            department = self.db.query(Department).filter(
                Department.name == "Информатика и вычислительная техника"
            ).first()

            if not department:
                logger.error("❌ Направление не найдено в БД")
                # Попробуем найти любое направление
                department = self.db.query(Department).first()
                if not department:
                    logger.error("❌ В БД нет ни одного направления")
                    return

            # Ищем специальность по названию
            speciality = self.db.query(Speciality).filter(
                Speciality.name.like("%Прикладная информатика%"),
                Speciality.department_id == department.id
            ).first()

            if not speciality:
                logger.error("❌ Специальность не найдена в БД")
                # Возьмем любую специальность этого направления
                speciality = self.db.query(Speciality).filter(
                    Speciality.department_id == department.id
                ).first()
                if not speciality:
                    logger.error("❌ В БД нет ни одной специальности")
                    return

            # Ищем профиль
            profile = self.db.query(Profile).filter(
                Profile.speciality_id == speciality.id
            ).first()

            self.group_info = {
                "name": f"{speciality.code if speciality.code else ''} {speciality.name}",
                "department_id": department.id,
                "department_name": department.name,
                "speciality_id": speciality.id,
                "speciality_name": speciality.name,
                "profile_id": profile.id if profile else None,
                "profile_name": profile.name if profile else None,
                "faculty_name": department.faculty
            }

            logger.info(f"✅ Загружена информация о группе из БД:")
            logger.info(f"   Направление: {department.name} (ID: {department.id})")
            logger.info(f"   Специальность: {speciality.name} (ID: {speciality.id})")
            if profile:
                logger.info(f"   Профиль: {profile.name} (ID: {profile.id})")

        except Exception as e:
            logger.error(f"❌ Ошибка загрузки информации о группе: {e}")

    def fetch_group_data(self) -> Optional[Dict[str, Any]]:
        """Получает данные для конкурсной группы"""
        payload = {
            "processor": "rating_getListAbiturients",
            "КонкурснаяГруппа": {
                "type": "CatalogRef",
                "catalog": "КонкурсныеГруппы",
                "uid": GROUP_UID
            }
        }

        try:
            logger.info(f"📤 Запрос для группы {GROUP_UID}")

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

    def map_study_level(self, level_name: str) -> Optional[StudyLevel]:
        """Маппинг уровня подготовки - возвращает Enum"""
        mapping = {
            "Бакалавриат": StudyLevel.BACHELOR,
            "Магистратура": StudyLevel.MASTER,
            "Специалитет": StudyLevel.SPECIALIST,
            "Аспирантура": StudyLevel.PHD
        }
        return mapping.get(level_name)

    def map_study_form(self, form_name: str) -> Optional[StudyForm]:
        """Маппинг формы обучения - возвращает Enum"""
        mapping = {
            "Очная": StudyForm.FULL_TIME,
            "Очно-заочная": StudyForm.PART_TIME,
            "Заочная": StudyForm.CORRESPONDENCE
        }
        return mapping.get(form_name)

    def map_study_basis(self, basis_name: str) -> Optional[StudyBasis]:
        """Маппинг основания - возвращает Enum"""
        mapping = {
            "Бюджетная основа": StudyBasis.BUDGET,
            "Платная основа": StudyBasis.PAID,
            "Целевая основа": StudyBasis.TARGET
        }
        return mapping.get(basis_name)

    def map_application_status(self, status_name: str) -> Optional[ApplicationStatus]:
        """Маппинг статуса заявления - возвращает Enum ApplicationStatus"""
        mapping = {
            "Подано": ApplicationStatus.PENDING,
            "Принято": ApplicationStatus.ACCEPTED,
            "Отказано": ApplicationStatus.REJECTED,
            "Оплачено": ApplicationStatus.PAID,
            "Зачислен": ApplicationStatus.ACCEPTED
        }
        return mapping.get(status_name)

    def update_student(self, item: Dict) -> Optional[Student]:
        try:
            if not self.group_info:
                logger.error("❌ Нет информации о группе")
                return None
            russian_id = item.get('Идентификатор') or item.get('Абитуриент') or item.get('УникальныйКодПоступающего')
            if not russian_id:
                logger.warning("⚠️ Нет ID абитуриента")
                return None

            # Ищем студента ТОЛЬКО среди существующих по russian_student_id
            student = self.db.query(Student).filter(
                Student.russian_student_id == int(russian_id)
            ).first()

            # Если студент не найден в БД - пропускаем (не создаем)
            if not student:
                self.stats["students_skipped"] += 1
                logger.debug(f"⏭️ Пропущен студент с ID {russian_id} (нет в БД)")
                return None

            logger.info(f"🔄 Обновление студента ID {russian_id} ({student.full_name})")

            # Обновляем ID из загруженной информации о группе
            student.department_id = self.group_info['department_id']
            student.speciality_id = self.group_info['speciality_id']
            if self.group_info.get('profile_id'):
                student.profile_id = self.group_info['profile_id']

            # Маппинг Enum полей - используем Enum, а не строки
            level_name = item.get('УровеньПодготовки', {}).get('name') if item.get('УровеньПодготовки') else None
            if level_name:
                study_level = self.map_study_level(level_name)
                if study_level:
                    student.study_level = study_level

            form_name = item.get('ФормаОбучения', {}).get('name') if item.get('ФормаОбучения') else None
            if form_name:
                study_form = self.map_study_form(form_name)
                if study_form:
                    student.study_form = study_form

            basis_name = item.get('ОснованиеПоступления', {}).get('name') if item.get('ОснованиеПоступления') else None
            if basis_name:
                study_basis = self.map_study_basis(basis_name)
                if study_basis:
                    student.study_basis = study_basis

            # Позиция и приоритет
            student.position = item.get('Место') or item.get('Место в конкурсе')
            student.priority = item.get('Приоритет')
            student.participation = item.get('Участие в конкурсе') == 'Да' if item.get('Участие в конкурсе') else True

            # Статус заявления
            status_name = item.get('Состояние заявления') or item.get('СостояниеЗаявления', {}).get('name', '')
            app_status = self.map_application_status(status_name)
            if app_status:
                student.application_status = app_status

            # Согласие на зачисление
            consent = item.get('Согласие на зачисление') or item.get('СогласиеНаЗачисление')
            student.consent_status = consent == 'Да' if consent else False

            # Сумма баллов - пробуем разные варианты
            total_score = None

            # Вариант 1: прямое поле "Сумма баллов"
            if item.get('Сумма баллов') is not None:
                total_score = item.get('Сумма баллов')
            # Вариант 2: поле "Баллы"
            elif item.get('Баллы') is not None:
                total_score = item.get('Баллы')
            # Вариант 3: сумма из вступительных испытаний и индивидуальных достижений
            elif item.get('БалловЗаВИ') is not None or item.get('БалловЗаИД') is not None:
                exam_score = item.get('БалловЗаВИ', 0)
                id_score = item.get('БалловЗаИД', 0)
                total_score = exam_score + id_score
            # Вариант 4: из вложенных объектов
            elif item.get('Вступительные испытания') is not None:
                exam_data = item.get('Вступительные испытания')
                if isinstance(exam_data, (int, float)):
                    total_score = exam_data
                elif isinstance(exam_data, dict):
                    total_score = exam_data.get('сумма', 0) or exam_data.get('балл', 0)

            if total_score is not None:
                try:
                    student.total_score = int(total_score)
                except (ValueError, TypeError):
                    logger.warning(f"⚠️ Не удалось преобразовать баллы: {total_score}")

            student.imported_at = datetime.utcnow()
            student.updated_at = datetime.utcnow()

            # Сохраняем сразу для каждого студента
            self.db.commit()
            self.db.refresh(student)

            self.stats["students_updated"] += 1
            logger.info(f"✅ Обновлен студент {russian_id}: место={student.position}, баллы={student.total_score}, "
                        f"department_id={student.department_id}, speciality_id={student.speciality_id}")
            return student

        except Exception as e:
            self.stats["errors"] += 1
            logger.error(f"❌ Ошибка обновления студента {russian_id if 'russian_id' in locals() else 'unknown'}: {e}")
            import traceback
            traceback.print_exc()
            # Откатываем транзакцию при ошибке
            self.db.rollback()
            return None

    def run_parser(self) -> Dict:
        """Запускает парсинг и обновляет ТОЛЬКО существующих студентов"""
        logger.info("=" * 60)
        logger.info("🚀 ЗАПУСК ПАРСЕРА АБИТУРИЕНТОВ")
        logger.info("=" * 60)

        # Проверяем, загружена ли информация о группе
        if not self.group_info:
            logger.error("❌ Не удалось загрузить информацию о группе из БД")
            return self.stats

        logger.info(f"\n📌 Парсинг группы: {self.group_info['name']}")
        logger.info("-" * 40)

        # Получаем данные
        data = self.fetch_group_data()
        if not data or 'data' not in data:
            logger.error(f"❌ Нет данных для группы")
            return self.stats

        students_data = data['data']
        logger.info(f"📊 В API: {len(students_data)} абитуриентов")

        # Обновляем каждого студента
        updated_count = 0
        skipped_count = 0

        for i, item in enumerate(students_data, 1):
            try:
                result = self.update_student(item)
                if result:
                    updated_count += 1
                else:
                    russian_id = item.get('Идентификатор') or item.get('Абитуриент') or item.get(
                        'УникальныйКодПоступающего')
                    if russian_id:
                        exists = self.db.query(Student).filter(
                            Student.russian_student_id == int(russian_id)
                        ).first()
                        if not exists:
                            skipped_count += 1
            except Exception as e:
                logger.error(f"❌ Ошибка при обработке студента: {e}")
                self.stats["errors"] += 1
                self.db.rollback()

            if i % 50 == 0:
                logger.info(f"⏳ Обработано {i}/{len(students_data)}...")

        self.stats["students_updated"] = updated_count
        self.stats["students_skipped"] = skipped_count

        logger.info(f"✅ Обновлено: {updated_count}, Пропущено (нет в БД): {skipped_count}")

        logger.info("\n" + "=" * 60)
        logger.info("📊 СТАТИСТИКА:")
        logger.info(f"   Обновлено студентов: {self.stats['students_updated']}")
        logger.info(f"   Пропущено студентов (нет в БД): {self.stats['students_skipped']}")
        logger.info(f"   Ошибок: {self.stats['errors']}")
        logger.info("=" * 60)

        return self.stats


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
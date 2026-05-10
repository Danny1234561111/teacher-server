# services/parser_service.py
import requests
import json
import logging
from typing import Dict, Any, List, Optional, Set
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
        "name": "Прикладная информатика (разработка ПО)",
        "department_name": "Прикладная информатика",
        "speciality_name": "Прикладная информатика",
        "profile_name": "Прикладная информатика (разработка программного обеспечения)",
        "study_level": StudyLevel.BACHELOR,
        "study_form": StudyForm.FULL_TIME,
        "study_basis": StudyBasis.BUDGET,
        "budget_places": 25,
        "paid_places": 15,
        "target_places": 5,
        "passing_score_2024": 245,
        "faculty_name": "Факультет бизнес-коммуникаций и информатики"
    },
    {
        "uid": "8d51d4dd-134e-11f0-8122-82761dd90eed",
        "name": "Прикладная информатика (дизайн)",
        "department_name": "Прикладная информатика",
        "speciality_name": "Прикладная информатика",
        "profile_name": "Прикладная информатика (дизайн)",
        "study_level": StudyLevel.BACHELOR,
        "study_form": StudyForm.FULL_TIME,
        "study_basis": StudyBasis.BUDGET,
        "budget_places": 20,
        "paid_places": 10,
        "target_places": 3,
        "passing_score_2024": 230,
        "faculty_name": "Факультет бизнес-коммуникаций и информатики"
    }
]


class ParserService:
    """Сервис для парсинга данных абитуриентов"""

    def __init__(self, db: Session):
        self.db = db

        # Статистика по всем группам
        self.all_stats = {
            "groups": {},
            "total": {
                "students_updated": 0,
                "students_skipped": 0,
                "students_created": 0,
                "applications_created": 0,
                "applications_updated": 0,
                "applications_skipped": 0,
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

    def _get_or_create_speciality(self, speciality_name: str, department_id: int, code: str = None) -> Optional[Speciality]:
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
                code=profile_name[:10].upper().replace(" ", "_"),
                study_level=None,
                study_form=None,
                study_basis=None,
                budget_places=0,
                paid_places=0,
                target_places=0
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
        name = item.get('ФИО')
        if name:
            return name

        name = item.get('АбитуриентФИО')
        if name:
            return name

        last_name = item.get('Фамилия', '')
        first_name = item.get('Имя', '')
        middle_name = item.get('Отчество', '')

        if last_name or first_name:
            return f"{last_name} {first_name} {middle_name}".strip()

        return f"Студент {item.get('Абитуриент', '')}"

    def _has_valid_full_name(self, full_name: str) -> bool:
        """Проверяет, является ли ФИО валидным (не "Студент XXX" и не пустое)"""
        if not full_name:
            return False
        if full_name.startswith('Студент'):
            return False
        if len(full_name) < 5:
            return False
        return True

    def _get_exam_scores(self, item: Dict) -> Dict[str, int]:
        """Извлекает баллы ЕГЭ и индивидуальных достижений"""
        scores = {
            'exam_total': 0,
            'id_total': 0,
            'subjects': {}
        }

        for i in range(1, 6):
            subject_key = f'Предмет{i}'
            score_key = f'БаллыПредмет{i}'

            if subject_key in item and score_key in item:
                subject = item[subject_key]
                if isinstance(subject, dict):
                    subject_name = subject.get('name', '')
                else:
                    subject_name = str(subject) if subject else ''

                score = item.get(score_key, 0)
                if subject_name and score > 0:
                    scores['subjects'][subject_name] = score

                    type_key = f'ТипВИ{i}'
                    score_type = item.get(type_key, '')

                    if score_type == 'ЕГЭ':
                        scores['exam_total'] += score
                    elif score_type == 'Индивидуальное достижение':
                        scores['id_total'] += score

        return scores

    def _get_priority_from_item(self, item: Dict) -> Optional[int]:
        """Извлекает приоритет заявления из данных API"""
        priority = item.get('Приоритет')
        if priority is not None:
            try:
                return int(priority)
            except (ValueError, TypeError):
                pass

        priority = item.get('ПриоритетЗаявления')
        if priority is not None:
            try:
                return int(priority)
            except (ValueError, TypeError):
                pass

        return None

    def _is_valid_application(self, item: Dict) -> bool:
        """Проверяет, является ли заявление валидным (не отклонено, не отозвано)"""
        status_data = item.get('СостояниеЗаявления', {})
        status_name = status_data.get('name') if isinstance(status_data, dict) else status_data
        if not status_name:
            status_name = item.get('Состояние заявления')

        invalid_statuses = ['Отказано', 'Отозвано', 'Аннулировано']
        return status_name not in invalid_statuses if status_name else True

    def update_or_create_application(self, item: Dict, group_config: Dict, student_id: int,
                                     priority: Optional[int] = None) -> tuple[Optional[StudentApplication], bool]:
        """Обновляет или создает заявление студента на конкретную специальность"""
        try:
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

            application = self.db.query(StudentApplication).filter(
                StudentApplication.student_id == student_id,
                StudentApplication.department_id == department.id,
                StudentApplication.speciality_id == speciality.id,
                StudentApplication.profile_id == profile.id,
                StudentApplication.study_form == group_config.get('study_form'),
                StudentApplication.study_basis == group_config.get('study_basis'),
            ).first()

            is_new = False
            if not application:
                logger.debug(f"   ➕ Создание заявления на {group_config['profile_name']}")
                is_new = True
                application = StudentApplication(
                    student_id=student_id,
                    department_id=department.id,
                    speciality_id=speciality.id,
                    profile_id=profile.id,
                    study_form=group_config.get('study_form'),
                    study_basis=group_config.get('study_basis'),
                    study_level=group_config.get('study_level'),
                    budget_places_total=group_config.get('budget_places'),
                    paid_places_total=group_config.get('paid_places'),
                    target_places_total=group_config.get('target_places'),
                )
                self.db.add(application)
                self.db.flush()

            if priority is not None:
                application.priority = priority
            else:
                api_priority = self._get_priority_from_item(item)
                if api_priority is not None:
                    application.priority = api_priority

            position = item.get('Место') or item.get('Место в конкурсе')
            if position is not None:
                try:
                    application.position = int(position)
                except (ValueError, TypeError):
                    pass

            participation = item.get('УчаствуетВКонкурсе') or item.get('Участие в конкурсе')
            if participation is not None:
                if isinstance(participation, bool):
                    application.participation = participation
                else:
                    application.participation = participation == 'Да' or participation == True

            is_main_contest = item.get('ОсновнойКонкурс') or item.get('Основной высший приоритет')
            if is_main_contest is not None:
                if isinstance(is_main_contest, bool):
                    application.is_main_contest = is_main_contest
                else:
                    application.is_main_contest = is_main_contest == 'Да'

            status_data = item.get('СостояниеЗаявления', {})
            status_name = status_data.get('name') if isinstance(status_data, dict) else status_data
            if not status_name:
                status_name = item.get('Состояние заявления')

            app_status = self.map_application_status(status_name)
            if app_status:
                application.application_status = app_status

            consent = item.get('СогласиеНаЗачисление') or item.get('Согласие на зачисление')
            application.consent_status = consent == 'Да' if consent else False

            total_score = None
            if item.get('СуммаБаллов') is not None:
                total_score = item.get('СуммаБаллов')
            elif item.get('Сумма баллов') is not None:
                total_score = item.get('Сумма баллов')
            elif item.get('БалловЗаВИ') is not None or item.get('БалловЗаИД') is not None:
                exam_score = item.get('БалловЗаВИ', 0)
                id_score = item.get('БалловЗаИД', 0)
                total_score = exam_score + id_score

            if total_score is None or total_score == 0:
                scores = self._get_exam_scores(item)
                total_score = scores['exam_total'] + scores['id_total']

            if total_score is not None:
                try:
                    application.total_score = int(total_score)
                except (ValueError, TypeError):
                    logger.warning(f"⚠️ Не удалось преобразовать баллы: {total_score}")

            if application.position and application.position > 0:
                if application.study_basis == StudyBasis.BUDGET and application.budget_places_total:
                    if application.position <= application.budget_places_total:
                        application.budget_places_filled = max(
                            application.budget_places_filled or 0,
                            application.position
                        )
                elif application.study_basis == StudyBasis.PAID and application.paid_places_total:
                    if application.position <= application.paid_places_total:
                        application.paid_places_filled = max(
                            application.paid_places_filled or 0,
                            application.position
                        )
                elif application.study_basis == StudyBasis.TARGET and application.target_places_total:
                    if application.position <= application.target_places_total:
                        application.target_places_filled = max(
                            application.target_places_filled or 0,
                            application.position
                        )

            application.main_contest_other = item.get('ОсновнойКонкурсДругое')
            application.higher_priority_other = item.get('ВысшийПриоритетДругое')
            application.updated_at = datetime.utcnow()

            return application, is_new

        except Exception as e:
            logger.error(f"❌ Ошибка обработки заявления: {e}")
            import traceback
            traceback.print_exc()
            return None, False

    def update_or_create_student(self, item: Dict, group_config: Dict) -> tuple[Optional[Student], bool]:
        """Обновляет существующего студента или создает нового с валидным ФИО"""
        try:
            russian_id = item.get('Абитуриент') or item.get('УникальныйКодПоступающего')
            if not russian_id:
                logger.warning("⚠️ Нет ID абитуриента")
                return None, False

            full_name = self._get_full_name(item)
            is_valid_name = self._has_valid_full_name(full_name)

            student = self.db.query(Student).filter(
                Student.russian_student_id == int(russian_id)
            ).first()

            is_new = False

            if not student:
                if not is_valid_name:
                    logger.debug(f"⏭️ Пропуск создания студента ID {russian_id}: невалидное ФИО ('{full_name}')")
                    return None, False

                logger.info(f"➕ Создание нового студента с ID {russian_id}, ФИО: {full_name}")
                is_new = True
                student = Student(
                    russian_student_id=int(russian_id),
                    full_name=full_name,
                    status=StudentStatus.ACTIVE,
                    contact_status=ContactStatus.NEW
                )
                self.db.add(student)
                self.db.flush()
            else:
                if is_valid_name and full_name != student.full_name:
                    logger.info(f"📝 Обновление ФИО студента {russian_id}: '{student.full_name}' -> '{full_name}'")
                    student.full_name = full_name

                if not student.study_level and group_config.get('study_level'):
                    student.study_level = group_config.get('study_level')
                if not student.study_form and group_config.get('study_form'):
                    student.study_form = group_config.get('study_form')
                if not student.study_basis and group_config.get('study_basis'):
                    student.study_basis = group_config.get('study_basis')

            student.imported_at = datetime.utcnow()
            student.updated_at = datetime.utcnow()

            return student, is_new

        except Exception as e:
            logger.error(f"❌ Ошибка обработки студента: {e}")
            import traceback
            traceback.print_exc()
            return None, False

    def process_student_applications(self, student_id: int, student_applications_data: List[tuple]) -> Dict[str, int]:
        """Обрабатывает все заявления студента с учетом приоритетов"""
        stats = {
            "created": 0,
            "updated": 0,
            "skipped": 0
        }

        if not student_applications_data:
            return stats

        student_applications_data.sort(key=lambda x: x[2] if x[2] is not None else 999)

        valid_applications = [
            (item, config, priority)
            for item, config, priority in student_applications_data
            if self._is_valid_application(item)
        ]

        if not valid_applications:
            logger.debug(f"Студент {student_id} не имеет валидных заявлений")
            return stats

        max_applications = 5
        applications_to_process = valid_applications[:max_applications]

        logger.debug(f"Студент {student_id} подает {len(applications_to_process)} заявлений")

        for item, config, priority in applications_to_process:
            application, is_new = self.update_or_create_application(item, config, student_id, priority)
            if application:
                if is_new:
                    stats["created"] += 1
                else:
                    stats["updated"] += 1
            else:
                stats["skipped"] += 1

        processed_profile_ids = set()
        for item, config, _ in applications_to_process:
            department = self.db.query(Department).filter(Department.name == config['department_name']).first()
            if department:
                speciality = self.db.query(Speciality).filter(
                    Speciality.name == config['speciality_name'],
                    Speciality.department_id == department.id
                ).first()
                if speciality:
                    profile = self.db.query(Profile).filter(
                        Profile.name == config['profile_name'],
                        Profile.speciality_id == speciality.id
                    ).first()
                    if profile:
                        processed_profile_ids.add(profile.id)

        old_applications = self.db.query(StudentApplication).filter(
            StudentApplication.student_id == student_id,
            StudentApplication.profile_id.notin_(processed_profile_ids) if processed_profile_ids else True
        ).all()

        for old_app in old_applications:
            logger.debug(f"Удаление неактуального заявления на профиль {old_app.profile_id}")
            self.db.delete(old_app)

        return stats

    def calculate_group_statistics_from_api(self, group_config: Dict, api_data: List[Dict]) -> Dict[str, Any]:
        """Рассчитывает статистику по группе на основе данных из API (всех абитуриентов)"""
        if not api_data:
            return self._empty_statistics()

        total_applications = len(api_data)

        # Подавшие документы (имеют баллы)
        applications_submitted = len([
            item for item in api_data
            if item.get('СуммаБаллов') and int(item.get('СуммаБаллов', 0)) > 0
        ])

        # Зачисленные (статус "Зачислен")
        enrolled = len([
            item for item in api_data
            if item.get('СостояниеЗаявления') == 'Зачислен' or item.get('Состояние заявления') == 'Зачислен'
        ])

        # Сбор баллов
        scores = []
        for item in api_data:
            score = item.get('СуммаБаллов')
            if score:
                try:
                    scores.append(int(score))
                except (ValueError, TypeError):
                    pass

        avg_score = sum(scores) / len(scores) if scores else 0
        min_score = min(scores) if scores else 0
        max_score = max(scores) if scores else 0

        # Бюджетные места
        budget_total = group_config.get('budget_places', 0)

        # Подсчет мест и согласий
        positions = []
        consent_count = 0
        for item in api_data:
            position = item.get('Место') or item.get('Место в конкурсе')
            if position:
                try:
                    positions.append(int(position))
                except (ValueError, TypeError):
                    pass

            consent = item.get('СогласиеНаЗачисление') or item.get('Согласие на зачисление')
            if consent == 'Да':
                consent_count += 1

        # Заполненные места
        filled = max(positions) if positions else 0
        if filled > budget_total:
            filled = budget_total

        # Проходной балл
        passing_score = 0
        if budget_total > 0 and scores:
            # Сортируем абитуриентов по баллам
            sorted_items = sorted(api_data, key=lambda x: int(x.get('СуммаБаллов', 0)) if x.get('СуммаБаллов') else 0, reverse=True)
            if len(sorted_items) >= budget_total:
                last_accepted = sorted_items[budget_total - 1]
                passing_score = int(last_accepted.get('СуммаБаллов', 0)) if last_accepted.get('СуммаБаллов') else 0

        budget_stats = {
            "total": budget_total,
            "filled": filled,
            "free": max(0, budget_total - filled),
            "applicants_in_range": len([p for p in positions if p <= budget_total]),
            "applicants_with_consent": consent_count,
            "passing_score": passing_score
        }

        # Платные места
        paid_total = group_config.get('paid_places', 0)
        paid_stats = {
            "total": paid_total,
            "filled": 0,
            "free": paid_total,
            "applicants_with_consent": 0
        }

        # Целевые места
        target_total = group_config.get('target_places', 0)
        target_stats = {
            "total": target_total,
            "filled": 0,
            "free": target_total,
            "applicants_with_consent": 0
        }

        competition = round(total_applications / max(budget_total, 1), 2) if budget_total > 0 else 0

        return {
            "total_applications": total_applications,
            "applications_submitted": applications_submitted,
            "enrolled": enrolled,
            "average_score": round(avg_score, 2),
            "min_score": min_score,
            "max_score": max_score,
            "budget": budget_stats,
            "paid": paid_stats,
            "target": target_stats,
            "competition": competition,
            "passing_score_current": passing_score,
            "passing_score_last_year": group_config.get('passing_score_2024', 0)
        }

    def calculate_group_statistics(self, group_config: Dict) -> Dict[str, Any]:
        """Рассчитывает статистику по группе (устаревший метод, используйте calculate_group_statistics_from_api)"""
        return self._empty_statistics()

    def _empty_statistics(self) -> Dict[str, Any]:
        """Пустая статистика"""
        return {
            "total_applications": 0,
            "applications_submitted": 0,
            "enrolled": 0,
            "average_score": 0,
            "min_score": 0,
            "max_score": 0,
            "budget": {"total": 0, "filled": 0, "free": 0, "applicants_in_range": 0, "applicants_with_consent": 0,
                       "passing_score": 0},
            "paid": {"total": 0, "filled": 0, "free": 0, "applicants_with_consent": 0},
            "target": {"total": 0, "filled": 0, "free": 0, "applicants_with_consent": 0},
            "competition": 0,
            "passing_score_current": 0,
            "passing_score_last_year": 0
        }

    def get_students_by_criteria(self, study_form: StudyForm = None, study_basis: StudyBasis = None) -> List[Student]:
        """Получает студентов, подавших заявления с определенной формой/основой"""
        query = self.db.query(Student).join(StudentApplication)

        if study_form:
            query = query.filter(StudentApplication.study_form == study_form)
        if study_basis:
            query = query.filter(StudentApplication.study_basis == study_basis)

        return query.distinct().all()

    def get_applications_by_form_and_basis(self, study_form: StudyForm = None, study_basis: StudyBasis = None) -> List[StudentApplication]:
        """Получает заявления по форме обучения и основе"""
        query = self.db.query(StudentApplication)

        if study_form:
            query = query.filter(StudentApplication.study_form == study_form)
        if study_basis:
            query = query.filter(StudentApplication.study_basis == study_basis)

        return query.all()

    def run_parser(self) -> Dict:
        """Запускает парсинг для всех настроенных групп"""
        logger.info("=" * 60)
        logger.info("🚀 ЗАПУСК ПАРСЕРА АБИТУРИЕНТОВ")
        logger.info("=" * 60)

        # Сначала собираем все данные со всех групп
        all_groups_data = []
        for group_config in GROUPS_CONFIG:
            logger.info(f"\n📌 Получение данных группы: {group_config['name']}")
            data = self.fetch_group_data(group_config['uid'])
            if data and 'data' in data:
                all_groups_data.append({
                    "config": group_config,
                    "data": data['data']
                })
                logger.info(f"📊 Получено {len(data['data'])} абитуриентов")
            else:
                logger.error(f"❌ Нет данных для группы {group_config['name']}")

        if not all_groups_data:
            logger.error("❌ Нет данных ни по одной группе")
            return self.all_stats

        # Сохраняем API данные для последующего расчета статистики
        api_data_by_group = {}
        for group_data in all_groups_data:
            group_config = group_data['config']
            api_data_by_group[group_config['name']] = group_data['data']

        # Группируем заявления по студентам
        students_applications = {}

        for group_data in all_groups_data:
            group_config = group_data['config']
            for item in group_data['data']:
                student_id = item.get('Абитуриент') or item.get('УникальныйКодПоступающего')
                if not student_id:
                    continue

                if student_id not in students_applications:
                    students_applications[student_id] = []

                priority = self._get_priority_from_item(item)
                students_applications[student_id].append((item, group_config, priority))

        logger.info(f"\n📊 Найдено {len(students_applications)} уникальных абитуриентов")

        # Обрабатываем каждого студента
        for student_idx, (student_russian_id, applications_data) in enumerate(students_applications.items(), 1):
            try:
                logger.debug(f"\n🔄 Обработка студента {student_idx}/{len(students_applications)}: ID {student_russian_id}")

                first_item = applications_data[0][0]
                first_config = applications_data[0][1]

                student, is_new = self.update_or_create_student(first_item, first_config)

                if student:
                    if is_new:
                        self.all_stats["total"]["students_created"] += 1
                    else:
                        self.all_stats["total"]["students_updated"] += 1

                    app_stats = self.process_student_applications(student.id, applications_data)

                    self.all_stats["total"]["applications_created"] += app_stats["created"]
                    self.all_stats["total"]["applications_updated"] += app_stats["updated"]
                    self.all_stats["total"]["applications_skipped"] += app_stats["skipped"]

                    self.db.commit()
                else:
                    self.all_stats["total"]["students_skipped"] += 1

            except Exception as e:
                logger.error(f"❌ Ошибка при обработке студента {student_russian_id}: {e}")
                import traceback
                traceback.print_exc()
                self.all_stats["total"]["errors"] += 1
                self.db.rollback()

        # Рассчитываем статистику по каждой группе на основе API данных (всех абитуриентов)
        for group_config in GROUPS_CONFIG:
            api_data = api_data_by_group.get(group_config['name'], [])
            group_statistics = self.calculate_group_statistics_from_api(group_config, api_data)

            self.all_stats["groups"][group_config['name']] = {
                "config": group_config,
                "statistics": group_statistics,
                "total_in_api": len(api_data)
            }

            logger.info(f"\n📊 СТАТИСТИКА ГРУППЫ '{group_config['name']}':")
            logger.info(f"   Всего абитуриентов в API: {len(api_data)}")
            logger.info(f"   Всего заявлений: {group_statistics['total_applications']}")
            logger.info(f"   Подало документы: {group_statistics['applications_submitted']}")
            logger.info(f"   Поступило (зачислено): {group_statistics['enrolled']}")
            logger.info(f"   Средний балл: {group_statistics['average_score']}")
            logger.info(f"   Минимальный балл: {group_statistics['min_score']}")
            logger.info(f"   Максимальный балл: {group_statistics['max_score']}")
            logger.info(f"\n💰 БЮДЖЕТНЫЕ МЕСТА:")
            logger.info(f"   Всего: {group_statistics['budget']['total']}")
            logger.info(f"   Заполнено: {group_statistics['budget']['filled']}")
            logger.info(f"   Свободно: {group_statistics['budget']['free']}")
            logger.info(f"   Подали согласие: {group_statistics['budget']['applicants_with_consent']}")
            logger.info(f"   Текущий проходной: {group_statistics['budget']['passing_score']}")
            logger.info(f"   Проходной прошлый год: {group_statistics['passing_score_last_year']}")
            logger.info(f"   Конкурс: {group_statistics['competition']} чел/место")

        logger.info("\n" + "=" * 60)
        logger.info("📊 ИТОГОВАЯ СТАТИСТИКА ПО ВСЕМ ГРУППАМ:")
        logger.info(f"   Всего создано студентов: {self.all_stats['total']['students_created']}")
        logger.info(f"   Всего обновлено студентов: {self.all_stats['total']['students_updated']}")
        logger.info(f"   Всего пропущено студентов: {self.all_stats['total']['students_skipped']}")
        logger.info(f"   Создано заявлений: {self.all_stats['total']['applications_created']}")
        logger.info(f"   Обновлено заявлений: {self.all_stats['total']['applications_updated']}")
        logger.info(f"   Пропущено заявлений: {self.all_stats['total']['applications_skipped']}")
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
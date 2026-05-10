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
        "name": "Прикладная информатика (разработка ПО)",
        "department_name": "Факультет бизнес-коммуникаций и информатики",
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
        "department_name": "Факультет бизнес-коммуникаций и информатики",
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

    def update_or_create_application(self, item: Dict, group_config: Dict, student: Student) -> tuple[
        Optional[StudentApplication], bool]:
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
                StudentApplication.student_id == student.id,
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
                    student_id=student.id,
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

            position = item.get('Место') or item.get('Место в конкурсе')
            if position is not None:
                try:
                    application.position = int(position)
                except (ValueError, TypeError):
                    pass

            priority = item.get('Приоритет')
            if priority is not None:
                try:
                    application.priority = int(priority)
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
        """Обновляет существующего или создает нового студента"""
        try:
            russian_id = item.get('Абитуриент') or item.get('УникальныйКодПоступающего')
            if not russian_id:
                logger.warning("⚠️ Нет ID абитуриента")
                return None, False

            student = self.db.query(Student).filter(
                Student.russian_student_id == int(russian_id)
            ).first()

            is_new_student = False
            if not student:
                full_name = self._get_full_name(item)
                # Пропускаем студентов без нормального ФИО
                if full_name.startswith('Студент') or len(full_name) < 5:
                    logger.debug(f"⏭️ Пропуск студента ID {russian_id}: нет ФИО")
                    return None, False

                logger.info(f"➕ Создание нового студента с ID {russian_id}")
                is_new_student = True
                student = Student(
                    russian_student_id=int(russian_id),
                    full_name=full_name,
                    status=StudentStatus.ACTIVE,
                    contact_status=ContactStatus.NEW
                )
                self.db.add(student)
                self.db.flush()
            else:
                current_name = self._get_full_name(item)
                if student.full_name != current_name and current_name != f"Студент {russian_id}":
                    student.full_name = current_name

                if not student.study_level and group_config.get('study_level'):
                    student.study_level = group_config.get('study_level')
                if not student.study_form and group_config.get('study_form'):
                    student.study_form = group_config.get('study_form')
                if not student.study_basis and group_config.get('study_basis'):
                    student.study_basis = group_config.get('study_basis')

            logger.info(f"{'🆕 Создание' if is_new_student else '🔄 Обновление'} студента ID {russian_id}")

            application, is_new_application = self.update_or_create_application(item, group_config, student)

            if application:
                if is_new_application:
                    logger.debug(f"   ✅ Добавлено заявление на {group_config['profile_name']}")
                else:
                    logger.debug(
                        f"   ✅ Обновлено заявление на {group_config['profile_name']} (место: {application.position})")

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

    def calculate_statistics_from_api_data(self, group_config: Dict, api_data: List[Dict]) -> Dict[str, Any]:
        """Рассчитывает статистику НАПРЯМУЮ ИЗ API ДАННЫХ (всех абитуриентов группы)"""

        if not api_data:
            return self._empty_statistics()

        total_applications = len(api_data)

        # Подавшие документы (имеют баллы)
        applications_submitted = len([
            item for item in api_data
            if item.get('СуммаБаллов') and int(item.get('СуммаБаллов', 0)) > 0
        ])

        # Зачисленные
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
            sorted_items = sorted(api_data, key=lambda x: int(x.get('СуммаБаллов', 0)) if x.get('СуммаБаллов') else 0,
                                  reverse=True)
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

        paid_stats = {
            "total": group_config.get('paid_places', 0),
            "filled": 0,
            "free": group_config.get('paid_places', 0),
            "applicants_with_consent": 0
        }

        target_stats = {
            "total": group_config.get('target_places', 0),
            "filled": 0,
            "free": group_config.get('target_places', 0),
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

    def get_students_by_criteria(self, study_form: StudyForm = None, study_basis: StudyBasis = None) -> List[Student]:
        """Получает студентов, подавших заявления с определенной формой/основой"""
        query = self.db.query(Student).join(StudentApplication)

        if study_form:
            query = query.filter(StudentApplication.study_form == study_form)
        if study_basis:
            query = query.filter(StudentApplication.study_basis == study_basis)

        return query.distinct().all()

    def get_applications_by_form_and_basis(self, study_form: StudyForm = None, study_basis: StudyBasis = None) -> List[
        StudentApplication]:
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

        # Сохраняем API данные для каждой группы
        all_api_data = {}

        for group_config in GROUPS_CONFIG:
            logger.info(f"\n📌 Парсинг группы: {group_config['name']}")
            logger.info(f"   Профиль: {group_config['profile_name']}")
            logger.info(f"   Бюджетных мест: {group_config.get('budget_places', 0)}")
            logger.info("-" * 40)

            group_stats = {
                "students_updated": 0,
                "students_created": 0,
                "students_skipped": 0,
                "errors": 0
            }

            data = self.fetch_group_data(group_config['uid'])
            if not data or 'data' not in data:
                logger.error(f"❌ Нет данных для группы {group_config['name']}")
                continue

            students_data = data['data']
            logger.info(f"📊 В API: {len(students_data)} абитуриентов")

            # Сохраняем API данные для статистики
            all_api_data[group_config['name']] = students_data

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

            # Обновляем общую статистику
            self.all_stats["total"]["students_updated"] += group_stats["students_updated"]
            self.all_stats["total"]["students_created"] += group_stats["students_created"]
            self.all_stats["total"]["students_skipped"] += group_stats["students_skipped"]
            self.all_stats["total"]["errors"] += group_stats["errors"]

            self.db.commit()

        # После обработки всех студентов - считаем статистику из API данных
        for group_config in GROUPS_CONFIG:
            api_data = all_api_data.get(group_config['name'], [])
            # Статистика считается из API данных (всех абитуриентов группы)
            group_statistics = self.calculate_statistics_from_api_data(group_config, api_data)

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
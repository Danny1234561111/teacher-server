import pandas as pd
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
import re
import logging

from database.schema import (
    Student, StudentApplication, Profile,
    StudentStatus, StudyForm, StudyBasis, ApplicationStatus
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def normalize_full_name(full_name: str) -> str:
    """Нормализует ФИО: убирает *, приводит к правильному регистру"""
    if not full_name or not isinstance(full_name, str):
        return ""

    cleaned = re.sub(r'[*]', '', full_name)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()

    if not cleaned:
        return ""

    words = cleaned.split()
    normalized_words = []
    for word in words:
        if word:
            if '-' in word:
                parts = word.split('-')
                normalized_parts = [p[0].upper() + p[1:].lower() if p else p for p in parts]
                normalized_words.append('-'.join(normalized_parts))
            else:
                normalized_words.append(word[0].upper() + word[1:].lower())

    return ' '.join(normalized_words)


class ExcelImportService:

    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id
        self.column_mapping = {
            'фио': 'full_name',
            'ффио': 'full_name',
            'фамилия имя отчество': 'full_name',
            'ф.и.о.': 'full_name',
            'full_name': 'full_name',
            'телефон': 'phone',
            'phone': 'phone',
            'профиль': 'profile_name',
            'образовательная программа': 'profile_name',
            'обр.программа': 'profile_name',
            'program': 'profile_name',
            'направление': 'profile_name',
            'баллы': 'score',
            'сумма баллов': 'score',
            'score': 'score',
            'егэ': 'score',
            'приоритет': 'priority',
            'priority': 'priority',
            'форма обучения': 'study_form',
            'форма': 'study_form',
            'основа обучения': 'study_basis',
            'основа': 'study_basis',
            'вид мест': 'study_basis',
            'russian_student_id': 'russian_student_id',
            'идентификатор': 'russian_student_id',
            'id студента': 'russian_student_id',
            'уникальный код поступающего': 'russian_student_id',
            'уникальный код': 'russian_student_id',
            'id поступающего': 'russian_student_id',
            'ид поступающего': 'russian_student_id',
            'почта': 'email',
            'email': 'email'
        }
        self.study_form_mapping = {
            'очная': StudyForm.FULL_TIME,
            'очная форма': StudyForm.FULL_TIME,
            'очная форма обучения': StudyForm.FULL_TIME,
            'full-time': StudyForm.FULL_TIME,
            'очно-заочная': StudyForm.PART_TIME,
            'очно-заочная форма': StudyForm.PART_TIME,
            'part-time': StudyForm.PART_TIME,
            'заочная': StudyForm.CORRESPONDENCE,
            'заочная форма': StudyForm.CORRESPONDENCE,
            'заочная форма обучения': StudyForm.CORRESPONDENCE,
            'correspondence': StudyForm.CORRESPONDENCE,
        }
        self.study_basis_mapping = {
            'бюджетная': StudyBasis.BUDGET,
            'бюджет': StudyBasis.BUDGET,
            'бюджетная основа': StudyBasis.BUDGET,
            'бюджетные места': StudyBasis.BUDGET,
            'основные места в рамках кцп': StudyBasis.BUDGET,
            'платная': StudyBasis.PAID,
            'платное': StudyBasis.PAID,
            'платные места': StudyBasis.PAID,
            'коммерческая': StudyBasis.PAID,
            'целевая': StudyBasis.TARGET,
            'целевое': StudyBasis.TARGET,
            'целевые места': StudyBasis.TARGET,
        }

    async def import_from_dataframe(
            self,
            df: pd.DataFrame,
            create_missing_profiles: bool = False,
            duplicate_strategy: str = 'skip',
            replace_ids: Set[int] = set()
    ) -> Dict[str, Any]:
        # Нормализуем колонки
        df = self._normalize_columns(df)

        # Проверяем обязательные колонки
        missing_columns = []
        if 'full_name' not in df.columns:
            missing_columns.append('ФИО')
        if 'phone' not in df.columns:
            missing_columns.append('Телефон')
        if 'russian_student_id' not in df.columns:
            missing_columns.append('ID поступающего')

        if missing_columns:
            return {
                'success': False,
                'total_rows': len(df),
                'created_students': 0,
                'updated_students': 0,
                'created_applications': 0,
                'errors': [{"row": 0, "error": f"Отсутствуют обязательные колонки: {', '.join(missing_columns)}"}],
                'warnings': [],
                'message': f"Ошибка: в файле нет обязательных колонок",
                'duplicates_found': None
            }

        records = df.to_dict(orient='records')

        # Удаляем дубликаты внутри файла
        seen_ids = set()
        unique_records = []
        duplicate_ids_in_file = set()

        for row_dict in records:
            russian_student_id_raw = row_dict.get('russian_student_id')
            if pd.isna(russian_student_id_raw) or russian_student_id_raw is None:
                unique_records.append(row_dict)
                continue

            try:
                if isinstance(russian_student_id_raw, str):
                    cleaned = re.sub(r'[^\d]', '', russian_student_id_raw)
                    student_id = int(cleaned) if cleaned else None
                else:
                    student_id = int(float(russian_student_id_raw))

                if student_id and student_id > 0:
                    if student_id in seen_ids:
                        duplicate_ids_in_file.add(student_id)
                        continue
                    else:
                        seen_ids.add(student_id)
                        unique_records.append(row_dict)
                else:
                    unique_records.append(row_dict)
            except (ValueError, TypeError):
                unique_records.append(row_dict)

        records = unique_records

        # Собираем все ID из файла
        all_ids = []
        id_to_row = {}
        id_to_row_num = {}

        for idx, row_dict in enumerate(records):
            russian_student_id_raw = row_dict.get('russian_student_id')
            if pd.isna(russian_student_id_raw) or russian_student_id_raw is None:
                continue
            try:
                if isinstance(russian_student_id_raw, str):
                    cleaned = re.sub(r'[^\d]', '', russian_student_id_raw)
                    student_id = int(cleaned) if cleaned else None
                else:
                    student_id = int(float(russian_student_id_raw))
                if student_id and student_id > 0:
                    all_ids.append(student_id)
                    id_to_row[student_id] = row_dict
                    id_to_row_num[student_id] = idx + 2  # +2 для учета заголовка и 0-индексации
            except (ValueError, TypeError):
                continue

        # Находим существующих студентов в БД
        existing_students = self.db.query(Student).filter(
            Student.russian_student_id.in_(set(all_ids))
        ).all()

        existing_ids = {s.russian_student_id for s in existing_students}
        existing_students_dict = {s.russian_student_id: s for s in existing_students}

        logger.info(f"📊 Статистика дубликатов:")
        logger.info(f"   existing_ids: {existing_ids}")
        logger.info(f"   replace_ids: {replace_ids}")
        logger.info(f"   duplicate_strategy: {duplicate_strategy}")

        # Если стратегия skip и есть дубликаты - возвращаем их список для выбора
        if duplicate_strategy == 'skip' and existing_ids:
            duplicates_found = [
                {"id": s.russian_student_id, "full_name": s.full_name}
                for s in existing_students
            ]
            return {
                'success': False,
                'total_rows': len(df),
                'created_students': 0,
                'updated_students': 0,
                'created_applications': 0,
                'errors': [{"row": 0, "error": f"Найдено {len(existing_ids)} дубликатов в БД"}],
                'warnings': [],
                'message': "Обнаружены дубликаты в системе",
                'duplicates_found': duplicates_found
            }

        # Определяем, какие ID обновлять, какие пропускать
        ids_to_update = set()
        ids_to_skip = set()

        if duplicate_strategy == 'replace_all':
            ids_to_update = existing_ids.copy()
            logger.info(f"   replace_all: обновляем ВСЕ {len(ids_to_update)} дубликатов")
        elif duplicate_strategy == 'replace_selected':
            ids_to_update = replace_ids & existing_ids
            ids_to_skip = existing_ids - ids_to_update
            logger.info(f"   replace_selected: обновляем {len(ids_to_update)} ID: {ids_to_update}")
            logger.info(f"   replace_selected: пропускаем {len(ids_to_skip)} ID: {ids_to_skip}")
        else:
            ids_to_skip = existing_ids
            logger.info(f"   skip: пропускаем ВСЕ {len(ids_to_skip)} дубликатов")

        created_students = 0
        updated_students = 0
        created_applications = 0
        errors = []
        warnings = []

        if duplicate_ids_in_file:
            warnings.append({"row": 0, "warning": f"Пропущено {len(duplicate_ids_in_file)} дубликатов внутри файла"})

        # Добавляем предупреждения о пропущенных дубликатах (НЕ ОШИБКИ!)
        for student_id in ids_to_skip:
            student = existing_students_dict.get(student_id)
            if student:
                warnings.append({
                    "row": id_to_row_num.get(student_id, 0),
                    "warning": f"Дубликат ID {student_id} (ФИО: {student.full_name}) пропущен - не выбран для замены"
                })

        # Обрабатываем каждого студента из файла
        for student_id, row_dict in id_to_row.items():
            row_num = id_to_row_num.get(student_id, 0)

            try:
                existing_student = existing_students_dict.get(student_id)

                if existing_student:
                    # Студент существует
                    if student_id in ids_to_skip:
                        # Пропускаем (уже добавили предупреждение)
                        continue

                    if student_id in ids_to_update:
                        # Обновляем
                        logger.info(f"🔄 Обновляем ID {student_id}")
                        updated_students += 1

                        # Получаем данные из строки
                        full_name_raw = row_dict.get('full_name')
                        phone_raw = row_dict.get('phone')
                        email_raw = row_dict.get('email')
                        study_form_val = row_dict.get('study_form')
                        study_basis_val = row_dict.get('study_basis')
                        profile_name_val = row_dict.get('profile_name')
                        score_raw = row_dict.get('score')
                        priority_raw = row_dict.get('priority')

                        normalized_full_name = normalize_full_name(
                            str(full_name_raw).strip()) if full_name_raw and not pd.isna(
                            full_name_raw) else existing_student.full_name
                        normalized_phone = self._normalize_phone(str(phone_raw)) if phone_raw and not pd.isna(
                            phone_raw) else existing_student.phone

                        logger.info(f"   Старое ФИО: {existing_student.full_name} -> Новое: {normalized_full_name}")
                        logger.info(f"   Старый телефон: {existing_student.phone} -> Новый: {normalized_phone}")

                        # Обновляем поля
                        existing_student.full_name = normalized_full_name
                        existing_student.phone = normalized_phone

                        if email_raw and not pd.isna(email_raw):
                            additional_contacts = existing_student.additional_contacts or {}
                            additional_contacts['email'] = str(email_raw).strip()
                            existing_student.additional_contacts = additional_contacts

                        if study_form_val and not pd.isna(study_form_val):
                            parsed_form = self._parse_study_form(str(study_form_val))
                            if parsed_form:
                                existing_student.study_form = parsed_form

                        if study_basis_val and not pd.isna(study_basis_val):
                            parsed_basis = self._parse_study_basis(str(study_basis_val))
                            if parsed_basis:
                                existing_student.study_basis = parsed_basis

                        existing_student.updated_at = datetime.utcnow()
                        self.db.flush()

                        # Обработка заявления
                        if profile_name_val and not pd.isna(profile_name_val):
                            result = {'warnings': []}
                            await self._process_application_dict(
                                student=existing_student,
                                profile_name=str(profile_name_val).strip(),
                                score_raw=score_raw,
                                priority_raw=priority_raw,
                                study_form_val=study_form_val,
                                study_basis_val=study_basis_val,
                                create_missing_profiles=create_missing_profiles,
                                result=result
                            )
                            created_applications += result.get('applications_created', 0)
                            if result.get('warnings'):
                                warnings.extend([{"row": row_num, "warning": w} for w in result['warnings']])
                else:
                    # Создаем нового студента
                    logger.info(f"✨ Создаем нового студента ID {student_id}")
                    created_students += 1

                    full_name_raw = row_dict.get('full_name')
                    phone_raw = row_dict.get('phone')
                    email_raw = row_dict.get('email')
                    study_form_val = row_dict.get('study_form')
                    study_basis_val = row_dict.get('study_basis')
                    profile_name_val = row_dict.get('profile_name')
                    score_raw = row_dict.get('score')
                    priority_raw = row_dict.get('priority')

                    normalized_full_name = normalize_full_name(
                        str(full_name_raw).strip()) if full_name_raw and not pd.isna(full_name_raw) else ""
                    normalized_phone = self._normalize_phone(str(phone_raw)) if phone_raw and not pd.isna(
                        phone_raw) else ""

                    study_form_parsed = None
                    if study_form_val and not pd.isna(study_form_val):
                        study_form_parsed = self._parse_study_form(str(study_form_val))

                    study_basis_parsed = None
                    if study_basis_val and not pd.isna(study_basis_val):
                        study_basis_parsed = self._parse_study_basis(str(study_basis_val))

                    additional_contacts = {}
                    if email_raw and not pd.isna(email_raw):
                        additional_contacts['email'] = str(email_raw).strip()

                    new_student = Student(
                        russian_student_id=student_id,
                        full_name=normalized_full_name,
                        phone=normalized_phone,
                        additional_contacts=additional_contacts if additional_contacts else None,
                        study_form=study_form_parsed,
                        study_basis=study_basis_parsed,
                        status=StudentStatus.ACTIVE,
                        kurator_id=self.user_id,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    self.db.add(new_student)
                    self.db.flush()

                    # Обработка заявления
                    if profile_name_val and not pd.isna(profile_name_val):
                        result = {'warnings': []}
                        await self._process_application_dict(
                            student=new_student,
                            profile_name=str(profile_name_val).strip(),
                            score_raw=score_raw,
                            priority_raw=priority_raw,
                            study_form_val=study_form_val,
                            study_basis_val=study_basis_val,
                            create_missing_profiles=create_missing_profiles,
                            result=result
                        )
                        created_applications += result.get('applications_created', 0)
                        if result.get('warnings'):
                            warnings.extend([{"row": row_num, "warning": w} for w in result['warnings']])

            except Exception as e:
                logger.error(f"Ошибка при обработке ID {student_id}: {e}")
                errors.append({"row": row_num, "error": f"Ошибка: {str(e)}"})

        if not errors:
            self.db.commit()
            logger.info(f"✅ Импорт завершен. Создано: {created_students}, Обновлено: {updated_students}")
        else:
            self.db.rollback()
            logger.error(f"❌ Импорт отменен из-за критических ошибок. Ошибок: {len(errors)}")

        # Успех, если нет критических ошибок (пропущенные дубликаты - это не ошибки)
        success = len(errors) == 0

        return {
            'success': success,
            'total_rows': len(df),
            'created_students': created_students,
            'updated_students': updated_students,
            'created_applications': created_applications,
            'errors': errors,  # Только критические ошибки
            'warnings': warnings,  # Пропущенные дубликаты и другие предупреждения
            'message': f"Импорт завершен. Создано: {created_students}, Обновлено: {updated_students}, Заявлений: {created_applications}",
            'duplicates_found': None
        }

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        df.columns = df.columns.str.strip().str.lower()
        rename_dict = {}
        for col in df.columns:
            if col in self.column_mapping:
                rename_dict[col] = self.column_mapping[col]
        if rename_dict:
            df = df.rename(columns=rename_dict)
        return df

    async def _process_application_dict(
            self,
            student: Student,
            profile_name: str,
            score_raw,
            priority_raw,
            study_form_val,
            study_basis_val,
            create_missing_profiles: bool,
            result: Dict[str, Any]
    ):
        clean_profile_name = profile_name.split(';')[0].strip()

        profile = self.db.query(Profile).filter(
            Profile.name.ilike(f"%{clean_profile_name}%")
        ).first()

        if not profile:
            profile = self.db.query(Profile).filter(
                Profile.name.ilike(clean_profile_name)
            ).first()

        if not profile:
            result['warnings'].append(f"Не найден профиль '{clean_profile_name}'")
            return

        existing_application = self.db.query(StudentApplication).filter(
            StudentApplication.student_id == student.id,
            StudentApplication.profile_id == profile.id
        ).first()

        if existing_application:
            result['warnings'].append(f"Заявление на профиль '{clean_profile_name}' уже существует")
            return

        total_score = None
        if score_raw and not pd.isna(score_raw):
            try:
                total_score = int(float(score_raw))
            except (ValueError, TypeError):
                result['warnings'].append(f"Не удалось распознать баллы: {score_raw}")

        priority_value = 1
        if priority_raw and not pd.isna(priority_raw):
            try:
                priority_value = int(float(priority_raw))
                priority_value = max(1, min(10, priority_value))
            except (ValueError, TypeError):
                pass

        study_form_for_apps = None
        if study_form_val and not pd.isna(study_form_val):
            study_form_for_apps = self._parse_study_form(str(study_form_val))
        if not study_form_for_apps:
            study_form_for_apps = student.study_form

        study_basis_for_apps = None
        if study_basis_val and not pd.isna(study_basis_val):
            study_basis_for_apps = self._parse_study_basis(str(study_basis_val))
        if not study_basis_for_apps:
            study_basis_for_apps = student.study_basis

        application = StudentApplication(
            student_id=student.id,
            department_id=profile.speciality.department_id if profile.speciality else None,
            speciality_id=profile.speciality_id,
            profile_id=profile.id,
            total_score=total_score,
            priority=priority_value,
            study_form=study_form_for_apps,
            study_basis=study_basis_for_apps,
            study_level=profile.study_level,
            application_status=ApplicationStatus.PENDING,
            consent_status=False,
            participation=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        self.db.add(application)

        try:
            self.db.flush()
            result['applications_created'] = result.get('applications_created', 0) + 1
        except Exception as e:
            result['warnings'].append(f"Ошибка при создании заявления: {str(e)}")

    def _parse_study_form(self, value: Any) -> Optional[StudyForm]:
        if not value or pd.isna(value):
            return None
        str_value = str(value).strip().lower()
        for key, form in self.study_form_mapping.items():
            if key in str_value:
                return form
        return None

    def _parse_study_basis(self, value: Any) -> Optional[StudyBasis]:
        if not value or pd.isna(value):
            return None
        str_value = str(value).strip().lower()
        for key, basis in self.study_basis_mapping.items():
            if key in str_value:
                return basis
        return None

    def _normalize_phone(self, phone: str) -> str:
        digits = re.sub(r'\D', '', phone)
        if len(digits) == 11 and digits.startswith('8'):
            return '+7' + digits[1:]
        elif len(digits) == 11 and digits.startswith('7'):
            return '+' + digits
        elif len(digits) == 10:
            return '+7' + digits
        return phone
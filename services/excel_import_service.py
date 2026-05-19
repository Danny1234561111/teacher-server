import pandas as pd
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import datetime
import re

from database.schema import (
    Student, StudentApplication, Profile,
    StudentStatus, ContactStatus, MeetingStatus, CallStatus,
    DecisionStatus, DocumentsStatus, StudyForm, StudyBasis,
    ApplicationStatus
)


class ExcelImportService:
    """Сервис для импорта абитуриентов из Excel"""

    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id

        # Маппинг названий колонок
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
            'id поступающего': 'russian_student_id',
            'russian_student_id': 'russian_student_id',
            'идентификатор': 'russian_student_id',
            'id студента': 'russian_student_id',
            'почта': 'email',
            'email': 'email'
        }

        # Маппинг для формы обучения
        self.study_form_mapping = {
            'очная': StudyForm.FULL_TIME,
            'очная форма': StudyForm.FULL_TIME,
            'full-time': StudyForm.FULL_TIME,
            'очно-заочная': StudyForm.PART_TIME,
            'очно-заочная форма': StudyForm.PART_TIME,
            'part-time': StudyForm.PART_TIME,
            'заочная': StudyForm.CORRESPONDENCE,
            'заочная форма': StudyForm.CORRESPONDENCE,
            'correspondence': StudyForm.CORRESPONDENCE,
        }

        # Маппинг для основы обучения
        self.study_basis_mapping = {
            'бюджетная': StudyBasis.BUDGET,
            'бюджет': StudyBasis.BUDGET,
            'бюджетная основа': StudyBasis.BUDGET,
            'бюджетные места': StudyBasis.BUDGET,
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
            create_missing_profiles: bool = False
    ) -> Dict[str, Any]:
        """Импорт данных из DataFrame"""

        # Нормализуем названия колонок
        df = self._normalize_columns(df)

        # Проверяем наличие ОБЯЗАТЕЛЬНЫХ колонок
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
                'message': f"Ошибка: в файле нет обязательных колонок: {', '.join(missing_columns)}"
            }

        # Результаты импорта
        created_students = 0
        updated_students = 0
        created_applications = 0
        errors = []
        warnings = []

        # Обрабатываем каждую строку
        for idx, row in df.iterrows():
            row_num = idx + 2

            try:
                result = await self._process_row(row, row_num, create_missing_profiles)

                if result.get('error'):
                    errors.append({
                        "row": row_num,
                        "error": result['error']
                    })
                else:
                    if result.get('created'):
                        created_students += 1
                    elif result.get('updated'):
                        updated_students += 1

                    created_applications += result.get('applications_created', 0)

                    if result.get('warnings'):
                        warnings.extend([
                            {"row": row_num, "warning": w}
                            for w in result['warnings']
                        ])

            except Exception as e:
                errors.append({
                    "row": row_num,
                    "error": f"Ошибка обработки строки: {str(e)}"
                })

        # Коммитим все изменения
        if not errors:
            self.db.commit()
        else:
            self.db.rollback()

        return {
            'success': len(errors) == 0,
            'total_rows': len(df),
            'created_students': created_students,
            'updated_students': updated_students,
            'created_applications': created_applications,
            'errors': errors,
            'warnings': warnings,
            'message': f"Импорт завершен. Создано: {created_students}, Обновлено: {updated_students}, Заявлений: {created_applications}"
        }

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Нормализует названия колонок"""
        df.columns = df.columns.str.strip().str.lower()

        rename_dict = {}
        for col in df.columns:
            if col in self.column_mapping:
                rename_dict[col] = self.column_mapping[col]

        if rename_dict:
            df = df.rename(columns=rename_dict)
        return df

    async def _process_row(
            self,
            row: pd.Series,
            row_num: int,
            create_missing_profiles: bool = False
    ) -> Dict[str, Any]:
        """Обрабатывает одну строку Excel"""

        result = {
            'created': False,
            'updated': False,
            'applications_created': 0,
            'warnings': [],
            'error': None
        }

        # 1. ФИО (ОБЯЗАТЕЛЬНО)
        full_name = self._get_value(row, 'full_name')
        if not full_name:
            result['error'] = "ФИО обязательно"
            return result
        full_name = str(full_name).strip()

        # 2. Телефон (ОБЯЗАТЕЛЬНО)
        phone = self._get_value(row, 'phone')
        if not phone:
            result['error'] = "Телефон обязателен"
            return result
        phone = self._normalize_phone(str(phone).strip())

        # 3. Russian Student ID (ОБЯЗАТЕЛЬНО - уникальный идентификатор)
        russian_student_id = None
        if 'russian_student_id' in row and pd.notna(row['russian_student_id']):
            try:
                russian_student_id = int(float(row['russian_student_id']))
                if russian_student_id <= 0:
                    result['error'] = "ID должен быть положительным числом"
                    return result
            except (ValueError, TypeError):
                result['error'] = "ID должен быть числом"
                return result
        else:
            result['error'] = "ID поступающего обязателен"
            return result

        # 4. Email (опционально)
        email = self._get_value(row, 'email')
        if email:
            email = str(email).strip()

        # 5. ПОИСК СТУДЕНТА ПО УНИКАЛЬНОМУ ID
        existing_student = self.db.query(Student).filter(
            Student.russian_student_id == russian_student_id
        ).first()

        if existing_student:
            # Студент существует - обновляем данные
            result['updated'] = True

            # Обновляем ФИО если изменилось
            if existing_student.full_name != full_name:
                existing_student.full_name = full_name

            # Обновляем телефон если изменился
            if existing_student.phone != phone:
                existing_student.phone = phone

            # Обновляем email если указан
            if email:
                additional = existing_student.additional_contacts or {}
                if additional.get('email') != email:
                    additional['email'] = email
                    existing_student.additional_contacts = additional

            # Обновляем форму и основу обучения если указаны
            study_form = self._parse_study_form(row)
            if study_form and not existing_student.study_form:
                existing_student.study_form = study_form

            study_basis = self._parse_study_basis(row)
            if study_basis and not existing_student.study_basis:
                existing_student.study_basis = study_basis

            existing_student.updated_at = datetime.utcnow()
            self.db.flush()
            student = existing_student

        else:
            # Студент не существует - создаем нового
            result['created'] = True

            study_form = self._parse_study_form(row)
            study_basis = self._parse_study_basis(row)

            additional_contacts = {}
            if email:
                additional_contacts['email'] = email

            new_student = Student(
                russian_student_id=russian_student_id,
                full_name=full_name,
                phone=phone,
                additional_contacts=additional_contacts if additional_contacts else None,
                study_form=study_form,
                study_basis=study_basis,
                status=StudentStatus.ACTIVE,
                contact_status=ContactStatus.NEW,
                meeting_status=MeetingStatus.NOT_MET,
                call_status=CallStatus.NOT_REACHED,
                decision_status=DecisionStatus.THINKING,
                documents_status=DocumentsStatus.NOT_SUBMITTED,
                kurator_id=self.user_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            self.db.add(new_student)
            self.db.flush()
            student = new_student

        # 6. Заявление (опционально)
        profile_name = self._get_value(row, 'profile_name')
        if profile_name:
            await self._process_application(
                student=student,
                profile_name=str(profile_name).strip(),
                row=row,
                create_missing_profiles=create_missing_profiles,
                result=result
            )

        return result

    async def _process_application(
            self,
            student: Student,
            profile_name: str,
            row: pd.Series,
            create_missing_profiles: bool,
            result: Dict
    ):
        """Обрабатывает заявление студента на профиль"""

        # Ищем профиль по названию
        profile = self.db.query(Profile).filter(
            Profile.name.ilike(f"%{profile_name}%")
        ).first()

        if not profile:
            profile = self.db.query(Profile).filter(
                Profile.name.ilike(profile_name)
            ).first()

        if not profile:
            result['warnings'].append(f"Не найден профиль '{profile_name}'")
            return

        # Проверяем существующее заявление
        existing_application = self.db.query(StudentApplication).filter(
            StudentApplication.student_id == student.id,
            StudentApplication.profile_id == profile.id
        ).first()

        if existing_application:
            result['warnings'].append(f"Заявление на профиль '{profile_name}' уже существует")
            return

        # Получаем баллы
        score = self._get_value(row, 'score')
        total_score = None
        if score:
            try:
                total_score = int(float(score))
            except (ValueError, TypeError):
                result['warnings'].append(f"Не удалось распознать баллы: {score}")

        # Получаем приоритет
        priority = self._get_value(row, 'priority')
        priority_value = None
        if priority:
            try:
                priority_value = int(float(priority))
                if priority_value < 1:
                    priority_value = 1
                if priority_value > 10:
                    priority_value = 10
            except (ValueError, TypeError):
                priority_value = 1

        # Форма и основа обучения
        study_form = self._parse_study_form(row) or profile.study_form
        study_basis = self._parse_study_basis(row) or profile.study_basis

        # Создаем заявление
        application = StudentApplication(
            student_id=student.id,
            department_id=profile.speciality.department_id if profile.speciality else None,
            speciality_id=profile.speciality_id,
            profile_id=profile.id,
            total_score=total_score,
            priority=priority_value,
            study_form=study_form,
            study_basis=study_basis,
            study_level=profile.study_level,
            application_status=ApplicationStatus.PENDING,
            consent_status=False,
            participation=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        self.db.add(application)
        result['applications_created'] += 1

    def _parse_study_form(self, row: pd.Series) -> Optional[StudyForm]:
        """Парсит форму обучения"""
        value = self._get_value(row, 'study_form')
        if not value:
            return None

        str_value = str(value).strip().lower()
        for key, form in self.study_form_mapping.items():
            if key in str_value:
                return form
        return None

    def _parse_study_basis(self, row: pd.Series) -> Optional[StudyBasis]:
        """Парсит основу обучения"""
        value = self._get_value(row, 'study_basis')
        if not value:
            return None

        str_value = str(value).strip().lower()
        for key, basis in self.study_basis_mapping.items():
            if key in str_value:
                return basis
        return None

    def _get_value(self, row: pd.Series, key: str) -> Any:
        """Безопасно получает значение из строки"""
        if key in row and pd.notna(row[key]):
            return row[key]
        return None

    def _normalize_phone(self, phone: str) -> str:
        """Нормализует номер телефона"""
        digits = re.sub(r'\D', '', phone)

        if len(digits) == 11 and digits.startswith('8'):
            digits = '7' + digits[1:]
        if len(digits) == 11 and digits.startswith('7'):
            return '+' + digits
        if len(digits) == 10 and digits.startswith('9'):
            return '+7' + digits

        return phone
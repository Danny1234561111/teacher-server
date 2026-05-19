import pandas as pd
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import re

from database.schema import (
    Student, StudentApplication, Profile, Speciality, Department,
    StudentStatus, ContactStatus, MeetingStatus, CallStatus,
    DecisionStatus, DocumentsStatus, StudyForm, StudyBasis,
    ApplicationStatus, PriorContact
)


class ExcelImportService:
    """Сервис для импорта абитуриентов из Excel"""

    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id

        # Маппинг названий колонок (поддерживаем разные варианты)
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
            'почта': 'email',
            'email': 'email'
        }

        # Маппинг для формы обучения
        self.study_form_mapping = {
            'очная': StudyForm.FULL_TIME,
            'очная форма': StudyForm.FULL_TIME,
            'full-time': StudyForm.FULL_TIME,
            'full time': StudyForm.FULL_TIME,
            'очно-заочная': StudyForm.PART_TIME,
            'очно-заочная форма': StudyForm.PART_TIME,
            'part-time': StudyForm.PART_TIME,
            'part time': StudyForm.PART_TIME,
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
            'бюджетное': StudyBasis.BUDGET,
            'платная': StudyBasis.PAID,
            'платное': StudyBasis.PAID,
            'платные места': StudyBasis.PAID,
            'коммерческая': StudyBasis.PAID,
            'коммерция': StudyBasis.PAID,
            'целевая': StudyBasis.TARGET,
            'целевое': StudyBasis.TARGET,
            'целевые места': StudyBasis.TARGET,
            'целевой прием': StudyBasis.TARGET,
        }

    async def import_from_dataframe(
            self,
            df: pd.DataFrame,
            create_missing_profiles: bool = False
    ) -> Dict[str, Any]:
        """
        Импорт данных из DataFrame

        Args:
            df: DataFrame с данными
            create_missing_profiles: Создавать ли профили, если не найдены

        Returns:
            Dict с результатами импорта
        """
        # Нормализуем названия колонок
        df = self._normalize_columns(df)

        # Проверяем наличие обязательных колонок
        if 'full_name' not in df.columns:
            return {
                'success': False,
                'total_rows': len(df),
                'created_students': 0,
                'updated_students': 0,
                'created_applications': 0,
                'errors': [{"row": 0, "error": "Отсутствует обязательная колонка 'ФИО'"}],
                'warnings': [],
                'message': "Ошибка: в файле нет колонки с ФИО"
            }

        # Результаты импорта
        created_students = 0
        updated_students = 0
        created_applications = 0
        errors = []
        warnings = []

        # Обрабатываем каждую строку
        for idx, row in df.iterrows():
            row_num = idx + 2  # +2 потому что индекс с 0 и +1 для заголовка

            try:
                result = await self._process_row(row, row_num, create_missing_profiles)

                if result.get('error'):
                    errors.append({
                        "row": row_num,
                        "error": result['error'],
                        "data": result.get('data', {})
                    })
                else:
                    if result.get('created'):
                        created_students += 1
                    elif result.get('updated'):
                        updated_students += 1

                    created_applications += result.get('applications_created', 0)

                    if result.get('warnings'):
                        warnings.extend([
                            {"row": row_num, "warning": w, "student": result.get('student_name')}
                            for w in result['warnings']
                        ])

            except Exception as e:
                errors.append({
                    "row": row_num,
                    "error": f"Ошибка обработки строки: {str(e)}",
                    "data": row.to_dict()
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
            'message': f"Импорт завершен. Создано студентов: {created_students}, Обновлено: {updated_students}, Создано заявлений: {created_applications}"
        }

    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Нормализует названия колонок в DataFrame"""
        # Приводим все названия колонок к нижнему регистру и убираем пробелы
        df.columns = df.columns.str.strip().str.lower()

        # Переименовываем согласно маппингу
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

        # 1. Получаем ФИО (обязательно)
        full_name = self._get_value(row, 'full_name')
        if not full_name:
            result['error'] = "ФИО обязательно для заполнения"
            return result

        full_name = str(full_name).strip()
        result['student_name'] = full_name

        # 2. Получаем телефон
        phone = self._get_value(row, 'phone')
        if phone:
            phone = self._normalize_phone(str(phone).strip())

        # 3. Получаем russian_student_id (если есть)
        russian_student_id = None
        if 'russian_student_id' in row and pd.notna(row['russian_student_id']):
            try:
                russian_student_id = int(float(row['russian_student_id']))
            except (ValueError, TypeError):
                result['warnings'].append(f"Не удалось распознать ID поступающего: {row['russian_student_id']}")

        # 4. Получаем email (если есть)
        email = self._get_value(row, 'email')
        if email:
            email = str(email).strip()

        # 5. Ищем или создаем студента
        student = self._find_or_create_student(
            full_name=full_name,
            phone=phone,
            russian_student_id=russian_student_id,
            email=email,
            row=row,
            result=result
        )

        if not student:
            result['error'] = "Не удалось создать студента"
            return result

        # 6. Обрабатываем заявление (профиль, баллы, приоритет)
        profile_name = self._get_value(row, 'profile_name')

        if profile_name:
            await self._process_application(
                student=student,
                profile_name=str(profile_name).strip(),
                row=row,
                create_missing_profiles=create_missing_profiles,
                result=result
            )
        else:
            result['warnings'].append("Не указан профиль, заявление не создано")

        return result

    def _find_or_create_student(
            self,
            full_name: str,
            phone: Optional[str],
            russian_student_id: Optional[int],
            email: Optional[str],
            row: pd.Series,
            result: Dict
    ) -> Optional[Student]:
        """Находит существующего студента или создает нового"""

        # Пробуем найти по russian_student_id
        student = None
        if russian_student_id:
            student = self.db.query(Student).filter(
                Student.russian_student_id == russian_student_id
            ).first()

        # Если не нашли по ID, ищем по ФИО и телефону
        if not student and phone:
            student = self.db.query(Student).filter(
                Student.full_name == full_name,
                Student.phone == phone
            ).first()

        # Если не нашли, ищем только по ФИО
        if not student:
            student = self.db.query(Student).filter(
                Student.full_name == full_name
            ).first()

        # Если студент найден, обновляем данные
        if student:
            updated = False

            if phone and not student.phone:
                student.phone = phone
                updated = True

            if russian_student_id and not student.russian_student_id:
                student.russian_student_id = russian_student_id
                updated = True

            if email:
                additional_contacts = student.additional_contacts or {}
                if additional_contacts.get('email') != email:
                    additional_contacts['email'] = email
                    student.additional_contacts = additional_contacts
                    updated = True

            # Обновляем форму обучения, если указана
            study_form = self._parse_study_form(row)
            if study_form and not student.study_form:
                student.study_form = study_form
                updated = True

            # Обновляем основу обучения, если указана
            study_basis = self._parse_study_basis(row)
            if study_basis and not student.study_basis:
                student.study_basis = study_basis
                updated = True

            if updated:
                student.updated_at = datetime.utcnow()
                result['updated'] = True

            return student

        # Создаем нового студента
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
        self.db.flush()  # Получаем ID без коммита

        result['created'] = True

        return new_student

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
            # Пробуем точное совпадение без учета регистра
            profile = self.db.query(Profile).filter(
                Profile.name.ilike(profile_name)
            ).first()

        if not profile:
            result['warnings'].append(f"Не найден профиль '{profile_name}'")
            return

        # Проверяем, есть ли уже заявление на этот профиль
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
                if total_score < 0 or total_score > 400:
                    result['warnings'].append(f"Баллы {total_score} выходят за пределы 0-400")
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
                result['warnings'].append(f"Не удалось распознать приоритет: {priority}, установлен 1")
                priority_value = 1

        # Получаем форму и основу обучения из строки или из профиля
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
        """Парсит форму обучения из строки"""
        study_form_value = self._get_value(row, 'study_form')
        if not study_form_value:
            return None

        study_form_str = str(study_form_value).strip().lower()

        for key, value in self.study_form_mapping.items():
            if key in study_form_str:
                return value

        return None

    def _parse_study_basis(self, row: pd.Series) -> Optional[StudyBasis]:
        """Парсит основу обучения из строки"""
        study_basis_value = self._get_value(row, 'study_basis')
        if not study_basis_value:
            return None

        study_basis_str = str(study_basis_value).strip().lower()

        for key, value in self.study_basis_mapping.items():
            if key in study_basis_str:
                return value

        return None

    def _get_value(self, row: pd.Series, key: str) -> Any:
        """Безопасно получает значение из строки"""
        if key in row and pd.notna(row[key]):
            return row[key]
        return None

    def _normalize_phone(self, phone: str) -> str:
        """Нормализует номер телефона"""
        # Убираем все нецифровые символы
        digits = re.sub(r'\D', '', phone)

        # Если номер начинается с 8 и длина 11, заменяем на +7
        if len(digits) == 11 and digits.startswith('8'):
            digits = '7' + digits[1:]

        # Если номер начинается с 7 и длина 11, добавляем +
        if len(digits) == 11 and digits.startswith('7'):
            return '+' + digits

        # Если номер начинается с 9 и длина 10, добавляем +7
        if len(digits) == 10 and digits.startswith('9'):
            return '+7' + digits

        return phone
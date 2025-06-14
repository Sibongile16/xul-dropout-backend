from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from typing import Optional, List, Dict, Any
import pandas as pd
import io
from datetime import datetime, date
from uuid import UUID
import re
from enum import Enum

from app.database import get_db
from app.routes.classes import ClassResponse, get_class_or_404
from app.utils.auth import get_current_user
from app.models.all_models import (
    User, Teacher, Student, Guardian, Class, UserRole, Gender, 
    RelationshipType, TransportMethod, IncomeRange, EducationLevel,
    StudentStatus, StudentClassHistory
)

router = APIRouter(prefix="/api/students", tags=["students"])

# CSV field mappings and validation
REQUIRED_STUDENT_FIELDS = [
    'first_name', 'last_name', 'date_of_birth', 'gender', 'student_number'
]

OPTIONAL_STUDENT_FIELDS = [
    'home_address', 'distance_to_school_km', 'transport_method',
    'special_needs', 'medical_conditions', 'enrollment_date'
]

REQUIRED_GUARDIAN_FIELDS = [
    'guardian_first_name', 'guardian_last_name', 'relationship_to_student'
]

OPTIONAL_GUARDIAN_FIELDS = [
    'guardian_phone', 'guardian_email', 'guardian_address',
    'guardian_occupation', 'guardian_income_range', 'guardian_education_level'
]

def validate_csv_headers(df: pd.DataFrame) -> List[str]:
    """Validate that required headers are present in the CSV."""
    errors = []
    missing_required = []
    
    # Check required student fields
    for field in REQUIRED_STUDENT_FIELDS:
        if field not in df.columns:
            missing_required.append(field)
    
    # Check required guardian fields
    for field in REQUIRED_GUARDIAN_FIELDS:
        if field not in df.columns:
            missing_required.append(field)
    
    if missing_required:
        errors.append(f"Missing required columns: {', '.join(missing_required)}")
    
    return errors

def validate_date(date_str: str) -> Optional[date]:
    """Validate and parse date string."""
    if pd.isna(date_str) or str(date_str).strip() == '':
        return None
    
    date_formats = ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y']
    
    for fmt in date_formats:
        try:
            return datetime.strptime(str(date_str).strip(), fmt).date()
        except ValueError:
            continue
    
    raise ValueError(f"Invalid date format: {date_str}")

def validate_enum_value(value: str, enum_class) -> Optional[str]:
    """Validate enum values."""
    if pd.isna(value) or str(value).strip() == '':
        return None
    
    value_str = str(value).strip().lower()
    
    # Try to match enum values
    for enum_item in enum_class:
        if enum_item.value.lower() == value_str:
            return enum_item
    
    # Try common variations for gender
    if enum_class == Gender:
        if value_str in ['m', 'boy', 'man']:
            return Gender.MALE
        elif value_str in ['f', 'girl', 'woman']:
            return Gender.FEMALE
    
    raise ValueError(f"Invalid {enum_class.__name__}: {value}")

def calculate_age(birth_date: date) -> int:
    """Calculate age from birth date."""
    today = date.today()
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))

def validate_phone_number(phone: str) -> Optional[str]:
    """Validate phone number format."""
    if pd.isna(phone) or str(phone).strip() == '':
        return None
    
    phone_str = str(phone).strip()
    # Basic phone validation - adjust regex as needed for your region
    phone_pattern = r'^[\+]?[0-9\s\-\(\)]{7,15}$'
    
    if not re.match(phone_pattern, phone_str):
        raise ValueError(f"Invalid phone number format: {phone}")
    
    return phone_str

def validate_email(email: str) -> Optional[str]:
    """Validate email format."""
    if pd.isna(email) or str(email).strip() == '':
        return None
    
    email_str = str(email).strip()
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if not re.match(email_pattern, email_str):
        raise ValueError(f"Invalid email format: {email}")
    
    return email_str.lower()

def process_student_row(row: pd.Series, row_index: int, class_id: Optional[str] = None) -> tuple:
    """Process a single row of student data."""
    errors = []
    student_data = {}
    guardian_data = {}
    
    try:
        # Process required student fields
        student_data['first_name'] = str(row['first_name']).strip()
        student_data['last_name'] = str(row['last_name']).strip()
        student_data['student_number'] = str(row['student_number']).strip()
        
        # Validate date of birth
        try:
            dob = validate_date(row['date_of_birth'])
            if not dob:
                errors.append(f"Row {row_index}: date_of_birth is required")
            else:
                student_data['date_of_birth'] = dob
                student_data['age'] = calculate_age(dob)
        except ValueError as e:
            errors.append(f"Row {row_index}: {str(e)}")
        
        # Validate gender
        try:
            gender = validate_enum_value(row['gender'], Gender)
            if not gender:
                errors.append(f"Row {row_index}: gender is required")
            else:
                student_data['gender'] = gender
        except ValueError as e:
            errors.append(f"Row {row_index}: {str(e)}")
        
        # Process optional student fields
        if 'home_address' in row and not pd.isna(row['home_address']):
            student_data['home_address'] = str(row['home_address']).strip()
        
        if 'distance_to_school_km' in row and not pd.isna(row['distance_to_school_km']):
            try:
                student_data['distance_to_school_km'] = float(row['distance_to_school_km'])
            except ValueError:
                errors.append(f"Row {row_index}: Invalid distance_to_school_km")
        
        if 'transport_method' in row:
            try:
                transport = validate_enum_value(row['transport_method'], TransportMethod)
                if transport:
                    student_data['transport_method'] = transport
            except ValueError as e:
                errors.append(f"Row {row_index}: {str(e)}")
        
        if 'special_needs' in row and not pd.isna(row['special_needs']):
            student_data['special_needs'] = str(row['special_needs']).strip()
        
        if 'medical_conditions' in row and not pd.isna(row['medical_conditions']):
            student_data['medical_conditions'] = str(row['medical_conditions']).strip()
        
        if 'enrollment_date' in row:
            try:
                enrollment_date = validate_date(row['enrollment_date'])
                if enrollment_date:
                    student_data['enrollment_date'] = enrollment_date
            except ValueError as e:
                errors.append(f"Row {row_index}: {str(e)}")
        
        if not student_data.get('enrollment_date'):
            student_data['enrollment_date'] = date.today()
        
        # Set class if provided
        if class_id:
            student_data['current_class_id'] = class_id
        
        # Process guardian data
        guardian_data['first_name'] = str(row['guardian_first_name']).strip()
        guardian_data['last_name'] = str(row['guardian_last_name']).strip()
        
        # Validate relationship
        try:
            relationship = validate_enum_value(row['relationship_to_student'], RelationshipType)
            if not relationship:
                errors.append(f"Row {row_index}: relationship_to_student is required")
            else:
                guardian_data['relationship_to_student'] = relationship
        except ValueError as e:
            errors.append(f"Row {row_index}: {str(e)}")
        
        # Process optional guardian fields
        if 'guardian_phone' in row:
            try:
                phone = validate_phone_number(row['guardian_phone'])
                if phone:
                    guardian_data['phone_number'] = phone
            except ValueError as e:
                errors.append(f"Row {row_index}: {str(e)}")
        
        if 'guardian_email' in row:
            try:
                email = validate_email(row['guardian_email'])
                if email:
                    guardian_data['email'] = email
            except ValueError as e:
                errors.append(f"Row {row_index}: {str(e)}")
        
        if 'guardian_address' in row and not pd.isna(row['guardian_address']):
            guardian_data['address'] = str(row['guardian_address']).strip()
        
        if 'guardian_occupation' in row and not pd.isna(row['guardian_occupation']):
            guardian_data['occupation'] = str(row['guardian_occupation']).strip()
        
        if 'guardian_income_range' in row:
            try:
                income = validate_enum_value(row['guardian_income_range'], IncomeRange)
                if income:
                    guardian_data['monthly_income_range'] = income
            except ValueError as e:
                errors.append(f"Row {row_index}: {str(e)}")
        
        if 'guardian_education_level' in row:
            try:
                education = validate_enum_value(row['guardian_education_level'], EducationLevel)
                if education:
                    guardian_data['education_level'] = education
            except ValueError as e:
                errors.append(f"Row {row_index}: {str(e)}")
        
    except Exception as e:
        errors.append(f"Row {row_index}: Unexpected error - {str(e)}")
    
    return student_data, guardian_data, errors
class GuardianBase(BaseModel):
    first_name: str
    last_name: str
    relationship_to_student: RelationshipType
    phone_number: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    occupation: Optional[str] = None
    monthly_income_range: Optional[IncomeRange] = None
    education_level: Optional[EducationLevel] = None

    class Config:
        from_attributes = True

class GuardianCreate(GuardianBase):
    pass

class GuardianResponse(GuardianBase):
    id: UUID

class StudentBase(BaseModel):
    student_number: str
    first_name: str
    last_name: str
    date_of_birth: date
    gender: Gender
    home_address: Optional[str] = None
    distance_to_school_km: Optional[float] = None
    transport_method: Optional[TransportMethod] = None
    enrollment_date: date
    special_needs: Optional[str] = None
    medical_conditions: Optional[str] = None

    class Config:
        from_attributes = True

class StudentCreate(StudentBase):
    guardian_id: UUID
    current_class_id: Optional[UUID] = None

class StudentUpdate(BaseModel):
    student_number: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[Gender] = None
    home_address: Optional[str] = None
    distance_to_school_km: Optional[float] = None
    transport_method: Optional[TransportMethod] = None
    enrollment_date: Optional[date] = None
    special_needs: Optional[str] = None
    medical_conditions: Optional[str] = None
    current_class_id: Optional[UUID] = None
    guardian_id: Optional[UUID] = None
    is_active: Optional[bool] = None

class StudentResponse(StudentBase):
    id: UUID
    age: int
    is_active: bool
    current_class_id: Optional[UUID] = None
    guardian_id: UUID

class StudentWithGuardianResponse(StudentResponse):
    guardian: GuardianResponse

class StudentWithClassResponse(StudentResponse):
    current_class: Optional[ClassResponse] = None

class StudentWithDetailsResponse(StudentWithGuardianResponse, StudentWithClassResponse):
    pass

class StudentClassHistoryResponse(BaseModel):
    id: UUID
    student_id: UUID
    class_id: UUID
    academic_year: str
    enrollment_date: date
    completion_date: Optional[date] = None
    status: StudentStatus
    reason_for_status_change: Optional[str] = None

    class Config:
        from_attributes = True

class StudentListResponse(BaseModel):
    students: List[StudentWithDetailsResponse]
    total_count: int

class UploadResponse(BaseModel):
    message: str
    records_added: int
    records_updated: int = 0
    errors: Optional[List[str]] = None
    warnings: Optional[List[str]] = None

class ValidationError(BaseModel):
    row: int
    field: str
    value: str
    error: str

# Helper functions
def get_student_or_404(db: Session, student_id: UUID):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    return student

def get_guardian_or_404(db: Session, guardian_id: UUID):
    guardian = db.query(Guardian).filter(Guardian.id == guardian_id).first()
    if not guardian:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guardian not found")
    return guardian

# Student CRUD endpoints
@router.post("", response_model=StudentResponse, status_code=status.HTTP_201_CREATED)
async def create_student(
    student_data: StudentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Check if student number already exists
    existing_student = db.query(Student).filter(
        Student.student_number == student_data.student_number
    ).first()
    
    if existing_student:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Student with this student number already exists"
        )
    
    # Validate guardian exists
    get_guardian_or_404(db, student_data.guardian_id)
    
    # Validate class exists if provided
    if student_data.current_class_id:
        get_class_or_404(db, student_data.current_class_id)
    
    # Calculate age
    age = calculate_age(student_data.date_of_birth)
    
    # Create student
    db_student = Student(
        **student_data.model_dump(),
        age=age
    )
    
    db.add(db_student)
    db.commit()
    db.refresh(db_student)
    return db_student

@router.get("", response_model=StudentListResponse)
async def get_students(
    skip: int = 0,
    limit: int = 100,
    is_active: Optional[bool] = None,
    class_id: Optional[UUID] = None,
    gender: Optional[Gender] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Student).options(
        joinedload(Student.guardian),
        joinedload(Student.current_class)
    )
    
    if is_active is not None:
        query = query.filter(Student.is_active == is_active)
    
    if class_id:
        query = query.filter(Student.current_class_id == class_id)
    
    if gender:
        query = query.filter(Student.gender == gender)
    
    students = query.offset(skip).limit(limit).all()
    total_count = query.count()
    
    return StudentListResponse(students=students, total_count=total_count)

@router.get("/{student_id}", response_model=StudentWithDetailsResponse)
async def get_student(
    student_id: UUID,
    db: Session = Depends(get_db)
):
    student = db.query(Student).options(
        joinedload(Student.guardian),
        joinedload(Student.current_class)
    ).filter(Student.id == student_id).first()
    
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    
    return student

@router.put("/{student_id}", response_model=StudentResponse)
async def update_student(
    student_id: UUID,
    student_data: StudentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    db_student = get_student_or_404(db, student_id)
    
    # Validate student number if being updated
    if student_data.student_number and student_data.student_number != db_student.student_number:
        existing = db.query(Student).filter(
            Student.student_number == student_data.student_number,
            Student.id != student_id
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Student with this student number already exists"
            )
    
    # Validate guardian exists if being updated
    if student_data.guardian_id:
        get_guardian_or_404(db, student_data.guardian_id)
    
    # Validate class exists if being updated
    if student_data.current_class_id:
        get_class_or_404(db, student_data.current_class_id)
    
    # Calculate age if date of birth is being updated
    if student_data.date_of_birth:
        student_data.age = calculate_age(student_data.date_of_birth)
    
    update_data = student_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_student, field, value)
    
    db.commit()
    db.refresh(db_student)
    return db_student

@router.delete("/{student_id}", response_model=StudentResponse)
async def delete_student(
    student_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Only allow admins to delete students
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can delete students"
        )
    
    db_student = get_student_or_404(db, student_id)
    db_student.is_active = False
    db.commit()
    db.refresh(db_student)
    return db_student

# Student history endpoints
@router.get("/{student_id}/history", response_model=List[StudentClassHistoryResponse])
async def get_student_history(
    student_id: UUID,
    db: Session = Depends(get_db)
):
    get_student_or_404(db, student_id)
    
    history = db.query(StudentClassHistory).filter(
        StudentClassHistory.student_id == student_id
    ).order_by(StudentClassHistory.academic_year).all()
    
    return history

# Guardian endpoints
@router.post("/guardians", response_model=GuardianResponse, status_code=status.HTTP_201_CREATED)
async def create_guardian(
    guardian_data: GuardianCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    db_guardian = Guardian(**guardian_data.model_dump())
    db.add(db_guardian)
    db.commit()
    db.refresh(db_guardian)
    return db_guardian

@router.get("/guardians/{guardian_id}", response_model=GuardianResponse)
async def get_guardian(
    guardian_id: UUID,
    db: Session = Depends(get_db)
):
    return get_guardian_or_404(db, guardian_id)

@router.get("/guardians/{guardian_id}/students", response_model=List[StudentResponse])
async def get_guardian_students(
    guardian_id: UUID,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    get_guardian_or_404(db, guardian_id)
    
    query = db.query(Student).filter(Student.guardian_id == guardian_id)
    
    if is_active is not None:
        query = query.filter(Student.is_active == is_active)
    
    return query.all()

# CSV Upload endpoints (keep the existing implementation from your code)
@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_student_csv(
    file: UploadFile = File(...),
    class_id: Optional[str] = Form(None),
    term: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Keep your existing implementation
    pass

@router.get("/upload/template")
async def get_csv_template(
    # current_user: User = Depends(get_current_user)
):
    """
    Download a CSV template for student uploads.
    """
    
    # if current_user.role not in [UserRole.TEACHER, UserRole.ADMIN, UserRole.HEADTEACHER]:
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN,
    #         detail="Access denied."
    #     )
    
    # Create template headers
    headers = (
        REQUIRED_STUDENT_FIELDS + 
        OPTIONAL_STUDENT_FIELDS + 
        REQUIRED_GUARDIAN_FIELDS + 
        OPTIONAL_GUARDIAN_FIELDS
    )
    
    # Create sample data
    sample_data = {
        'first_name': ['John', 'Jane'],
        'last_name': ['Banda', 'Mwale'],
        'date_of_birth': ['2010-05-15', '2011-03-22'],
        'gender': ['male', 'female'],
        'student_number': ['STU001', 'STU002'],
        'home_address': ['123 Main St, Lilongwe', '456 Oak Ave, Blantyre'],
        'distance_to_school_km': [2.5, 1.8],
        'transport_method': ['walking', 'bicycle'],
        'special_needs': ['', 'Hearing impaired'],
        'medical_conditions': ['', 'Asthma'],
        'enrollment_date': ['2024-01-15', '2024-01-15'],
        'guardian_first_name': ['Peter', 'Mary'],
        'guardian_last_name': ['Banda', 'Mwale'],
        'relationship_to_student': ['parent', 'parent'],
        'guardian_phone': ['+265991234567', '+265998765432'],
        'guardian_email': ['peter.banda@email.com', 'mary.mwale@email.com'],
        'guardian_address': ['123 Main St, Lilongwe', '456 Oak Ave, Blantyre'],
        'guardian_occupation': ['Teacher', 'Nurse'],
        'guardian_income_range': ['50k_100k', '100k_200k'],
        'guardian_education_level': ['tertiary', 'tertiary']
    }
    
    # Create DataFrame and CSV
    template_df = pd.DataFrame(sample_data)
    csv_buffer = io.StringIO()
    template_df.to_csv(csv_buffer, index=False)
    
    from fastapi.responses import StreamingResponse
    
    return StreamingResponse(
        io.BytesIO(csv_buffer.getvalue().encode('utf-8')),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=student_upload_template.csv"}
    )
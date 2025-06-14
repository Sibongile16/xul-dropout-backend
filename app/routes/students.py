from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import IntegrityError
from typing import List, Optional
import pandas as pd
import io
from datetime import datetime, date
from uuid import UUID


from app.database import get_db
from app.utils.auth import get_current_user
from app.models.all_models import (
    AttendanceStatus, User, Student, Guardian, Class, Gender, RelationshipType, 
    TransportMethod, IncomeRange, EducationLevel, StudentStatus,
    StudentClassHistory, AttendanceRecord, DropoutPrediction, UserRole
)
from pytz import timezone

router = APIRouter(prefix="/api/students", tags=["students"])

# Pydantic Models
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

class ClassResponse(BaseModel):
    id: UUID
    name: str
    code: str
    academic_year: str

    class Config:
        from_attributes = True

class StudentWithClassResponse(StudentResponse):
    current_class: Optional[ClassResponse] = None

class StudentWithDetailsResponse(StudentWithGuardianResponse, StudentWithClassResponse):
    pass

class StudentClassHistoryResponse(BaseModel):
    id: UUID
    class_id: UUID
    academic_year: str
    enrollment_date: date
    completion_date: Optional[date] = None
    status: StudentStatus
    reason_for_status_change: Optional[str] = None
    class_info: ClassResponse

    class Config:
        from_attributes = True

class StudentListResponse(BaseModel):
    students: List[StudentWithDetailsResponse]
    total_count: int

class StudentRiskResponse(BaseModel):
    id: UUID
    name: str
    risk_score: float
    risk_level: str
    absences: int
    current_class: Optional[str] = None

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

# Helper Functions
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

def calculate_age(birth_date: date) -> int:
    today = date.today()
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))

# Student CRUD Endpoints
@router.post("", response_model=StudentResponse, status_code=status.HTTP_201_CREATED)
async def create_student(
    student_data: StudentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Check if student number exists
    existing_student = db.query(Student).filter(
        Student.student_number == student_data.student_number
    ).first()
    
    if existing_student:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Student with this number already exists"
        )
    
    # Validate guardian exists
    get_guardian_or_404(db, student_data.guardian_id)
    
    # Validate class exists if provided
    if student_data.current_class_id:
        class_ = db.query(Class).filter(Class.id == student_data.current_class_id).first()
        if not class_:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Class not found"
            )
    
    # Calculate age
    age = calculate_age(student_data.date_of_birth)
    
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
    
    # Validate student number
    if student_data.student_number and student_data.student_number != db_student.student_number:
        existing = db.query(Student).filter(
            Student.student_number == student_data.student_number,
            Student.id != student_id
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Student number already exists"
            )
    
    # Validate guardian exists
    if student_data.guardian_id:
        get_guardian_or_404(db, student_data.guardian_id)
    
    # Validate class exists
    if student_data.current_class_id:
        class_ = db.query(Class).filter(Class.id == student_data.current_class_id).first()
        if not class_:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Class not found"
            )
    
    # Calculate age if DOB changes
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

# Student History Endpoints
@router.get("/{student_id}/history", response_model=List[StudentClassHistoryResponse])
async def get_student_history(
    student_id: UUID,
    db: Session = Depends(get_db)
):
    get_student_or_404(db, student_id)
    
    history = db.query(StudentClassHistory).options(
        joinedload(StudentClassHistory.class_)
    ).filter(
        StudentClassHistory.student_id == student_id
    ).order_by(StudentClassHistory.academic_year).all()
    
    return history

# Guardian Endpoints
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

# Risk Assessment Endpoints
@router.get("/{student_id}/risk", response_model=StudentRiskResponse)
async def get_student_risk(
    student_id: UUID,
    db: Session = Depends(get_db)
):
    student = get_student_or_404(db, student_id)
    
    # Get latest prediction
    prediction = db.query(DropoutPrediction).filter(
        DropoutPrediction.student_id == student_id
    ).order_by(DropoutPrediction.prediction_date.desc()).first()
    
    # Get absences in current academic year
    academic_year = student.current_class.academic_year if student.current_class else str(datetime.now().year)
    year_start, year_end = get_academic_year_dates(academic_year)
    
    absences = db.query(func.count(AttendanceRecord.id)).filter(
        AttendanceRecord.student_id == student_id,
        AttendanceRecord.status == AttendanceStatus.ABSENT,
        AttendanceRecord.date >= year_start,
        AttendanceRecord.date <= year_end
    ).scalar() or 0
    
    return StudentRiskResponse(
        id=student.id,
        name=f"{student.first_name} {student.last_name}",
        risk_score=prediction.risk_score if prediction else 0.0,
        risk_level=prediction.risk_level.value if prediction else "low",
        absences=absences,
        current_class=student.current_class.name if student.current_class else None
    )

# CSV Upload Endpoints (keep existing implementation)
CSV_FIELDS = [
    'first_name', 'last_name', 'date_of_birth', 'gender', 'student_number',
    'home_address', 'distance_to_school_km', 'transport_method',
    'special_needs', 'medical_conditions', 'enrollment_date',
    'guardian_first_name', 'guardian_last_name', 'relationship_to_student',
    'guardian_phone', 'guardian_email', 'guardian_address',
    'guardian_occupation', 'guardian_income_range', 'guardian_education_level'
]

@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_student_csv(
    file: UploadFile = File(...),
    class_id: Optional[str] = Form(None),
    term: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Authorization check
    if current_user.role not in [UserRole.TEACHER, UserRole.ADMIN, UserRole.HEADTEACHER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only teachers and administrators can upload student data"
        )
    
    # Validate file type
    if not file.filename.lower().endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are accepted"
        )
    
    # Validate class exists if provided
    if class_id:
        class_ = db.query(Class).filter(Class.id == class_id).first()
        if not class_:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Class not found"
            )
    
    try:
        # Read CSV
        contents = await file.read()
        df = pd.read_csv(io.StringIO(contents.decode('utf-8')))
        
        if df.empty:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CSV file is empty"
            )
        
        # Validate headers
        missing_fields = [field for field in CSV_FIELDS if field not in df.columns]
        if missing_fields:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Missing required fields: {', '.join(missing_fields)}"
            )
        
        # Process rows
        records_added = 0
        records_updated = 0
        errors = []
        warnings = []
        
        for index, row in df.iterrows():
            try:
                # Process student and guardian data
                student_data = {
                    'student_number': str(row['student_number']).strip(),
                    'first_name': str(row['first_name']).strip(),
                    'last_name': str(row['last_name']).strip(),
                    'date_of_birth': pd.to_datetime(row['date_of_birth']).date(),
                    'gender': Gender[row['gender'].lower()],
                    'enrollment_date': pd.to_datetime(row['enrollment_date']).date() if pd.notna(row['enrollment_date']) else date.today(),
                    'home_address': str(row['home_address']) if pd.notna(row['home_address']) else None,
                    'distance_to_school_km': float(row['distance_to_school_km']) if pd.notna(row['distance_to_school_km']) else None,
                    'transport_method': TransportMethod[row['transport_method'].lower()] if pd.notna(row['transport_method']) else None,
                    'special_needs': str(row['special_needs']) if pd.notna(row['special_needs']) else None,
                    'medical_conditions': str(row['medical_conditions']) if pd.notna(row['medical_conditions']) else None,
                    'current_class_id': class_id
                }
                
                guardian_data = {
                    'first_name': str(row['guardian_first_name']).strip(),
                    'last_name': str(row['guardian_last_name']).strip(),
                    'relationship_to_student': RelationshipType[row['relationship_to_student'].lower()],
                    'phone_number': str(row['guardian_phone']) if pd.notna(row['guardian_phone']) else None,
                    'email': str(row['guardian_email']) if pd.notna(row['guardian_email']) else None,
                    'address': str(row['guardian_address']) if pd.notna(row['guardian_address']) else None,
                    'occupation': str(row['guardian_occupation']) if pd.notna(row['guardian_occupation']) else None,
                    'monthly_income_range': IncomeRange[row['guardian_income_range'].lower()] if pd.notna(row['guardian_income_range']) else None,
                    'education_level': EducationLevel[row['guardian_education_level'].lower()] if pd.notna(row['guardian_education_level']) else None
                }
                
                # Find or create guardian
                guardian = db.query(Guardian).filter(
                    Guardian.first_name.ilike(guardian_data['first_name']),
                    Guardian.last_name.ilike(guardian_data['last_name']),
                    Guardian.relationship_to_student == guardian_data['relationship_to_student']
                ).first()
                
                if guardian:
                    # Update existing guardian
                    for key, value in guardian_data.items():
                        if value is not None:
                            setattr(guardian, key, value)
                    guardian_id = guardian.id
                else:
                    # Create new guardian
                    guardian = Guardian(**guardian_data)
                    db.add(guardian)
                    db.flush()
                    guardian_id = guardian.id
                
                # Find or create student
                student = db.query(Student).filter(
                    Student.student_number == student_data['student_number']
                ).first()
                
                if student:
                    # Update existing student
                    student_data['guardian_id'] = guardian_id
                    for key, value in student_data.items():
                        if value is not None:
                            setattr(student, key, value)
                    records_updated += 1
                    warnings.append(f"Updated student {student_data['student_number']}")
                else:
                    # Create new student
                    student_data['guardian_id'] = guardian_id
                    student_data['age'] = calculate_age(student_data['date_of_birth'])
                    student = Student(**student_data)
                    db.add(student)
                    records_added += 1
                
            except Exception as e:
                errors.append(f"Row {index + 2}: {str(e)}")
                continue
        
        # Commit changes
        if records_added > 0 or records_updated > 0:
            try:
                db.commit()
            except IntegrityError as e:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Database error: {str(e)}"
                )
        else:
            db.rollback()
        
        return UploadResponse(
            message="Upload completed",
            records_added=records_added,
            records_updated=records_updated,
            errors=errors if errors else None,
            warnings=warnings if warnings else None
        )
    
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing file: {str(e)}"
        )

@router.get("/upload/template")
async def get_csv_template():
    # Create sample data
    sample_data = {
        'first_name': ['John', 'Jane'],
        'last_name': ['Doe', 'Smith'],
        'date_of_birth': ['2010-05-15', '2011-03-22'],
        'gender': ['male', 'female'],
        'student_number': ['STU001', 'STU002'],
        'home_address': ['123 Main St', '456 Oak Ave'],
        'distance_to_school_km': [2.5, 1.8],
        'transport_method': ['walking', 'bicycle'],
        'special_needs': ['', 'Hearing impaired'],
        'medical_conditions': ['', 'Asthma'],
        'enrollment_date': ['2023-01-10', '2023-01-10'],
        'guardian_first_name': ['Mary', 'James'],
        'guardian_last_name': ['Doe', 'Smith'],
        'relationship_to_student': ['parent', 'parent'],
        'guardian_phone': ['+265991234567', '+265998765432'],
        'guardian_email': ['mary@example.com', 'james@example.com'],
        'guardian_address': ['123 Main St', '456 Oak Ave'],
        'guardian_occupation': ['Teacher', 'Engineer'],
        'guardian_income_range': ['50k_100k', '100k_200k'],
        'guardian_education_level': ['secondary', 'tertiary']
    }
    
    # Create DataFrame
    df = pd.DataFrame(sample_data)
    
    # Convert to CSV
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    
    from fastapi.responses import StreamingResponse
    
    return StreamingResponse(
        io.BytesIO(csv_buffer.getvalue().encode('utf-8')),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=student_upload_template.csv"}
    )

def get_academic_year_dates(academic_year: str):
    try:
        start_year = int(academic_year.split('-')[0])
        return date(start_year, 9, 1), date(start_year + 1, 8, 31)
    except:
        current_year = datetime.now().year
        return date(current_year, 1, 1), date(current_year, 12, 31)
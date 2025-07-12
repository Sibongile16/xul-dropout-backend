from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import datetime, date
from uuid import UUID

from app.database import get_db
from app.utils.auth import get_current_user
from app.models.all_models import (
    Subject, User, Student, Guardian, Class, Gender, RelationshipType, 
    TransportMethod, IncomeLevel, StudentStatus, AcademicTerm,
    SubjectScore, DropoutPrediction, UserRole, TermType
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

    class Config:
        from_attributes = True

class GuardianCreate(GuardianBase):
    pass

class GuardianResponse(GuardianBase):
    id: UUID

class SubjectScoreResponse(BaseModel):
    subject_name: str
    score: float
    grade: str

class TermPerformanceResponse(BaseModel):
    term_id: UUID
    term_type: TermType
    academic_year: str
    standard: int
    term_avg_score: float
    present_days: int
    absent_days: int
    subject_scores: List[SubjectScoreResponse]

    class Config:
        from_attributes = True

class StudentBase(BaseModel):
    student_id: str
    first_name: str
    last_name: str
    date_of_birth: date
    gender: Gender
    home_address: Optional[str] = None
    distance_to_school: Optional[float] = None
    transport_method: Optional[TransportMethod] = None
    enrollment_date: date
    special_learning: Optional[bool] = None
    textbook_availability: Optional[bool] = None
    class_repetitions: Optional[int] = None
    household_income: Optional[IncomeLevel] = None

    class Config:
        from_attributes = True

class StudentCreate(StudentBase):
    guardian_id: UUID
    class_id: Optional[UUID] = None

class StudentUpdate(BaseModel):
    student_id: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[Gender] = None
    home_address: Optional[str] = None
    distance_to_school: Optional[float] = None
    transport_method: Optional[TransportMethod] = None
    enrollment_date: Optional[date] = None
    special_learning: Optional[bool] = None
    textbook_availability: Optional[bool] = None
    class_repetitions: Optional[int] = None
    household_income: Optional[IncomeLevel] = None
    class_id: Optional[UUID] = None
    guardian_id: Optional[UUID] = None
    status: Optional[StudentStatus] = None

class StudentResponse(StudentBase):
    id: UUID
    age: int
    status: StudentStatus
    class_id: Optional[UUID] = None
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
    performance_history: Optional[List[TermPerformanceResponse]] = None

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
    last_term_avg: Optional[float] = None

class UploadResponse(BaseModel):
    message: str
    records_added: int
    records_updated: int = 0
    errors: Optional[List[str]] = None
    warnings: Optional[List[str]] = None

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

def get_student_performance(db: Session, student_id: UUID):
    terms = db.query(AcademicTerm).filter(
        AcademicTerm.student_id == student_id
    ).order_by(
        AcademicTerm.academic_year,
        AcademicTerm.term_type
    ).all()

    performance = []
    for term in terms:
        scores = db.query(
            SubjectScore,
            Subject.name.label('subject_name')
        ).join(
            Subject,
            SubjectScore.subject_id == Subject.id
        ).filter(
            SubjectScore.academic_term_id == term.id
        ).all()

        performance.append(TermPerformanceResponse(
            term_id=term.id,
            term_type=term.term_type,
            academic_year=term.academic_year,
            standard=term.standard,
            term_avg_score=term.term_avg_score,
            present_days=term.present_days,
            absent_days=term.absent_days,
            subject_scores=[
                SubjectScoreResponse(
                    subject_name=score.subject_name,
                    score=score.score,
                    grade=score.grade
                ) for score in scores
            ]
        ))

    return performance

# Student CRUD Endpoints
@router.post("", response_model=StudentResponse, status_code=status.HTTP_201_CREATED)
async def create_student(
    student_data: StudentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Check if student ID exists
    existing_student = db.query(Student).filter(
        Student.id == student_data.student_id
    ).first()
    
    if existing_student:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Student with this ID already exists"
        )
    
    # Validate guardian exists
    get_guardian_or_404(db, student_data.guardian_id)
    
    # Validate class exists if provided
    if student_data.class_id:
        class_ = db.query(Class).filter(Class.id == student_data.class_id).first()
        if not class_:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Class not found"
            )
    
    # Calculate age
    age = calculate_age(student_data.date_of_birth)
    
    db_student = Student(
        **student_data.model_dump(),
        age=age,
        status=StudentStatus.ACTIVE
    )
    
    db.add(db_student)
    db.commit()
    db.refresh(db_student)
    return db_student

@router.get("", response_model=StudentListResponse)
async def get_students(
    skip: int = 0,
    limit: int = 100,
    status: Optional[StudentStatus] = None,
    class_id: Optional[UUID] = None,
    gender: Optional[Gender] = None,
    include_performance: bool = False,
    db: Session = Depends(get_db)
):
    query = db.query(Student).options(
        joinedload(Student.guardian),
        joinedload(Student.class_)
    )
    
    if status is not None:
        query = query.filter(Student.status == status)
    
    if class_id:
        query = query.filter(Student.class_id == class_id)
    
    if gender:
        query = query.filter(Student.gender == gender)
    
    students = query.offset(skip).limit(limit).all()
    total_count = query.count()
    
    student_responses = []
    for student in students:
        student_data = StudentWithDetailsResponse.model_validate(student)
        if include_performance:
            student_data.performance_history = get_student_performance(db, student.id)
        student_responses.append(student_data)
    
    return StudentListResponse(
        students=student_responses,
        total_count=total_count
    )

@router.get("/{student_id}", response_model=StudentWithDetailsResponse)
async def get_student(
    student_id: UUID,
    include_performance: bool = False,
    db: Session = Depends(get_db)
):
    student = db.query(Student).options(
        joinedload(Student.guardian),
        joinedload(Student.class_)
    ).filter(Student.id == student_id).first()
    
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    
    response = StudentWithDetailsResponse.model_validate(student)
    if include_performance:
        response.performance_history = get_student_performance(db, student_id)
    
    return response

@router.put("/{student_id}", response_model=StudentResponse)
async def update_student(
    student_id: UUID,
    student_data: StudentUpdate,
    db: Session = Depends(get_db)
):
    db_student = get_student_or_404(db, student_id)
    
    # Validate student ID
    if student_data.student_id and student_data.student_id != db_student.id:
        existing = db.query(Student).filter(
            Student.student_id == student_data.student_id,
            Student.id != student_id
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Student ID already exists"
            )
    
    # Validate guardian exists
    if student_data.guardian_id:
        get_guardian_or_404(db, student_data.guardian_id)
    
    # Validate class exists
    if student_data.class_id:
        class_ = db.query(Class).filter(Class.id == student_data.class_id).first()
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
):
    
    db_student = get_student_or_404(db, student_id)
    db_student.status = StudentStatus.DROPPED_OUT
    db.commit()
    db.refresh(db_student)
    return db_student

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
    
    # Get latest term performance
    latest_term = db.query(AcademicTerm).filter(
        AcademicTerm.student_id == student_id
    ).order_by(
        AcademicTerm.academic_year.desc(),
        AcademicTerm.term_type.desc()
    ).first()
    
    return StudentRiskResponse(
        id=student.id,
        name=f"{student.first_name} {student.last_name}",
        risk_score=prediction.risk_score if prediction else 0.0,
        risk_level=prediction.risk_level.value if prediction else "low",
        absences=latest_term.absent_days if latest_term else 0,
        current_class=student.class_.name if student.class_ else None,
        last_term_avg=latest_term.term_avg_score if latest_term else None
    )


def get_academic_year_dates(academic_year: str):
    try:
        start_year = int(academic_year.split('-')[0])
        return date(start_year, 9, 1), date(start_year + 1, 8, 31)
    except:
        current_year = datetime.now().year
        return date(current_year, 1, 1), date(current_year, 12, 31)
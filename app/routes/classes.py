from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.models.all_models import Class, Student, TeacherClass, Teacher, Guardian
from typing import List, Optional
from pydantic import BaseModel
from uuid import UUID

router = APIRouter(prefix="/api/classes", tags=["classes"])

# Pydantic models
class ClassCreate(BaseModel):
    name: str
    code: str
    academic_year: str
    capacity: Optional[int] = None
    is_active: bool = True

class ClassUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    academic_year: Optional[str] = None
    capacity: Optional[int] = None
    is_active: Optional[bool] = None

class ClassResponse(BaseModel): 
    id: UUID
    name: str
    code: str
    academic_year: str
    capacity: Optional[int] = None
    is_active: bool
    
    class Config:
        from_attributes = True

class ClassListResponse(BaseModel):
    classes: List[ClassResponse]
    total_count: int

class StudentResponse(BaseModel):
    id: UUID
    student_number: str
    first_name: str
    last_name: str
    date_of_birth: str
    age: int
    gender: str
    home_address: Optional[str] = None
    enrollment_date: str
    is_active: bool
    
    class Config:
        from_attributes = True

class GuardianResponse(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    relationship_to_student: str
    phone_number: Optional[str] = None
    
    class Config:
        from_attributes = True

class StudentWithGuardianResponse(StudentResponse):
    guardian: GuardianResponse

class TeacherResponse(BaseModel):
    id: UUID
    first_name: str
    last_name: str
    phone_number: Optional[str] = None
    
    class Config:
        from_attributes = True

class ClassWithStudentsResponse(ClassResponse):
    students: List[StudentWithGuardianResponse]

class ClassWithTeachersResponse(ClassResponse):
    teachers: List[TeacherResponse]

# Helper function to get class or raise 404
def get_class_or_404(db: Session, class_id: UUID):
    db_class = db.query(Class).filter(Class.id == class_id).first()
    if not db_class:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")
    return db_class

# Create a new class
@router.post("/", response_model=ClassResponse, status_code=status.HTTP_201_CREATED)
async def create_class(class_data: ClassCreate, db: Session = Depends(get_db)):
    # Check if class with same code and academic year already exists
    existing_class = db.query(Class).filter(
        Class.code == class_data.code,
        Class.academic_year == class_data.academic_year
    ).first()
    
    if existing_class:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Class with this code already exists for the academic year"
        )
    
    db_class = Class(**class_data.model_dump())
    db.add(db_class)
    db.commit()
    db.refresh(db_class)
    return db_class

# Get all classes
@router.get("/", response_model=ClassListResponse)
async def get_classes(
    skip: int = 0,
    limit: int = 100,
    is_active: Optional[bool] = None,
    academic_year: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Class)
    
    if is_active is not None:
        query = query.filter(Class.is_active == is_active)
    
    if academic_year:
        query = query.filter(Class.academic_year == academic_year)
    
    classes = query.offset(skip).limit(limit).all()
    total_count = query.count()
    
    return ClassListResponse(classes=classes, total_count=total_count)

# Get a class by ID
@router.get("/{class_id}", response_model=ClassResponse)
async def get_class_by_id(class_id: UUID, db: Session = Depends(get_db)):
    return get_class_or_404(db, class_id)

# Update a class
@router.put("/{class_id}", response_model=ClassResponse)
async def update_class(
    class_id: UUID, 
    class_data: ClassUpdate, 
    db: Session = Depends(get_db)
):
    db_class = get_class_or_404(db, class_id)
    
    update_data = class_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_class, field, value)
    
    db.commit()
    db.refresh(db_class)
    return db_class

# Delete a class (soft delete by setting is_active=False)
@router.delete("/{class_id}", response_model=ClassResponse)
async def delete_class(class_id: UUID, db: Session = Depends(get_db)):
    db_class = get_class_or_404(db, class_id)
    db_class.is_active = False
    db.commit()
    db.refresh(db_class)
    return db_class

# Get classes by academic year
@router.get("/academic-year/{academic_year}", response_model=ClassListResponse)
async def get_classes_by_academic_year(
    academic_year: str,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    classes = db.query(Class).filter(
        Class.academic_year == academic_year
    ).offset(skip).limit(limit).all()
    
    total_count = db.query(Class).filter(
        Class.academic_year == academic_year
    ).count()
    
    return ClassListResponse(classes=classes, total_count=total_count)

# Get classes with students
@router.get("/with-students", response_model=List[ClassWithStudentsResponse])
async def get_classes_with_students(
    academic_year: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Class).options(
        joinedload(Class.students).joinedload(Student.guardian)
    )
    
    if academic_year:
        query = query.filter(Class.academic_year == academic_year)
    
    if is_active is not None:
        query = query.filter(Class.is_active == is_active)
    
    classes = query.all()
    return classes

# Get students by class ID
@router.get("/{class_id}/students", response_model=List[StudentWithGuardianResponse])
async def get_students_by_class_id(
    class_id: UUID,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Student).filter(
        Student.current_class_id == class_id
    ).options(joinedload(Student.guardian))
    
    if is_active is not None:
        query = query.filter(Student.is_active == is_active)
    
    students = query.all()
    return students

# Get teachers assigned to a class
@router.get("/{class_id}/teachers", response_model=List[TeacherResponse])
async def get_class_teachers(
    class_id: UUID,
    academic_year: Optional[str] = None,
    is_class_teacher: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Teacher).join(TeacherClass).filter(
        TeacherClass.class_id == class_id
    )
    
    if academic_year:
        query = query.filter(TeacherClass.academic_year == academic_year)
    
    if is_class_teacher is not None:
        query = query.filter(TeacherClass.is_class_teacher == is_class_teacher)
    
    teachers = query.all()
    return teachers

# Get class with students and teachers
@router.get("/{class_id}/full-details", response_model=ClassWithStudentsResponse)
async def get_class_full_details(
    class_id: UUID,
    db: Session = Depends(get_db)
):
    db_class = db.query(Class).options(
        joinedload(Class.students).joinedload(Student.guardian),
        joinedload(Class.teacher_classes).joinedload(TeacherClass.teacher)
    ).filter(Class.id == class_id).first()
    
    if not db_class:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")
    
    return db_class
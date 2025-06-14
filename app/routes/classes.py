from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from app.database import get_db
from app.models.all_models import Class, Student
from typing import List
from pydantic import BaseModel
from uuid import UUID

router = APIRouter(prefix="/api/classes", tags=["classes"])

class ClassCreate(BaseModel):
    name: str
    description: str

class ClassUpdate(BaseModel):
    name: str
    description: str

class ClassResponse(BaseModel): 
    id: UUID
    name: str
    description: str

class ClassListResponse(BaseModel):
    classes: List[ClassResponse]
    total_count: int

class StudentResponse(BaseModel):
    id: UUID
    name: str
    age: int
    gender: str
    guardian_name: str
    guardian_phone: str

class ClassWithStudentsResponse(BaseModel):
    id: UUID
    name: str
    description: str
    students: List[StudentResponse]

# route to create a new class
@router.post("/classes", response_model=ClassResponse)
async def create_class(class_data: ClassCreate, db: Session = Depends(get_db)):
    db_class = Class(**class_data.model_dump())
    db.add(db_class)
    db.commit()
    db.refresh(db_class)
    return db_class


# route to get all classes
@router.get("/classes", response_model=ClassListResponse)
async def get_classes(db: Session = Depends(get_db)):
    classes = db.query(Class).all()
    return ClassListResponse(classes=classes, total_count=len(classes))


# route to get a class by id
@router.get("/classes/{class_id}", response_model=ClassResponse)
async def get_class_by_id(class_id: UUID, db: Session = Depends(get_db)):
    class_ = db.query(Class).filter(Class.id == class_id).first()
    if not class_:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")
    return class_


# route to update a class
@router.put("/classes/{class_id}", response_model=ClassResponse)
async def update_class(class_id: UUID, class_data: ClassUpdate, db: Session = Depends(get_db)):
    db_class = db.query(Class).filter(Class.id == class_id).first()
    if not db_class:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")
    db_class.name = class_data.name
    db_class.description = class_data.description
    db.commit()
    db.refresh(db_class)
    return db_class


# route to delete a class
@router.delete("/classes/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_class(class_id: UUID, db: Session = Depends(get_db)):
    db.query(Class).filter(Class.id == class_id).delete()
    db.commit()     
    

# route to get classes by academic year
@router.get("/classes/academic-year/{academic_year}", response_model=ClassListResponse)
async def get_classes_by_academic_year(academic_year: int, db: Session = Depends(get_db)):
    classes = db.query(Class).filter(Class.academic_year == academic_year).all()
    return ClassListResponse(classes=classes, total_count=len(classes))


# route to get classes with students
@router.get("/classes/with-students", response_model=List[ClassWithStudentsResponse])
async def get_classes_with_students(db: Session = Depends(get_db)):
    classes = db.query(Class).options(joinedload(Class.students)).all()
    return classes


# route to get students by class id
@router.get("/classes/{class_id}/students", response_model=List[StudentResponse])
async def get_students_by_class_id(class_id: UUID, db: Session = Depends(get_db)):
    students = db.query(Student).filter(Student.class_id == class_id).all()
    return students

# route to get students by class id and academic year
@router.get("/classes/{class_id}/students/academic-year/{academic_year}", response_model=List[StudentResponse])
async def get_students_by_class_id_and_academic_year(class_id: UUID, academic_year: int, db: Session = Depends(get_db)):
    students = db.query(Student).filter(Student.class_id == class_id, Student.academic_year == academic_year).all()
    return students

# route to get students by class id and academic year and term
@router.get("/classes/{class_id}/students/academic-year/{academic_year}/term/{term}", response_model=List[StudentResponse])
async def get_students_by_class_id_and_academic_year_and_term(class_id: UUID, academic_year: int, term: str, db: Session = Depends(get_db)):
    students = db.query(Student).filter(Student.class_id == class_id, Student.academic_year == academic_year, Student.term == term).all()
    return students





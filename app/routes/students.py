from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.models.all_models import Student, User
from app.database import get_db
from app.utils.security import get_current_user
from app.schemas.student import StudentCreate, StudentResponse, StudentUpdate

router = APIRouter(prefix="/students", tags=["students"])

@router.get("/", response_model=list[StudentResponse])
async def get_students(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    students = db.query(Student).all()
    return students 

@router.get("/{student_id}", response_model=StudentResponse)
async def get_student(student_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    return student

@router.post("/", response_model=StudentResponse)
async def create_student(student: StudentCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):      
    db_student = Student(**student.model_dump())
    db.add(db_student)
    db.commit()
    db.refresh(db_student)
    return db_student

@router.put("/{student_id}", response_model=StudentResponse)
async def update_student(student_id: int, student: StudentUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_student = db.query(Student).filter(Student.id == student_id).first()
    if not db_student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    for field, value in student.model_dump().items():
        setattr(db_student, field, value)
    db.commit()
    db.refresh(db_student)
    return db_student

@router.delete("/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_student(student_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_student = db.query(Student).filter(Student.id == student_id).first()
    if not db_student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    db.delete(db_student)
    db.commit()

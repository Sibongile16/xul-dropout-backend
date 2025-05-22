from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.models.all_models import Teacher, User
from app.database import get_db
from app.utils.security import get_current_user
from app.schemas.teacher import TeacherResponse

router = APIRouter(prefix="/teachers", tags=["teachers"])

@router.get("/", response_model=list[TeacherResponse])
async def get_teachers(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    teachers = db.query(Teacher).all()
    return teachers

@router.get("/{teacher_id}", response_model=TeacherResponse)
async def get_teacher(teacher_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not teacher:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found")
    return teacher

# @router.post("/", response_model=TeacherResponse)
# async def create_teacher(teacher: Teacher, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
#     db_teacher = Teacher(**teacher.model_dump())
#     db.add(db_teacher)
#     db.commit()
#     db.refresh(db_teacher)
#     return db_teacher

# @router.put("/{teacher_id}", response_model=TeacherResponse)
# async def update_teacher(teacher_id: int, teacher: Teacher, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
#     db_teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
#     if not db_teacher:
#         raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found")
#     for field, value in teacher.model_dump().items():
#         setattr(db_teacher, field, value)
#     db.commit()
#     db.refresh(db_teacher)
#     return db_teacher

@router.delete("/{teacher_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_teacher(teacher_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_teacher = db.query(Teacher).filter(Teacher.id == teacher_id).first()
    if not db_teacher:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found")
    db.delete(db_teacher)
    db.commit()





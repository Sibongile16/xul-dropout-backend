from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from app.database import get_db
from sqlalchemy.orm import Session
from app.models.all_models import Student, Teacher, User
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

@router.get("/students/class/{class_id}")
async def get_students_by_class(
    class_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Get teacher record
    teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
    if not teacher:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Teacher not found")

    # Verify teacher teaches this class
    if class_id not in [tc.class_id for tc in teacher.teacher_classes]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not teach this class"
        )

    # Get students in the class
    students = db.query(Student).filter(Student.current_class_id == class_id).all()

    # Format student data according to spec
    student_data = []
    for student in students:
        student_data.append({
            "id": student.id,
            "name": f"{student.first_name} {student.last_name}",
            "age": student.age,
            "gender": student.gender,
            "absences": len([a for a in student.attendance_records if a.status == "absent"]),
            "risk_score": student.dropout_predictions[-1].risk_score if student.dropout_predictions else 0,
            "risk_level": student.dropout_predictions[-1].risk_level if student.dropout_predictions else "Low"
        })

    return student_data

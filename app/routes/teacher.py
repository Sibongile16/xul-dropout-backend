from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, func, case
from typing import List, Optional
from datetime import datetime, date, timedelta
from pytz import timezone
from uuid import UUID
from app.database import get_db
from app.utils.auth import get_current_user
from app.models.all_models import (
    User, Teacher, Student, Class, AttendanceRecord, DropoutPrediction,
    TeacherClass, AttendanceStatus, UserRole
)

router = APIRouter(prefix="/api/teachers", tags=["teachers"])

from pydantic import BaseModel

class StudentRiskResponse(BaseModel):
    id: UUID
    name: str
    age: int
    gender: str
    absences: int
    risk_score: float
    risk_level: str
    
    class Config:
        from_attributes = True

class StudentListResponse(BaseModel):
    students: List[StudentRiskResponse]
    total_count: int
    class_name: str
    academic_year: str

@router.get("/class/{class_id}", response_model=StudentListResponse)
async def get_students_by_class(
    class_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get list of students and their risk status for a specific class.
    Only accessible by teachers who are assigned to the class or admins.
    """
    
    if current_user.role not in [UserRole.TEACHER, UserRole.ADMIN, UserRole.HEADTEACHER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only teachers and administrators can access this endpoint."
        )
    
    class_info = db.query(Class).filter(Class.id == class_id).first()
    if not class_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Class not found"
        )
    
    if current_user.role == UserRole.TEACHER:
        teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Teacher profile not found"
            )
        
        teacher_class_assignment = db.query(TeacherClass).filter(
            and_(
                TeacherClass.teacher_id == teacher.id,
                TeacherClass.class_id == class_id,
                TeacherClass.academic_year == class_info.academic_year
            )
        ).first()
        
        if not teacher_class_assignment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You are not assigned to this class."
            )
    
    current_year = datetime.now(timezone("Africa/Blantyre")).year
    current_month = datetime.now(timezone("Africa/Blantyre")).month
    
    if current_month >= 1:
        academic_year_start = date(current_year, 1, 1)
        academic_year_end = date(current_year, 12, 31)
    else:
        academic_year_start = date(current_year - 1, 1, 1)
        academic_year_end = date(current_year - 1, 12, 31)
    
    students_query = db.query(
        Student.id,
        Student.first_name,
        Student.last_name,
        Student.age,
        Student.gender,
        func.coalesce(
            func.count(
                case(
                    (AttendanceRecord.status == AttendanceStatus.ABSENT, 1),
                    else_=None
                )
            ), 0
        ).label('absences')
    ).outerjoin(
        AttendanceRecord,
        and_(
            AttendanceRecord.student_id == Student.id,
            AttendanceRecord.date >= academic_year_start,
            AttendanceRecord.date <= academic_year_end
        )
    ).filter(
        Student.current_class_id == class_id,
        Student.is_active == True
    ).group_by(
        Student.id,
        Student.first_name,
        Student.last_name,
        Student.age,
        Student.gender
    )
    
    students_data = students_query.all()
    
    student_ids = [str(student.id) for student in students_data]
    
    latest_predictions_subquery = db.query(
        DropoutPrediction.student_id,
        func.max(DropoutPrediction.prediction_date).label('latest_date')
    ).filter(
        DropoutPrediction.student_id.in_(student_ids)
    ).group_by(DropoutPrediction.student_id).subquery()
    
    latest_predictions = db.query(DropoutPrediction).join(
        latest_predictions_subquery,
        and_(
            DropoutPrediction.student_id == latest_predictions_subquery.c.student_id,
            DropoutPrediction.prediction_date == latest_predictions_subquery.c.latest_date
        )
    ).all()
    
    predictions_dict = {
        pred.student_id: pred for pred in latest_predictions
    }
    
    students_response = []
    for student in students_data:
        student_id = student.id
        prediction = predictions_dict.get(student_id)
        
        risk_score = prediction.risk_score if prediction else 0.0
        risk_level = prediction.risk_level.value if prediction else "low"
        
        students_response.append(StudentRiskResponse(
            id=student_id,
            name=f"{student.first_name} {student.last_name}",
            age=student.age or 0,
            gender=student.gender.value.title(),
            absences=student.absences,
            risk_score=round(risk_score, 2),
            risk_level=risk_level.title()
        ))
    
    students_response.sort(key=lambda x: (-x.risk_score, x.name))
    
    return StudentListResponse(
        students=students_response,
        total_count=len(students_response),
        class_name=class_info.name,
        academic_year=class_info.academic_year
    )

@router.get("/class/{class_id}/summary")
async def get_class_summary(
    class_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get summary statistics for a class including risk level distribution.
    """
    
    if current_user.role not in [UserRole.TEACHER, UserRole.ADMIN, UserRole.HEADTEACHER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only teachers and administrators can access this endpoint."
        )
    
    class_info = db.query(Class).filter(Class.id == class_id).first()
    if not class_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Class not found"
        )
    
    if current_user.role == UserRole.TEACHER:
        teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
        if not teacher:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Teacher profile not found"
            )
        
        teacher_class_assignment = db.query(TeacherClass).filter(
            and_(
                TeacherClass.teacher_id == teacher.id,
                TeacherClass.class_id == class_id,
                TeacherClass.academic_year == class_info.academic_year
            )
        ).first()
        
        if not teacher_class_assignment:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You are not assigned to this class."
            )
    
    total_students = db.query(Student).filter(
        Student.current_class_id == class_id,
        Student.is_active == True
    ).count()
    
    student_ids = db.query(Student.id).filter(
        Student.current_class_id == class_id,
        Student.is_active == True
    ).subquery()
    
    latest_predictions_subquery = db.query(
        DropoutPrediction.student_id,
        func.max(DropoutPrediction.prediction_date).label('latest_date')
    ).join(student_ids, DropoutPrediction.student_id == student_ids.c.id).group_by(
        DropoutPrediction.student_id
    ).subquery()
    
    risk_distribution = db.query(
        DropoutPrediction.risk_level,
        func.count(DropoutPrediction.student_id).label('count')
    ).join(
        latest_predictions_subquery,
        and_(
            DropoutPrediction.student_id == latest_predictions_subquery.c.student_id,
            DropoutPrediction.prediction_date == latest_predictions_subquery.c.latest_date
        )
    ).group_by(DropoutPrediction.risk_level).all()
    
    students_with_predictions = sum(item.count for item in risk_distribution)
    students_without_predictions = total_students - students_with_predictions
    
    risk_counts = {
        "low": students_without_predictions,
        "medium": 0,
        "high": 0,
        "critical": 0
    }
    
    for risk_item in risk_distribution:
        risk_counts[risk_item.risk_level.value] = risk_item.count
    
    return {
        "class_name": class_info.name,
        "academic_year": class_info.academic_year,
        "total_students": total_students,
        "capacity": class_info.capacity,
        "risk_distribution": risk_counts,
        "high_risk_students": risk_counts["high"] + risk_counts["critical"]
    }
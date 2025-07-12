from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, func, case
from app.database import get_db
from app.models.all_models import (
    Student, Teacher, TeacherClass, User, Class, AcademicTerm, 
    DropoutPrediction, StudentStatus
)
from app.utils.auth import get_current_user
from typing import Dict, List, Optional

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

class StudentRiskResponse(BaseModel):
    id: UUID
    name: str
    age: int
    gender: str
    absences: int
    risk_score: float
    risk_level: str
    last_term_avg: Optional[float] = None

class RiskDistributionResponse(BaseModel):
    low: int
    medium: int
    high: int
    critical: int

class DashboardClassResponse(BaseModel):
    students: List[StudentRiskResponse]
    risk_distribution: RiskDistributionResponse

@router.get("/students/class/{class_id}", response_model=DashboardClassResponse)
async def get_students_by_class(
    class_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Get teacher record
    teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
    if not teacher:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Teacher not found"
        )

    # Verify teacher teaches this class
    teaches_class = db.query(TeacherClass).filter(
        TeacherClass.teacher_id == teacher.id,
        TeacherClass.class_id == class_id
    ).first()
    
    if not teaches_class:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not teach this class"
        )

    # Get latest predictions subquery
    latest_predictions_subq = db.query(
        DropoutPrediction.student_id,
        func.max(DropoutPrediction.prediction_date).label('latest_date')
    ).group_by(DropoutPrediction.student_id).subquery()

    # Get students with their latest prediction and term data
    students = db.query(
        Student,
        DropoutPrediction.risk_score,
        DropoutPrediction.risk_level,
        AcademicTerm.absent_days,
        AcademicTerm.term_avg_score
    ).join(
        latest_predictions_subq,
        and_(
            Student.id == latest_predictions_subq.c.student_id,
        )
    ).join(
        DropoutPrediction,
        and_(
            DropoutPrediction.student_id == latest_predictions_subq.c.student_id,
            DropoutPrediction.prediction_date == latest_predictions_subq.c.latest_date
        )
    ).outerjoin(
        AcademicTerm,
        and_(
            AcademicTerm.student_id == Student.id,
            AcademicTerm.academic_year == Class.academic_year
        )
    ).join(
        Class,
        Student.class_id == Class.id
    ).filter(
        Student.class_id == class_id,
        Student.status == StudentStatus.ACTIVE
    ).options(
        joinedload(Student.class_)
    ).all()

    # Calculate risk distribution
    risk_counts = db.query(
        DropoutPrediction.risk_level,
        func.count(DropoutPrediction.student_id).label('count')
    ).join(
        latest_predictions_subq,
        and_(
            DropoutPrediction.student_id == latest_predictions_subq.c.student_id,
            DropoutPrediction.prediction_date == latest_predictions_subq.c.latest_date
        )
    ).join(
        Student,
        Student.id == DropoutPrediction.student_id
    ).filter(
        Student.class_id == class_id,
        Student.status == StudentStatus.ACTIVE
    ).group_by(DropoutPrediction.risk_level).all()

    # Format risk distribution
    risk_distribution = {
        "low": 0,
        "medium": 0,
        "high": 0,
        "critical": 0
    }
    for risk in risk_counts:
        risk_distribution[risk.risk_level.value] = risk.count

    # Format student data
    student_data = []
    for student, risk_score, risk_level, absences, term_avg in students:
        student_data.append(StudentRiskResponse(
            id=student.id,
            name=f"{student.first_name} {student.last_name}",
            age=student.age,
            gender=student.gender.value,
            absences=absences if absences is not None else 0,
            risk_score=risk_score,
            risk_level=risk_level.value,
            last_term_avg=term_avg
        ))

    return DashboardClassResponse(
        students=student_data,
        risk_distribution=RiskDistributionResponse(**risk_distribution)
    )
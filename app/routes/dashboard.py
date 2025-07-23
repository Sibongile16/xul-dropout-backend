from datetime import date, datetime
import logging
from uuid import UUID
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, desc, func, case
from app.crud.prediction import fetch_student_data, save_prediction_to_db
from app.database import get_db
from app.models.all_models import (
    BullyingIncident, RiskLevel, Student, Teacher, TeacherClass, User, Class, AcademicTerm, 
    DropoutPrediction, StudentStatus
)
from app.schemas.ml_model import PredictionResponse
from app.services.ml_model import generate_recommendations, get_contributing_factors
from app.utils.auth import get_current_user
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

async def get_teacher_class_ids(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> List[UUID]:
    """Get all class IDs that the current teacher is assigned to"""
    if not current_user.teacher:
        raise HTTPException(status_code=403, detail="Only teachers can access this data")
    
    teacher_classes = db.query(TeacherClass.class_id).filter(
        TeacherClass.teacher_id == current_user.teacher.id
    ).all()
    
    return [tc.class_id for tc in teacher_classes]

async def teacher_students_only(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Query:
    class_ids = await get_teacher_class_ids(current_user, db)
    return db.query(Student).filter(Student.class_id.in_(class_ids))
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

class DashboardStats(BaseModel):
    total_students: int
    at_risk_students: int
    total_classes: int
    average_attendance: float

class StudentSummary(BaseModel):
    id: str
    student_id: str
    first_name: str
    last_name: str
    age: int
    gender: str
    class_name: Optional[str]
    risk_level: Optional[str]
    last_attendance: Optional[float]

class AtRiskStudent(BaseModel):
    id: str
    student_id: str
    first_name: str
    last_name: str
    class_name: Optional[str]
    risk_score: float
    risk_level: str
    contributing_factors: List[str]
    recommendations: List[str]
    last_prediction_date: date

class RiskDistribution(BaseModel):
    low: int
    medium: int
    high: int
    critical: int

class TeacherProfile(BaseModel):
    id: str
    first_name: str
    last_name: str
    email: str
    phone_number: Optional[str]
    qualification: Optional[str]
    experience_years: Optional[int]

@router.get("/students/class/{class_id}", response_model=DashboardClassResponse)
async def get_students_by_class(
    class_id: UUID,
    class_ids: List[UUID] = Depends(get_teacher_class_ids),
    db: Session = Depends(get_db)
):
    # Verify the requested class is one the teacher teaches
    if class_id not in class_ids:
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

@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    class_ids: List[UUID] = Depends(get_teacher_class_ids),
    db: Session = Depends(get_db)
):
    if not class_ids:
        return DashboardStats(
            total_students=0,
            at_risk_students=0,
            total_classes=0,
            average_attendance=0
        )

    # Total students in teacher's classes
    total_students = db.query(Student).filter(
        Student.class_id.in_(class_ids),
        Student.status == StudentStatus.ACTIVE
    ).count()
    
    # At-risk students
    at_risk_students = db.query(Student).join(
        DropoutPrediction, Student.id == DropoutPrediction.student_id
    ).filter(
        Student.class_id.in_(class_ids),
        Student.status == StudentStatus.ACTIVE,
        DropoutPrediction.risk_level.in_([RiskLevel.HIGH, RiskLevel.CRITICAL])
    ).distinct().count()
    
    # Total classes
    total_classes = len(class_ids)
    
    # Average attendance (last 30 days)
    recent_terms = db.query(AcademicTerm).join(
        Student, AcademicTerm.student_id == Student.id
    ).filter(
        Student.class_id.in_(class_ids),
        AcademicTerm.created_at >= datetime.now().replace(day=1)  # This month
    ).all()
    
    if recent_terms:
        total_present = sum(term.present_days or 0 for term in recent_terms)
        total_days = sum((term.present_days or 0) + (term.absent_days or 0) for term in recent_terms)
        average_attendance = (total_present / total_days * 100) if total_days > 0 else 0
    else:
        average_attendance = 0
    
    return DashboardStats(
        total_students=total_students,
        at_risk_students=at_risk_students,
        total_classes=total_classes,
        average_attendance=round(average_attendance, 1)
    )

@router.get("/risk-distribution", response_model=RiskDistribution)
async def get_risk_distribution(
    class_ids: List[UUID] = Depends(get_teacher_class_ids),
    db: Session = Depends(get_db)
):
    if not class_ids:
        return RiskDistribution(low=0, medium=0, high=0, critical=0)

    # Get latest predictions for each student
    subquery = db.query(
        DropoutPrediction.student_id,
        func.max(DropoutPrediction.prediction_date).label('max_date')
    ).group_by(DropoutPrediction.student_id).subquery()
    
    risk_counts = db.query(
        DropoutPrediction.risk_level,
        func.count(DropoutPrediction.student_id).label('count')
    ).join(
        Student, DropoutPrediction.student_id == Student.id
    ).join(
        subquery, and_(
            DropoutPrediction.student_id == subquery.c.student_id,
            DropoutPrediction.prediction_date == subquery.c.max_date
        )
    ).filter(
        Student.class_id.in_(class_ids),
        Student.status == StudentStatus.ACTIVE
    ).group_by(DropoutPrediction.risk_level).all()
    
    risk_dict = {level.value: 0 for level in RiskLevel}
    for risk_level, count in risk_counts:
        risk_dict[risk_level.value] = count
    
    return RiskDistribution(
        low=risk_dict['low'],
        medium=risk_dict['medium'],
        high=risk_dict['high'],
        critical=risk_dict['critical']
    )

@router.get("/students/recent", response_model=List[StudentSummary])
async def get_recent_students(
    limit: int = 10,
    class_ids: List[UUID] = Depends(get_teacher_class_ids),
    db: Session = Depends(get_db)
):
    if not class_ids:
        return []

    students = db.query(Student).options(
        joinedload(Student.class_),
        joinedload(Student.dropout_predictions)
    ).filter(
        Student.class_id.in_(class_ids),
        Student.status == StudentStatus.ACTIVE
    ).order_by(desc(Student.created_at)).limit(limit).all()
    
    result = []
    for student in students:
        latest_prediction = None
        if student.dropout_predictions:
            latest_prediction = max(student.dropout_predictions, key=lambda x: x.prediction_date)
        
        latest_term = db.query(AcademicTerm).filter(
            AcademicTerm.student_id == student.id
        ).order_by(desc(AcademicTerm.created_at)).first()
        
        attendance = None
        if latest_term and latest_term.present_days and latest_term.absent_days:
            total_days = latest_term.present_days + latest_term.absent_days
            attendance = (latest_term.present_days / total_days * 100) if total_days > 0 else None
        
        result.append(StudentSummary(
            id=str(student.id),
            student_id=student.student_id,
            first_name=student.first_name,
            last_name=student.last_name,
            age=student.age or 0,
            gender=student.gender.value,
            class_name=student.class_.name if student.class_ else None,
            risk_level=latest_prediction.risk_level.value if latest_prediction else None,
            last_attendance=round(attendance, 1) if attendance else None
        ))
    
    return result

@router.get("/students/at-risk", response_model=List[AtRiskStudent])
async def get_at_risk_students(
    class_ids: List[UUID] = Depends(get_teacher_class_ids),
    db: Session = Depends(get_db)
):
    if not class_ids:
        return []

    subquery = db.query(
        DropoutPrediction.student_id,
        func.max(DropoutPrediction.prediction_date).label('max_date')
    ).group_by(DropoutPrediction.student_id).subquery()
    
    at_risk_data = db.query(
        Student, DropoutPrediction, Class
    ).join(
        DropoutPrediction, Student.id == DropoutPrediction.student_id
    ).join(
        Class, Student.class_id == Class.id
    ).join(
        subquery, and_(
            DropoutPrediction.student_id == subquery.c.student_id,
            DropoutPrediction.prediction_date == subquery.c.max_date
        )
    ).filter(
        Class.id.in_(class_ids),
        Student.status == StudentStatus.ACTIVE,
        DropoutPrediction.risk_level.in_([RiskLevel.HIGH, RiskLevel.CRITICAL])
    ).order_by(desc(DropoutPrediction.risk_score)).all()
    
    result = []
    for student, prediction, class_ in at_risk_data:
        factors = prediction.contributing_factors or []
        if isinstance(factors, dict):
            factors = list(factors.keys()) if factors else []
        
        recommendations = []
        if prediction.intervention_recommended:
            recommendations = prediction.intervention_recommended.split('; ')
        
        result.append(AtRiskStudent(
            id=str(student.id),
            student_id=student.student_id,
            first_name=student.first_name,
            last_name=student.last_name,
            class_name=class_.name,
            risk_score=prediction.risk_score,
            risk_level=prediction.risk_level.value,
            contributing_factors=factors,
            recommendations=recommendations,
            last_prediction_date=prediction.prediction_date
        ))
    
    return result

@router.get("/teacher/profile", response_model=TeacherProfile)
async def get_teacher_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    teacher_with_user = db.query(Teacher).options(
        joinedload(Teacher.user)
    ).filter(Teacher.id == current_user.teacher.id).first()
    
    return TeacherProfile(
        id=str(teacher_with_user.id),
        first_name=teacher_with_user.first_name,
        last_name=teacher_with_user.last_name,
        email=teacher_with_user.user.email,
        phone_number=teacher_with_user.phone_number,
        qualification=teacher_with_user.qualification,
        experience_years=teacher_with_user.experience_years
    )

@router.post("/students/{student_id}/predict-risk")
async def predict_student_risk(
    student_id: str,
    class_ids: List[UUID] = Depends(get_teacher_class_ids),
    db: Session = Depends(get_db)
):
    try:
        # Verify student is in teacher's classes
        student = db.query(Student).filter(
            Student.id == student_id,
            Student.class_id.in_(class_ids)
        ).first()
        
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student not found in your classes"
            )
        
        student_data = await fetch_student_data(student_id, db)
        if not student_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student data not found"
            )
        
        mock_probability = 0.65
        
        if mock_probability >= 0.8:
            risk_level = RiskLevel.CRITICAL
        elif mock_probability >= 0.6:
            risk_level = RiskLevel.HIGH
        elif mock_probability >= 0.4:
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.LOW
        
        contributing_factors = get_contributing_factors(student_data, mock_probability)
        recommendations = generate_recommendations(risk_level, contributing_factors)
        
        prediction = PredictionResponse(
            student_id=student_id,
            dropout_risk_probability=mock_probability,
            risk_level=risk_level,
            contributing_factors=contributing_factors,
            recommendations=recommendations,
            prediction_date=date.today()
        )
        
        await save_prediction_to_db(prediction, db)
        
        return {
            "student_id": student_id,
            "risk_probability": mock_probability,
            "risk_level": risk_level.value,
            "contributing_factors": contributing_factors,
            "recommendations": recommendations,
            "prediction_date": date.today()
        }
        
    except Exception as e:
        logger.error(f"Error predicting risk for student {student_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error generating prediction: {str(e)}"
        )

@router.get("/students/{student_id}/detailed-data")
async def get_student_detailed_data(
    student_id: UUID,
    class_ids: List[UUID] = Depends(get_teacher_class_ids),
    db: Session = Depends(get_db)
):
    try:
        student = db.query(Student).filter(
            Student.id == student_id,
            Student.class_id.in_(class_ids)
        ).first()
        
        if not student:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student not found in your classes"
            )
        
        student_data = await fetch_student_data(student_id, db)
        if not student_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Student data not found"
            )
        
        latest_prediction = db.query(DropoutPrediction).filter(
            DropoutPrediction.student_id == student_id
        ).order_by(desc(DropoutPrediction.prediction_date)).first()
        
        prediction_info = None
        if latest_prediction:
            factors = latest_prediction.contributing_factors or []
            if isinstance(factors, dict):
                factors = list(factors.keys()) if factors else []
            
            recommendations = []
            if latest_prediction.intervention_recommended:
                recommendations = latest_prediction.intervention_recommended.split('; ')
            
            prediction_info = {
                "risk_score": latest_prediction.risk_score,
                "risk_level": latest_prediction.risk_level.value,
                "contributing_factors": factors,
                "recommendations": recommendations,
                "prediction_date": latest_prediction.prediction_date
            }
        
        return {
            "student_data": student_data,
            "latest_prediction": prediction_info
        }
        
    except Exception as e:
        logger.error(f"Error fetching detailed data for student {student_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error fetching student data: {str(e)}"
        )

@router.post("/students/batch-predict")
async def batch_predict_students(
    background_tasks: BackgroundTasks,
    class_ids: List[UUID] = Depends(get_teacher_class_ids),
    db: Session = Depends(get_db)
):
    try:
        if not class_ids:
            return {
                "message": "No students to predict",
                "student_count": 0
            }
        
        students = db.query(Student).filter(
            Student.class_id.in_(class_ids),
            Student.status == StudentStatus.ACTIVE
        ).all()
        
        background_tasks.add_task(
            process_batch_predictions,
            [str(student.id) for student in students],
            db
        )
        
        return {
            "message": f"Batch prediction started for {len(students)} students",
            "student_count": len(students)
        }
        
    except Exception as e:
        logger.error(f"Error starting batch prediction: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error starting batch prediction: {str(e)}"
        )

@router.get("/students/{student_id}/bullying-incidents")
async def get_student_bullying_incidents(
    student_id: UUID,
    class_ids: List[UUID] = Depends(get_teacher_class_ids),
    db: Session = Depends(get_db)
):
    # Verify student is in teacher's classes
    student = db.query(Student).filter(
        Student.id == student_id,
        Student.class_id.in_(class_ids)
    ).first()
    
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found in your classes"
        )
    
    incidents = db.query(BullyingIncident).filter(
        BullyingIncident.student_id == student_id
    ).order_by(desc(BullyingIncident.incident_date)).all()
    
    return [{
        "id": str(incident.id),
        "incident_date": incident.incident_date,
        "incident_type": incident.incident_type.value,
        "description": incident.description,
        "location": incident.location,
        "severity_level": incident.severity_level.value,
        "is_addressed": incident.is_addressed,
        "action_taken": incident.action_taken
    } for incident in incidents]

async def process_batch_predictions(student_ids: List[str], db: Session):
    """Background task to process batch predictions"""
    logger.info(f"Starting batch prediction for {len(student_ids)} students")
    
    for student_id in student_ids:
        try:
            student_data = await fetch_student_data(student_id, db)
            if not student_data:
                logger.warning(f"No data found for student {student_id}")
                continue
            
            mock_probability = 0.5
            
            if mock_probability >= 0.8:
                risk_level = RiskLevel.CRITICAL
            elif mock_probability >= 0.6:
                risk_level = RiskLevel.HIGH
            elif mock_probability >= 0.4:
                risk_level = RiskLevel.MEDIUM
            else:
                risk_level = RiskLevel.LOW
            
            contributing_factors = get_contributing_factors(student_data, mock_probability)
            recommendations = generate_recommendations(risk_level, contributing_factors)
            
            prediction = PredictionResponse(
                student_id=student_id,
                dropout_risk_probability=mock_probability,
                risk_level=risk_level,
                contributing_factors=contributing_factors,
                recommendations=recommendations,
                prediction_date=date.today()
            )
            
            await save_prediction_to_db(prediction, db)
            logger.info(f"Prediction saved for student {student_id}")
            
        except Exception as e:
            logger.error(f"Error processing prediction for student {student_id}: {e}")
            continue
    
    logger.info("Batch prediction completed")
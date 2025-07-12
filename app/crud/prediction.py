from datetime import datetime
import logging
from fastapi import HTTPException
from sqlalchemy import func, and_, or_, case, text, Integer
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from app.models.all_models import (
    Student, Guardian, Class, AttendanceRecord,
    AcademicPerformance, BullyingIncident, StudentClassHistory,
    DropoutPrediction
)
from app.schemas.ml_model import PredictionResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def fetch_student_data(student_id: str, db: Session) -> Optional[Dict[str, Any]]:
    """Fetch student data from database for prediction using SQLAlchemy ORM"""
    try:
        # Calculate attendance rate subquery
        attendance_subq = (
            db.query(
                AttendanceRecord.student_id,
                func.count().filter(AttendanceRecord.status == 'present').label('present_count'),
                func.count().label('total_count')
            )
            .filter(
                AttendanceRecord.student_id == student_id,
                AttendanceRecord.date >= func.current_date() - text("INTERVAL '30 days'")
            )
            .group_by(AttendanceRecord.student_id)
            .subquery()
        )

        # Calculate average score subquery
        avg_score_subq = (
            db.query(
                AcademicPerformance.student_id,
                func.avg(AcademicPerformance.marks_obtained * AcademicPerformance.total_marks / 100).label('avg_score')
            )
            .filter(
                AcademicPerformance.student_id == student_id,
                AcademicPerformance.academic_year == (
                    db.query(func.max(AcademicPerformance.academic_year))
                        .filter(AcademicPerformance.student_id == student_id)
                        .scalar_subquery()
                )
            )
            .group_by(AcademicPerformance.student_id)
            .subquery()
        )

        # Count bullying incidents subquery
        bullying_subq = (
            db.query(
                BullyingIncident.victim_student_id,
                func.count().label('incident_count')
            )
            .filter(BullyingIncident.victim_student_id == student_id)
            .group_by(BullyingIncident.victim_student_id)
            .subquery()
        )

        # Count class repetitions subquery
        repetition_subq = (
            db.query(
                StudentClassHistory.student_id,
                func.count().label('repetition_count')
            )
            .filter(
                StudentClassHistory.student_id == student_id,
                StudentClassHistory.status == 'repeated'
            )
            .group_by(StudentClassHistory.student_id)
            .subquery()
        )

        # Main query
        student = db.query(
            Student.id.label('student_id'),
            Student.age,
            Student.gender,
            Student.distance_to_school_km.label('distance_to_school'),
            Student.special_needs,
            Guardian.monthly_income_range.label('household_income'),
            Guardian.relationship_to_student.label('orphan_status'),
            Class.name.label('current_class'),
            func.coalesce(
                attendance_subq.c.present_count / 
                func.nullif(attendance_subq.c.total_count, 0),
                0.8
            ).label('school_attendance_rate'),
            func.coalesce(avg_score_subq.c.avg_score, 300).label('term_avg_score'),
            func.coalesce(bullying_subq.c.incident_count, 0).label('bullying_incidents_total'),
            func.coalesce(repetition_subq.c.repetition_count, 0).label('class_repetitions'),
            func.coalesce(
                func.cast(
                    func.regexp_replace(Class.name, '[^0-9]', '', 'g'),
                    Integer
                ),
                5
            ).label('standard')
        )\
        .join(Guardian, Student.guardian_id == Guardian.id)\
        .join(Class, Student.current_class_id == Class.id)\
        .outerjoin(attendance_subq, Student.id == attendance_subq.c.student_id)\
        .outerjoin(avg_score_subq, Student.id == avg_score_subq.c.student_id)\
        .outerjoin(bullying_subq, Student.id == bullying_subq.c.victim_student_id)\
        .outerjoin(repetition_subq, Student.id == repetition_subq.c.student_id)\
        .filter(Student.id == student_id)\
        .first()

        if student:
            return {
                'student_id': str(student.student_id),
                'age': student.age,
                'gender': student.gender,
                'distance_to_school': student.distance_to_school or 5.0,
                'special_learning': bool(student.special_needs),
                'household_income': student.household_income or 'medium',
                'orphan_status': 'yes' if student.orphan_status in ['guardian', 'relative'] else 'no',
                'school_attendance_rate': float(student.school_attendance_rate),
                'term_avg_score': float(student.term_avg_score),
                'bullying_incidents_total': int(student.bullying_incidents_total),
                'class_repetitions': int(student.class_repetitions),
                'standard': int(student.standard)
            }
        return None
        
    except Exception as e:
        logger.error(f"Error fetching student data: {e}")
        return None

async def save_prediction_to_db(prediction: PredictionResponse, db: Session):
    """Save prediction to database using SQLAlchemy ORM"""
    try:
        new_prediction = DropoutPrediction(
            student_id=prediction.student_id,
            risk_score=prediction.dropout_risk_probability * 100,
            risk_level=prediction.risk_level.value,
            contributing_factors=prediction.contributing_factors,
            prediction_date=prediction.prediction_date,
            algorithm_version='xgboost_v1.0',
            intervention_recommended='; '.join(prediction.recommendations),
            created_at=datetime.now()
        )
        
        db.add(new_prediction)
        db.commit()
        logger.info(f"Prediction saved for student {prediction.student_id}")
        
    except Exception as e:
        logger.error(f"Error saving prediction: {e}")
        db.rollback()
        raise

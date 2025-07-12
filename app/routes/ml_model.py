from datetime import date, datetime
import logging
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
import psutil
from sqlalchemy import and_, case, func
from sqlalchemy.orm import Session
from app.crud.prediction import fetch_student_data, save_prediction_to_db
from app.database import get_db
from app.models.all_models import DropoutPrediction, Student
from app.schemas.ml_model import BatchPredictionRequest, BatchPredictionResponse, HealthCheckResponse, PredictionRequest, PredictionResponse, RiskDistributionResponse, StudentPredictionHistoryResponse
from app.services.ml_model import generate_recommendations, get_contributing_factors
from app.utils.ml_model import determine_risk_level, load_model_artifacts, preprocess_features
from app.utils.system_utils import determine_system_status

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/predictions", tags=["Predictions"])

model, scaler, feature_columns, label_encoders = load_model_artifacts()
@router.get("/")
async def root():
    return {"message": "Student Dropout Risk Prediction API", "version": "1.0.0"}

@router.get("/health", response_model=HealthCheckResponse)
async def health_check():
    cpu = psutil.cpu_percent(interval=0.5)
    memory = psutil.virtual_memory().percent
    system_status = determine_system_status(cpu, memory)

    return {
        "status": "healthy",
        "model_loaded": model is not None,
        "timestamp": datetime.now(),
        "system": {
            "cpu_usage": cpu,
            "memory_usage": memory,
            "status": system_status
        }
    }

@router.post("/predict", response_model=PredictionResponse)
async def predict_dropout_risk(
    request: PredictionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Predict dropout risk for a single student"""
    student = db.query(Student).filter(Student.id == request.student_id).first()
    if not student:
        raise HTTPException(
            status_code=404,
            detail=f"Student with ID {request.student_id} does not exist."
        )
    try:
        # Prepare features
        features_dict = request.model_dump()
        features = preprocess_features(features_dict)
        
        # Make prediction
        probability = model.predict_proba(features)[0][1]
        binary_prediction = int(probability >= 0.5)
        
        # Determine risk level
        risk_level = determine_risk_level(probability)
        
        # Get contributing factors
        contributing_factors = get_contributing_factors(features_dict, probability)
        
        # Generate recommendations
        recommendations = generate_recommendations(risk_level, contributing_factors)
        
        # Create response
        prediction_response = PredictionResponse(
            student_id=request.student_id,
            dropout_risk_probability=float(probability),
            dropout_risk_binary=binary_prediction,
            risk_level=risk_level,
            contributing_factors=contributing_factors,
            prediction_date=date.today(),
            confidence_score=max(probability, 1-probability),
            recommendations=recommendations
        )
        
        # Save to database in background
        background_tasks.add_task(save_prediction_to_db, prediction_response, db)
        
        return prediction_response
        
    except Exception as e:
        logger.error(f"Error in prediction: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/predict/batch", response_model=BatchPredictionResponse)
async def predict_batch_dropout_risk(
    request: BatchPredictionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Predict dropout risk for multiple students"""
    try:
        predictions = []
        
        for student_id in request.student_ids:
            # Fetch student data from database
            student_data = await fetch_student_data(student_id, db)
            
            if student_data:
                # Make prediction
                features = preprocess_features(student_data)
                probability = model.predict_proba(features)[0][1]
                
                # Create prediction response
                prediction = PredictionResponse(
                    student_id=student_id,
                    dropout_risk_probability=float(probability),
                    dropout_risk_binary=int(probability >= 0.5),
                    risk_level=determine_risk_level(probability),
                    contributing_factors=get_contributing_factors(student_data, probability),
                    prediction_date=date.today(),
                    confidence_score=max(probability, 1-probability),
                    recommendations=generate_recommendations(
                        determine_risk_level(probability),
                        get_contributing_factors(student_data, probability)
                    ) if request.include_recommendations else []
                )
                
                predictions.append(prediction)
                
                # Save to database in background
                background_tasks.add_task(save_prediction_to_db, prediction, db)
        
        return {"predictions": predictions, "total_processed": len(predictions)}
        
    except Exception as e:
        logger.error(f"Error in batch prediction: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/predictions/{student_id}", response_model=StudentPredictionHistoryResponse)
async def get_student_predictions(
    student_id: str,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    """Get historical predictions for a student using SQLAlchemy ORM"""
    try:
        predictions = db.query(
            DropoutPrediction.risk_score,
            DropoutPrediction.risk_level,
            DropoutPrediction.contributing_factors,
            DropoutPrediction.prediction_date,
            DropoutPrediction.intervention_recommended,
            DropoutPrediction.created_at
        )\
        .filter(DropoutPrediction.student_id == student_id)\
        .order_by(DropoutPrediction.created_at.desc())\
        .limit(limit)\
        .all()
        
        return {
            "student_id": student_id,
            "predictions": [
                {
                    "risk_score": pred.risk_score,
                    "risk_level": pred.risk_level,
                    "contributing_factors": pred.contributing_factors,
                    "prediction_date": pred.prediction_date,
                    "recommendations": pred.intervention_recommended,
                    "created_at": pred.created_at
                }
                for pred in predictions
            ]
        }
        
    except Exception as e:
        logger.error(f"Error fetching predictions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats/risk-distribution", response_model=RiskDistributionResponse)
async def get_risk_distribution(db: Session = Depends(get_db)):
    """Get distribution of risk levels across all students using SQLAlchemy ORM"""
    try:
        # Subquery to get latest prediction for each student
        latest_prediction_subq = (
            db.query(
                DropoutPrediction.student_id,
                func.max(DropoutPrediction.created_at).label('latest_prediction')
            )
            .group_by(DropoutPrediction.student_id)
            .subquery()
        )
        
        # Main query to count risk levels
        risk_counts = db.query(
            DropoutPrediction.risk_level,
            func.count().label('count')
        )\
        .join(
            latest_prediction_subq,
            and_(
                DropoutPrediction.student_id == latest_prediction_subq.c.student_id,
                DropoutPrediction.created_at == latest_prediction_subq.c.latest_prediction
            )
        )\
        .group_by(DropoutPrediction.risk_level)\
        .order_by(
            case(
                (DropoutPrediction.risk_level == 'low', 1),
                (DropoutPrediction.risk_level == 'medium', 2),
                (DropoutPrediction.risk_level == 'high', 3),
                (DropoutPrediction.risk_level == 'critical', 4),
                else_=5
            )
        )\
        .all()
        
        return {
            "risk_distribution": [
                {"risk_level": result.risk_level, "count": result.count}
                for result in risk_counts
            ]
        }
        
    except Exception as e:
        logger.error(f"Error fetching risk distribution: {e}")
        raise HTTPException(status_code=500, detail=str(e))

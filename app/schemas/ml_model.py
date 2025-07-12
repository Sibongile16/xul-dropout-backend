# Global variables for model artifacts
from datetime import date, datetime
from enum import Enum
from typing import List
from uuid import UUID

from pydantic import BaseModel, Field


model = None
scaler = None
feature_columns = None
label_encoders = None

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class PredictionRequest(BaseModel):
    student_id: UUID
    term_avg_score: float = Field(..., ge=0, le=600, description="Average score across all subjects")
    school_attendance_rate: float = Field(..., ge=0, le=1, description="Attendance rate (0-1)")
    bullying_incidents_total: int = Field(..., ge=0, description="Total bullying incidents")
    class_repetitions: int = Field(..., ge=0, description="Number of class repetitions")
    distance_to_school: float = Field(..., ge=0, description="Distance to school in km")
    special_learning: bool = Field(..., description="Has special learning needs")
    household_income: str = Field(..., description="Income level: low, medium, high")
    orphan_status: str = Field(..., description="Orphan status: yes, no, partial")
    standard: int = Field(..., ge=1, le=8, description="Current standard/grade")
    age: float = Field(..., ge=5, le=18, description="Student age")
    gender: str = Field(..., description="Gender: male, female")

class PredictionResponse(BaseModel):
    student_id: UUID
    dropout_risk_probability: float
    dropout_risk_binary: int
    risk_level: RiskLevel
    contributing_factors: List[str]
    prediction_date: date
    confidence_score: float
    recommendations: List[str]

class BatchPredictionRequest(BaseModel):
    student_ids: List[UUID]
    include_recommendations: bool = True
    
class RiskDistributionItem(BaseModel):
    risk_level: str
    count: int

class RiskDistributionResponse(BaseModel):
    risk_distribution: List[RiskDistributionItem]
    

class StudentPredictionItem(BaseModel):
    risk_score: float
    risk_level: str
    contributing_factors: List[str]
    prediction_date: date
    recommendations: List[str]
    created_at: datetime

class StudentPredictionHistoryResponse(BaseModel):
    student_id: str
    predictions: List[StudentPredictionItem]
    
    
class BatchPredictionResponse(BaseModel):
    predictions: List[PredictionResponse]
    total_processed: int
    

class SystemHealth(BaseModel):
    cpu_usage: float
    memory_usage: float
    status: str

class HealthCheckResponse(BaseModel):
    status: str
    model_loaded: bool
    timestamp: datetime
    system: SystemHealth
from sqlalchemy import Column, String, Integer, Float, Date, DateTime, Boolean, Text, ForeignKey, Enum as SQLEnum, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, date
from enum import Enum
import uuid
from pytz import timezone

Base = declarative_base()

# Enum Classes
class UserRole(str, Enum):
    ADMIN = "admin"
    HEADTEACHER = "headteacher"
    TEACHER = "teacher"

class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"

class RelationshipType(str, Enum):
    PARENT = "parent"
    GUARDIAN = "guardian"
    RELATIVE = "relative"
    OTHER = "other"

class IncomeRange(str, Enum):
    BELOW_50K = "below_50k"
    RANGE_50K_100K = "50k_100k"
    RANGE_100K_200K = "100k_200k"
    ABOVE_200K = "above_200k"

class EducationLevel(str, Enum):
    NONE = "none"
    PRIMARY = "primary"
    SECONDARY = "secondary"
    TERTIARY = "tertiary"

class TransportMethod(str, Enum):
    WALKING = "walking"
    BICYCLE = "bicycle"
    PUBLIC_TRANSPORT = "public_transport"
    PRIVATE_TRANSPORT = "private_transport"

class StudentStatus(str, Enum):
    COMPLETED = "completed"
    REPEATED = "repeated"
    TRANSFERRED = "transferred"
    DROPPED_OUT = "dropped_out"

class AttendanceStatus(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"
    EXCUSED = "excused"

class AssessmentType(str, Enum):
    TEST = "test"
    EXAM = "exam"
    ASSIGNMENT = "assignment"

class Term(str, Enum):
    TERM1 = "term1"
    TERM2 = "term2"
    TERM3 = "term3"

class BullyingType(str, Enum):
    PHYSICAL = "physical"
    VERBAL = "verbal"
    CYBER = "cyber"
    SOCIAL_EXCLUSION = "social_exclusion"
    OTHER = "other"

class Location(str, Enum):
    CLASSROOM = "classroom"
    PLAYGROUND = "playground"
    TOILET = "toilet"
    CORRIDOR = "corridor"
    OUTSIDE_SCHOOL = "outside_school"
    OTHER = "other"

class SeverityLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class IncidentStatus(str, Enum):
    REPORTED = "reported"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    NOT_REPORTED = "not_reported"

class RiskFactorType(str, Enum):
    ECONOMIC = "economic"
    FAMILY = "family"
    ACADEMIC = "academic"
    SOCIAL = "social"
    HEALTH = "health"
    BEHAVIORAL = "behavioral"

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

# Model Classes
class User(Base):
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now(timezone("Africa/Blantyre")))
    updated_at = Column(DateTime, default=datetime.now(timezone("Africa/Blantyre")), onupdate=datetime.now(timezone("Africa/Blantyre")))
    
    # Relationship
    # In User model
    teacher = relationship(
        "Teacher", 
        back_populates="user", 
        uselist=False, 
        cascade="all, delete-orphan"
)


class Teacher(Base):
    __tablename__ = "teachers"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    phone_number = Column(String(20))
    date_of_birth = Column(Date)
    gender = Column(SQLEnum(Gender))
    address = Column(Text)
    hire_date = Column(Date)
    qualification = Column(String(100))
    experience_years = Column(Integer)
    created_at = Column(DateTime, default=datetime.now(timezone("Africa/Blantyre")))
    updated_at = Column(DateTime, default=datetime.now(timezone("Africa/Blantyre")), onupdate=datetime.now(timezone("Africa/Blantyre")))
    
    # Relationships
    user = relationship("User", back_populates="teacher")
    teacher_subjects = relationship("TeacherSubject", back_populates="teacher")
    teacher_classes = relationship("TeacherClass", back_populates="teacher")
    attendance_records = relationship("AttendanceRecord", back_populates="teacher")
    academic_performances = relationship("AcademicPerformance", back_populates="teacher")
    bullying_incidents = relationship("BullyingIncident", back_populates="teacher")
    risk_factors = relationship("StudentRiskFactor", back_populates="teacher")

class Subject(Base):
    __tablename__ = "subjects"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    code = Column(String(10), nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    teacher_subjects = relationship("TeacherSubject", back_populates="subject")
    academic_performances = relationship("AcademicPerformance", back_populates="subject")

class Class(Base):
    __tablename__ = "classes"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), nullable=False)
    code = Column(String(10), nullable=False)
    academic_year = Column(String(9), nullable=False)
    capacity = Column(Integer)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    teacher_classes = relationship("TeacherClass", back_populates="class_")
    students = relationship("Student", back_populates="current_class")
    student_class_histories = relationship("StudentClassHistory", back_populates="class_")

class TeacherSubject(Base):
    __tablename__ = "teacher_subjects"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=False)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=False)
    academic_year = Column(String(9), nullable=False)
    created_at = Column(DateTime, default=datetime.now(timezone("Africa/Blantyre")))
    
    # Relationships
    teacher = relationship("Teacher", back_populates="teacher_subjects")
    subject = relationship("Subject", back_populates="teacher_subjects")

class TeacherClass(Base):
    __tablename__ = "teacher_classes"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=False)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)
    is_class_teacher = Column(Boolean, default=False)
    academic_year = Column(String(9), nullable=False)
    created_at = Column(DateTime, default=datetime.now(timezone("Africa/Blantyre")))
    
    # Relationships
    teacher = relationship("Teacher", back_populates="teacher_classes")
    class_ = relationship("Class", back_populates="teacher_classes")

class Guardian(Base):
    __tablename__ = "guardians"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    relationship_to_student = Column(SQLEnum(RelationshipType), nullable=False)
    phone_number = Column(String(20))
    email = Column(String(100))
    address = Column(Text)
    occupation = Column(String(100))
    monthly_income_range = Column(SQLEnum(IncomeRange))
    education_level = Column(SQLEnum(EducationLevel))
    created_at = Column(DateTime, default=datetime.now(timezone("Africa/Blantyre")))
    updated_at = Column(DateTime, default=datetime.now(timezone("Africa/Blantyre")), onupdate=datetime.now(timezone("Africa/Blantyre")))
    
    # Relationships
    students = relationship("Student", back_populates="guardian")

class Student(Base):
    __tablename__ = "students"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_number = Column(String(20), unique=True, nullable=False)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    date_of_birth = Column(Date, nullable=False)
    age = Column(Integer)  # Can be calculated
    gender = Column(SQLEnum(Gender), nullable=False)
    current_class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"))
    guardian_id = Column(UUID(as_uuid=True), ForeignKey("guardians.id"), nullable=False)
    home_address = Column(Text)
    distance_to_school_km = Column(Float)
    transport_method = Column(SQLEnum(TransportMethod))
    enrollment_date = Column(Date, nullable=False)
    is_active = Column(Boolean, default=True)
    special_needs = Column(Text)
    medical_conditions = Column(Text)
    created_at = Column(DateTime, default=datetime.now(timezone("Africa/Blantyre")))
    updated_at = Column(DateTime, default=datetime.now(timezone("Africa/Blantyre")), onupdate=datetime.now(timezone("Africa/Blantyre")))
    
    # Relationships
    current_class = relationship("Class", back_populates="students")
    guardian = relationship("Guardian", back_populates="students")
    class_histories = relationship("StudentClassHistory", back_populates="student")
    attendance_records = relationship("AttendanceRecord", back_populates="student")
    academic_performances = relationship("AcademicPerformance", back_populates="student")
    bullying_incidents_as_victim = relationship("BullyingIncident", back_populates="victim_student", foreign_keys="BullyingIncident.victim_student_id")
    bullying_incidents_as_perpetrator = relationship("BullyingIncident", back_populates="perpetrator_student", foreign_keys="BullyingIncident.perpetrator_student_id")
    risk_factors = relationship("StudentRiskFactor", back_populates="student")
    dropout_predictions = relationship("DropoutPrediction", back_populates="student")

class StudentClassHistory(Base):
    __tablename__ = "student_class_history"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)
    academic_year = Column(String(9), nullable=False)
    enrollment_date = Column(Date, nullable=False)
    completion_date = Column(Date)  # NULL if ongoing
    status = Column(SQLEnum(StudentStatus), nullable=False)
    reason_for_status_change = Column(Text)
    created_at = Column(DateTime, default=datetime.now(timezone("Africa/Blantyre")))
    
    # Relationships
    student = relationship("Student", back_populates="class_histories")
    class_ = relationship("Class", back_populates="student_class_histories")

class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    date = Column(Date, nullable=False)
    status = Column(SQLEnum(AttendanceStatus), nullable=False)
    reason_for_absence = Column(Text)
    recorded_by_teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.now(timezone("Africa/Blantyre")))
    
    # Relationships
    student = relationship("Student", back_populates="attendance_records")
    teacher = relationship("Teacher", back_populates="attendance_records")

class AcademicPerformance(Base):
    __tablename__ = "academic_performance"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=False)
    assessment_type = Column(SQLEnum(AssessmentType), nullable=False)
    assessment_name = Column(String(100), nullable=False)
    marks_obtained = Column(Float, nullable=False)
    total_marks = Column(Float, nullable=False)
    percentage = Column(Float)  # Can be calculated
    grade = Column(String(2))
    assessment_date = Column(Date, nullable=False)
    academic_year = Column(String(9), nullable=False)
    term = Column(SQLEnum(Term), nullable=False)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.now(timezone("Africa/Blantyre")))
    
    # Relationships
    student = relationship("Student", back_populates="academic_performances")
    subject = relationship("Subject", back_populates="academic_performances")
    teacher = relationship("Teacher", back_populates="academic_performances")

class BullyingIncident(Base):
    __tablename__ = "bullying_incidents"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    victim_student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    perpetrator_student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"))
    incident_date = Column(Date, nullable=False)
    incident_type = Column(SQLEnum(BullyingType), nullable=False)
    description = Column(Text, nullable=False)
    location = Column(SQLEnum(Location), nullable=False)
    severity_level = Column(SQLEnum(SeverityLevel), nullable=False)
    reported_by_teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=False)
    action_taken = Column(Text)
    follow_up_required = Column(Boolean, default=False)
    follow_up_date = Column(Date)
    status = Column(SQLEnum(IncidentStatus), default=IncidentStatus.REPORTED)
    created_at = Column(DateTime, default=datetime.now(timezone("Africa/Blantyre")))
    updated_at = Column(DateTime, default=datetime.now(timezone("Africa/Blantyre")), onupdate=datetime.now(timezone("Africa/Blantyre")))
    
    # Relationships
    victim_student = relationship("Student", back_populates="bullying_incidents_as_victim", foreign_keys=[victim_student_id])
    perpetrator_student = relationship("Student", back_populates="bullying_incidents_as_perpetrator", foreign_keys=[perpetrator_student_id])
    teacher = relationship("Teacher", back_populates="bullying_incidents")

class StudentRiskFactor(Base):
    __tablename__ = "student_risk_factors"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    factor_type = Column(SQLEnum(RiskFactorType), nullable=False)
    factor_description = Column(Text, nullable=False)
    severity_level = Column(SQLEnum(SeverityLevel), nullable=False)
    identified_date = Column(Date, nullable=False)
    identified_by_teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=False)
    mitigation_actions = Column(Text)
    is_resolved = Column(Boolean, default=False)
    resolution_date = Column(Date)
    created_at = Column(DateTime, default=datetime.now(timezone("Africa/Blantyre")))
    updated_at = Column(DateTime, default=datetime.now(timezone("Africa/Blantyre")), onupdate=datetime.now(timezone("Africa/Blantyre")))
    
    # Relationships
    student = relationship("Student", back_populates="risk_factors")
    teacher = relationship("Teacher", back_populates="risk_factors")

class DropoutPrediction(Base):
    __tablename__ = "dropout_predictions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    risk_score = Column(Float, nullable=False)  # 0-100
    risk_level = Column(SQLEnum(RiskLevel), nullable=False)
    contributing_factors = Column(JSON)  # Array of factor types
    prediction_date = Column(Date, nullable=False)
    algorithm_version = Column(String(20))
    teacher_notified = Column(Boolean, default=False)
    intervention_recommended = Column(Text)
    created_at = Column(DateTime, default=datetime.now(timezone("Africa/Blantyre")))
    
    # Relationships
    student = relationship("Student", back_populates="dropout_predictions")
from sqlalchemy import Column, Integer, String, Float, Boolean, Date, DateTime, ForeignKey, JSON, Text, Enum    
from sqlalchemy.orm import relationship
from app.database import Base
import enum



class Roles(enum.Enum):
    ADMIN = "admin"
    TEACHER = "teacher"
    HEADTEACHER = "headteacher"

class Gender(enum.Enum):
    MALE = "male"
    FEMALE = "female"

class Status(enum.Enum):
    ACTIVE = "active"
    DROPPED_OUT = "dropped_out"
    TRANSFERRED = "transferred"

class InterventionStatus(enum.Enum):
    PLANNED = "planned"
    ONGOING = "ongoing"
    COMPLETED = "completed"


class RiskCategory(enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high" 


class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True)
    email = Column(String(100), unique=True, index=True)
    hashed_password = Column(String(255))
    role = Column(Enum(Roles), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime)
    last_login = Column(DateTime)
    
    # Relationships
    teacher_profile = relationship("Teacher", back_populates="user", uselist=False)
    student_records = relationship("StudentRecord", back_populates="recorded_by_user")
    interventions = relationship("Intervention", back_populates="responsible_teacher")

class Teacher(Base):
    __tablename__ = 'teachers'
    
    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)
    first_name = Column(String(50))
    last_name = Column(String(50))
    phone = Column(String(20))
    subjects = Column(JSON)
    qualification = Column(String(100))
    hire_date = Column(Date)
    
    # Relationships
    user = relationship("User", back_populates="teacher_profile")
    classes = relationship("ClassEnrollment", back_populates="teacher")
    head_classes = relationship("SchoolClass", back_populates="head_teacher")
    interventions = relationship("Intervention", back_populates="responsible_teacher")

class SchoolClass(Base):
    __tablename__ = 'classes'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50))
    academic_year = Column(String(20))
    head_teacher_id = Column(Integer, ForeignKey('teachers.user_id'))
    classroom = Column(String(20))
    
    # Relationships
    head_teacher = relationship("Teacher", back_populates="head_classes")
    students = relationship("Student", back_populates="current_class")
    teacher_enrollments = relationship("ClassEnrollment", back_populates="school_class")

class Student(Base):
    __tablename__ = 'students'
    
    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String(50))
    last_name = Column(String(50))
    date_of_birth = Column(Date)
    gender = Column(Enum(Gender), nullable=False)
    address = Column(Text)
    parent_guardian_name = Column(String(100))
    parent_guardian_contact = Column(String(20))
    enrollment_date = Column(Date)
    current_class_id = Column(Integer, ForeignKey('classes.id'))
    photo_url = Column(String(255), nullable=True)
    status = Column(Enum(Status), default=Status.ACTIVE)
    
    # Relationships
    current_class = relationship("SchoolClass", back_populates="students")
    records = relationship("StudentRecord", back_populates="student")
    predictions = relationship("DropoutPrediction", back_populates="student")
    dropout_cases = relationship("DropoutCase", back_populates="student")
    interventions = relationship("Intervention", back_populates="student")

class ClassEnrollment(Base):
    __tablename__ = 'class_enrollments'
    
    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey('teachers.user_id'))
    class_id = Column(Integer, ForeignKey('classes.id'))
    subject = Column(String(50))
    
    # Relationships
    teacher = relationship("Teacher", back_populates="classes")
    school_class = relationship("SchoolClass", back_populates="teacher_enrollments")

class StudentRecord(Base):
    __tablename__ = 'student_records'
    
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey('students.id'))
    record_date = Column(Date)
    academic_performance = Column(Float)  # 0-100 scale
    attendance_rate = Column(Float)  # 0-1 scale
    behavior_notes = Column(Text, nullable=True)
    health_notes = Column(Text, nullable=True)
    family_status = Column(String(50))
    economic_status = Column(String(50))
    recorded_by = Column(Integer, ForeignKey('users.id'))
    
    # Relationships
    student = relationship("Student", back_populates="records")
    recorded_by_user = relationship("User", back_populates="student_records")

class DropoutPrediction(Base):
    __tablename__ = 'dropout_predictions'
    
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey('students.id'))
    prediction_date = Column(DateTime)
    risk_score = Column(Float)  # 0-1 probability
    risk_category = Column(Enum(RiskCategory), nullable=False)
    important_factors = Column(JSON)  # JSON of contributing factors
    model_version = Column(String(50))
    
    # Relationships
    student = relationship("Student", back_populates="predictions")

class Intervention(Base):
    __tablename__ = 'interventions'
    
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey('students.id'))
    intervention_type = Column(String(50))
    description = Column(Text)
    start_date = Column(Date)
    end_date = Column(Date)
    responsible_teacher_id = Column(Integer, ForeignKey('teachers.user_id'))
    status = Column(Enum(InterventionStatus), default=InterventionStatus.PLANNED)
    outcome = Column(Text, nullable=True)
    
    # Relationships
    student = relationship("Student", back_populates="interventions")
    responsible_teacher = relationship("Teacher", back_populates="interventions")

class DropoutCase(Base):
    __tablename__ = 'dropout_cases'
    
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey('students.id'))
    dropout_date = Column(Date)
    reason = Column(Text)
    follow_up_actions = Column(Text)
    is_reversible = Column(Boolean)
    case_closed = Column(Boolean, default=False)
    closed_date = Column(Date, nullable=True)
    
    # Relationships
    student = relationship("Student", back_populates="dropout_cases")
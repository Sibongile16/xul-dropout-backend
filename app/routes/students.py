from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import Optional, List, Dict, Any
import pandas as pd
import io
from datetime import datetime, date
import uuid
import re
from enum import Enum

from app.database import get_db
from app.utils.auth import get_current_user
from app.models.all_models import (
    User, Teacher, Student, Guardian, Class, UserRole, Gender, 
    RelationshipType, TransportMethod, IncomeRange, EducationLevel
)

router = APIRouter(prefix="/api/students", tags=["students"])

# Response models
from pydantic import BaseModel, ValidationError

class UploadResponse(BaseModel):
    message: str
    records_added: int
    records_updated: int = 0
    errors: Optional[List[str]] = None
    warnings: Optional[List[str]] = None

class ValidationError(BaseModel):
    row: int
    field: str
    value: str
    error: str

# CSV field mappings and validation
REQUIRED_STUDENT_FIELDS = [
    'first_name', 'last_name', 'date_of_birth', 'gender', 'student_number'
]

OPTIONAL_STUDENT_FIELDS = [
    'home_address', 'distance_to_school_km', 'transport_method',
    'special_needs', 'medical_conditions', 'enrollment_date'
]

REQUIRED_GUARDIAN_FIELDS = [
    'guardian_first_name', 'guardian_last_name', 'relationship_to_student'
]

OPTIONAL_GUARDIAN_FIELDS = [
    'guardian_phone', 'guardian_email', 'guardian_address',
    'guardian_occupation', 'guardian_income_range', 'guardian_education_level'
]

def validate_csv_headers(df: pd.DataFrame) -> List[str]:
    """Validate that required headers are present in the CSV."""
    errors = []
    missing_required = []
    
    # Check required student fields
    for field in REQUIRED_STUDENT_FIELDS:
        if field not in df.columns:
            missing_required.append(field)
    
    # Check required guardian fields
    for field in REQUIRED_GUARDIAN_FIELDS:
        if field not in df.columns:
            missing_required.append(field)
    
    if missing_required:
        errors.append(f"Missing required columns: {', '.join(missing_required)}")
    
    return errors

def validate_date(date_str: str) -> Optional[date]:
    """Validate and parse date string."""
    if pd.isna(date_str) or str(date_str).strip() == '':
        return None
    
    date_formats = ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y']
    
    for fmt in date_formats:
        try:
            return datetime.strptime(str(date_str).strip(), fmt).date()
        except ValueError:
            continue
    
    raise ValueError(f"Invalid date format: {date_str}")

def validate_enum_value(value: str, enum_class) -> Optional[str]:
    """Validate enum values."""
    if pd.isna(value) or str(value).strip() == '':
        return None
    
    value_str = str(value).strip().lower()
    
    # Try to match enum values
    for enum_item in enum_class:
        if enum_item.value.lower() == value_str:
            return enum_item
    
    # Try common variations for gender
    if enum_class == Gender:
        if value_str in ['m', 'boy', 'man']:
            return Gender.MALE
        elif value_str in ['f', 'girl', 'woman']:
            return Gender.FEMALE
    
    raise ValueError(f"Invalid {enum_class.__name__}: {value}")

def calculate_age(birth_date: date) -> int:
    """Calculate age from birth date."""
    today = date.today()
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))

def validate_phone_number(phone: str) -> Optional[str]:
    """Validate phone number format."""
    if pd.isna(phone) or str(phone).strip() == '':
        return None
    
    phone_str = str(phone).strip()
    # Basic phone validation - adjust regex as needed for your region
    phone_pattern = r'^[\+]?[0-9\s\-\(\)]{7,15}$'
    
    if not re.match(phone_pattern, phone_str):
        raise ValueError(f"Invalid phone number format: {phone}")
    
    return phone_str

def validate_email(email: str) -> Optional[str]:
    """Validate email format."""
    if pd.isna(email) or str(email).strip() == '':
        return None
    
    email_str = str(email).strip()
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if not re.match(email_pattern, email_str):
        raise ValueError(f"Invalid email format: {email}")
    
    return email_str.lower()

def process_student_row(row: pd.Series, row_index: int, class_id: Optional[str] = None) -> tuple:
    """Process a single row of student data."""
    errors = []
    student_data = {}
    guardian_data = {}
    
    try:
        # Process required student fields
        student_data['first_name'] = str(row['first_name']).strip()
        student_data['last_name'] = str(row['last_name']).strip()
        student_data['student_number'] = str(row['student_number']).strip()
        
        # Validate date of birth
        try:
            dob = validate_date(row['date_of_birth'])
            if not dob:
                errors.append(f"Row {row_index}: date_of_birth is required")
            else:
                student_data['date_of_birth'] = dob
                student_data['age'] = calculate_age(dob)
        except ValueError as e:
            errors.append(f"Row {row_index}: {str(e)}")
        
        # Validate gender
        try:
            gender = validate_enum_value(row['gender'], Gender)
            if not gender:
                errors.append(f"Row {row_index}: gender is required")
            else:
                student_data['gender'] = gender
        except ValueError as e:
            errors.append(f"Row {row_index}: {str(e)}")
        
        # Process optional student fields
        if 'home_address' in row and not pd.isna(row['home_address']):
            student_data['home_address'] = str(row['home_address']).strip()
        
        if 'distance_to_school_km' in row and not pd.isna(row['distance_to_school_km']):
            try:
                student_data['distance_to_school_km'] = float(row['distance_to_school_km'])
            except ValueError:
                errors.append(f"Row {row_index}: Invalid distance_to_school_km")
        
        if 'transport_method' in row:
            try:
                transport = validate_enum_value(row['transport_method'], TransportMethod)
                if transport:
                    student_data['transport_method'] = transport
            except ValueError as e:
                errors.append(f"Row {row_index}: {str(e)}")
        
        if 'special_needs' in row and not pd.isna(row['special_needs']):
            student_data['special_needs'] = str(row['special_needs']).strip()
        
        if 'medical_conditions' in row and not pd.isna(row['medical_conditions']):
            student_data['medical_conditions'] = str(row['medical_conditions']).strip()
        
        if 'enrollment_date' in row:
            try:
                enrollment_date = validate_date(row['enrollment_date'])
                if enrollment_date:
                    student_data['enrollment_date'] = enrollment_date
            except ValueError as e:
                errors.append(f"Row {row_index}: {str(e)}")
        
        if not student_data.get('enrollment_date'):
            student_data['enrollment_date'] = date.today()
        
        # Set class if provided
        if class_id:
            student_data['current_class_id'] = class_id
        
        # Process guardian data
        guardian_data['first_name'] = str(row['guardian_first_name']).strip()
        guardian_data['last_name'] = str(row['guardian_last_name']).strip()
        
        # Validate relationship
        try:
            relationship = validate_enum_value(row['relationship_to_student'], RelationshipType)
            if not relationship:
                errors.append(f"Row {row_index}: relationship_to_student is required")
            else:
                guardian_data['relationship_to_student'] = relationship
        except ValueError as e:
            errors.append(f"Row {row_index}: {str(e)}")
        
        # Process optional guardian fields
        if 'guardian_phone' in row:
            try:
                phone = validate_phone_number(row['guardian_phone'])
                if phone:
                    guardian_data['phone_number'] = phone
            except ValueError as e:
                errors.append(f"Row {row_index}: {str(e)}")
        
        if 'guardian_email' in row:
            try:
                email = validate_email(row['guardian_email'])
                if email:
                    guardian_data['email'] = email
            except ValueError as e:
                errors.append(f"Row {row_index}: {str(e)}")
        
        if 'guardian_address' in row and not pd.isna(row['guardian_address']):
            guardian_data['address'] = str(row['guardian_address']).strip()
        
        if 'guardian_occupation' in row and not pd.isna(row['guardian_occupation']):
            guardian_data['occupation'] = str(row['guardian_occupation']).strip()
        
        if 'guardian_income_range' in row:
            try:
                income = validate_enum_value(row['guardian_income_range'], IncomeRange)
                if income:
                    guardian_data['monthly_income_range'] = income
            except ValueError as e:
                errors.append(f"Row {row_index}: {str(e)}")
        
        if 'guardian_education_level' in row:
            try:
                education = validate_enum_value(row['guardian_education_level'], EducationLevel)
                if education:
                    guardian_data['education_level'] = education
            except ValueError as e:
                errors.append(f"Row {row_index}: {str(e)}")
        
    except Exception as e:
        errors.append(f"Row {row_index}: Unexpected error - {str(e)}")
    
    return student_data, guardian_data, errors

@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_student_csv(
    file: UploadFile = File(...),
    class_id: Optional[str] = Form(None),
    term: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Upload a CSV file containing student records.
    Only accessible by teachers, headteachers, and admins.
    """
    
    # Check authorization
    if current_user.role not in [UserRole.TEACHER, UserRole.ADMIN, UserRole.HEADTEACHER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only teachers and administrators can upload student data."
        )
    
    # Validate file type
    if not file.filename.lower().endswith('.csv'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bad File Format. Only CSV files are accepted."
        )
    
    # Validate class_id if provided
    if class_id:
        class_obj = db.query(Class).filter(Class.id == class_id).first()
        if not class_obj:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Validation Error: Invalid class_id provided."
            )
    
    try:
        # Read CSV file
        content = await file.read()
        df = pd.read_csv(io.StringIO(content.decode('utf-8')))
        
        if df.empty:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bad File Format. CSV file is empty."
            )
        
        # Strip whitespace from column names
        df.columns = df.columns.str.strip()
        
        # Validate headers
        header_errors = validate_csv_headers(df)
        if header_errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Validation Error: {'; '.join(header_errors)}"
            )
        
        # Process records
        records_added = 0
        records_updated = 0
        all_errors = []
        warnings = []
        
        for index, row in df.iterrows():
            try:
                student_data, guardian_data, row_errors = process_student_row(
                    row, index + 2, class_id  # +2 because CSV rows start from 1 and we skip header
                )
                
                if row_errors:
                    all_errors.extend(row_errors)
                    continue
                
                # Check if guardian already exists (by name and relationship)
                existing_guardian = db.query(Guardian).filter_by(
                    first_name=guardian_data['first_name'],
                    last_name=guardian_data['last_name'],
                    relationship_to_student=guardian_data['relationship_to_student']
                ).first()
                
                if existing_guardian:
                    # Update guardian data if provided
                    for key, value in guardian_data.items():
                        if hasattr(existing_guardian, key) and value is not None:
                            setattr(existing_guardian, key, value)
                    guardian_id = existing_guardian.id
                else:
                    # Create new guardian
                    guardian = Guardian(**guardian_data)
                    db.add(guardian)
                    db.flush()  # Get the ID
                    guardian_id = guardian.id
                
                # Check if student already exists
                existing_student = db.query(Student).filter_by(
                    student_number=student_data['student_number']
                ).first()
                
                if existing_student:
                    # Update existing student
                    for key, value in student_data.items():
                        if hasattr(existing_student, key) and value is not None:
                            setattr(existing_student, key, value)
                    existing_student.guardian_id = guardian_id
                    existing_student.updated_at = datetime.now()
                    records_updated += 1
                    warnings.append(f"Updated existing student: {student_data['student_number']}")
                else:
                    # Create new student
                    student_data['guardian_id'] = guardian_id
                    student = Student(**student_data)
                    db.add(student)
                    records_added += 1
                
            except Exception as e:
                all_errors.append(f"Row {index + 2}: Database error - {str(e)}")
                continue
        
        # Commit if no critical errors
        if records_added > 0 or records_updated > 0:
            try:
                db.commit()
            except IntegrityError as e:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Validation Error: Database integrity error - {str(e)}"
                )
        else:
            db.rollback()
        
        # Return response
        if all_errors and records_added == 0 and records_updated == 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Validation Error: {'; '.join(all_errors[:5])}..."  # Show first 5 errors
            )
        
        response = UploadResponse(
            message="Upload successful" if records_added > 0 or records_updated > 0 else "No records processed",
            records_added=records_added,
            records_updated=records_updated
        )
        
        if all_errors:
            response.errors = all_errors[:10]  # Limit to first 10 errors
        
        if warnings:
            response.warnings = warnings[:10]  # Limit to first 10 warnings
        
        return response
        
    except pd.errors.EmptyDataError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bad File Format. CSV file is empty or invalid."
        )
    except pd.errors.ParserError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bad File Format. Unable to parse CSV file."
        )
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Bad File Format. File encoding not supported. Please use UTF-8."
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )

# Additional endpoint to get CSV template
@router.get("/upload/template")
async def get_csv_template(
    # current_user: User = Depends(get_current_user)
):
    """
    Download a CSV template for student uploads.
    """
    
    # if current_user.role not in [UserRole.TEACHER, UserRole.ADMIN, UserRole.HEADTEACHER]:
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN,
    #         detail="Access denied."
    #     )
    
    # Create template headers
    headers = (
        REQUIRED_STUDENT_FIELDS + 
        OPTIONAL_STUDENT_FIELDS + 
        REQUIRED_GUARDIAN_FIELDS + 
        OPTIONAL_GUARDIAN_FIELDS
    )
    
    # Create sample data
    sample_data = {
        'first_name': ['John', 'Jane'],
        'last_name': ['Banda', 'Mwale'],
        'date_of_birth': ['2010-05-15', '2011-03-22'],
        'gender': ['male', 'female'],
        'student_number': ['STU001', 'STU002'],
        'home_address': ['123 Main St, Lilongwe', '456 Oak Ave, Blantyre'],
        'distance_to_school_km': [2.5, 1.8],
        'transport_method': ['walking', 'bicycle'],
        'special_needs': ['', 'Hearing impaired'],
        'medical_conditions': ['', 'Asthma'],
        'enrollment_date': ['2024-01-15', '2024-01-15'],
        'guardian_first_name': ['Peter', 'Mary'],
        'guardian_last_name': ['Banda', 'Mwale'],
        'relationship_to_student': ['parent', 'parent'],
        'guardian_phone': ['+265991234567', '+265998765432'],
        'guardian_email': ['peter.banda@email.com', 'mary.mwale@email.com'],
        'guardian_address': ['123 Main St, Lilongwe', '456 Oak Ave, Blantyre'],
        'guardian_occupation': ['Teacher', 'Nurse'],
        'guardian_income_range': ['50k_100k', '100k_200k'],
        'guardian_education_level': ['tertiary', 'tertiary']
    }
    
    # Create DataFrame and CSV
    template_df = pd.DataFrame(sample_data)
    csv_buffer = io.StringIO()
    template_df.to_csv(csv_buffer, index=False)
    
    from fastapi.responses import StreamingResponse
    
    return StreamingResponse(
        io.BytesIO(csv_buffer.getvalue().encode('utf-8')),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=student_upload_template.csv"}
    )
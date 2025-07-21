from enum import Enum
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import date, datetime

from app.database import get_db
from app.models.all_models import Class, DailyAttendance, Student, Teacher, TeacherClass, User, UserRole
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/attendance", tags=["Attendance"])


class AttendanceStatus(str, Enum):
    PRESENT = "present"
    ABSENT = "absent"
    LATE = "late"

class AttendanceBase(BaseModel):
    student_id: UUID
    class_id: UUID
    attendance_date: date
    status: AttendanceStatus
    notes: Optional[str] = None

class AttendanceCreate(AttendanceBase):
    pass

class AttendanceUpdate(BaseModel):
    status: Optional[AttendanceStatus] = None
    notes: Optional[str] = None

class AttendanceResponse(AttendanceBase):
    id: UUID
    student_name: str
    class_name: str
    marked_by_teacher_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    
    @classmethod
    def from_orm_with_names(cls, db_attendance: DailyAttendance, db: Session):
        # Get student name
        student = db.query(Student).filter(Student.id == db_attendance.student_id).first()
        student_name = f"{student.first_name} {student.last_name}" if student else "Unknown Student"
        
        # Get class name
        class_ = db.query(Class).filter(Class.id == db_attendance.class_id).first()
        class_name = class_.name if class_ else "Unknown Class"
        
        return cls(
            id=db_attendance.id,
            student_id=db_attendance.student_id,
            student_name=student_name,
            class_id=db_attendance.class_id,
            class_name=class_name,
            attendance_date=db_attendance.attendance_date,
            status=db_attendance.status,
            notes=db_attendance.notes,
            marked_by_teacher_id=db_attendance.marked_by_teacher_id,
            created_at=db_attendance.created_at,
            updated_at=db_attendance.updated_at
        )

class AttendanceBulkRecord(BaseModel):
    student_id: UUID
    status: AttendanceStatus
    notes: Optional[str] = None

class AttendanceBulkCreate(BaseModel):
    attendance_date: date
    records: List[AttendanceBulkRecord]

class AttendanceStatsResponse(BaseModel):
    class_id: UUID
    class_name: str
    start_date: date
    end_date: date
    total_records: int
    present_count: int
    absent_count: int
    late_count: int
    attendance_rate: float

class AttendanceSummaryResponse(BaseModel):
    student_id: UUID
    student_name: str
    class_id: Optional[UUID] = None
    class_name: Optional[str] = None
    term_start_date: date
    term_end_date: date
    total_days: int
    present_days: int
    absent_days: int
    late_days: int
    attendance_percentage: float


@router.post("/", response_model=AttendanceResponse, status_code=status.HTTP_201_CREATED)
def create_attendance_record(
    attendance: AttendanceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new attendance record for a student.
    Teachers can only create records for their own classes.
    """
    # Check if student exists
    student = db.query(Student).filter(Student.id == attendance.student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    
    # Check if class exists
    class_ = db.query(Class).filter(Class.id == attendance.class_id).first()
    if not class_:
        raise HTTPException(status_code=404, detail="Class not found")
    
    # For teachers, verify they teach this class
    if current_user.role == UserRole.TEACHER:
        teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
        if not teacher:
            raise HTTPException(status_code=403, detail="Teacher profile not found")
        
        # Check if teacher is assigned to this class
        teacher_class = db.query(TeacherClass).filter(
            TeacherClass.teacher_id == teacher.id,
            TeacherClass.class_id == attendance.class_id
        ).first()
        if not teacher_class:
            raise HTTPException(status_code=403, detail="Not authorized to mark attendance for this class")
    
    # Check if attendance record already exists for this student on this date
    existing_record = db.query(DailyAttendance).filter(
        DailyAttendance.student_id == attendance.student_id,
        DailyAttendance.attendance_date == attendance.attendance_date
    ).first()
    
    if existing_record:
        raise HTTPException(status_code=400, detail="Attendance record already exists for this student on this date")
    
    # Create new attendance record
    new_attendance = DailyAttendance(
        student_id=attendance.student_id,
        class_id=attendance.class_id,
        attendance_date=attendance.attendance_date,
        status=attendance.status,
        notes=attendance.notes,
        marked_by_teacher_id=current_user.id if current_user.role != UserRole.ADMIN else None
    )
    
    db.add(new_attendance)
    db.commit()
    db.refresh(new_attendance)
    
    return AttendanceResponse.from_orm_with_names(new_attendance, db)

@router.post("/bulk", response_model=List[AttendanceResponse], status_code=status.HTTP_201_CREATED)
def create_bulk_attendance_records(
    bulk_data: AttendanceBulkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create multiple attendance records at once.
    Teachers can only create records for their own classes.
    """
    # Verify all students belong to the same class
    student_ids = [record.student_id for record in bulk_data.records]
    students = db.query(Student).filter(Student.id.in_(student_ids)).all()
    
    if len(students) != len(student_ids):
        raise HTTPException(status_code=404, detail="One or more students not found")
    
    class_id = students[0].class_id
    if not all(student.class_id == class_id for student in students):
        raise HTTPException(status_code=400, detail="All students must belong to the same class")
    
    # For teachers, verify they teach this class
    if current_user.role == UserRole.TEACHER:
        teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
        if not teacher:
            raise HTTPException(status_code=403, detail="Teacher profile not found")
        
        teacher_class = db.query(TeacherClass).filter(
            TeacherClass.teacher_id == teacher.id,
            TeacherClass.class_id == class_id
        ).first()
        if not teacher_class:
            raise HTTPException(status_code=403, detail="Not authorized to mark attendance for this class")
    
    # Check for existing records
    existing_records = db.query(DailyAttendance).filter(
        DailyAttendance.student_id.in_(student_ids),
        DailyAttendance.attendance_date == bulk_data.attendance_date
    ).all()
    
    if existing_records:
        existing_student_ids = {str(record.student_id) for record in existing_records}
        raise HTTPException(
            status_code=400,
            detail=f"Attendance records already exist for these students on this date: {', '.join(existing_student_ids)}"
        )
    
    # Create new records
    new_attendance_records = []
    for record in bulk_data.records:
        new_record = DailyAttendance(
            student_id=record.student_id,
            class_id=class_id,
            attendance_date=bulk_data.attendance_date,
            status=record.status,
            notes=record.notes,
            marked_by_teacher_id=current_user.id if current_user.role != UserRole.ADMIN else None
        )
        new_attendance_records.append(new_record)
        db.add(new_record)
    
    db.commit()
    
    return [AttendanceResponse.from_orm_with_names(record, db) for record in new_attendance_records]

@router.get("/student/{student_id}", response_model=List[AttendanceResponse])
def get_student_attendance_history(
    student_id: UUID,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get attendance history for a specific student.
    Teachers can only view attendance for students in their classes.
    """
    # Check if student exists
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    
    # For teachers, verify they teach this student's class
    if current_user.role == UserRole.TEACHER:
        teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
        if not teacher:
            raise HTTPException(status_code=403, detail="Teacher profile not found")
        
        teacher_class = db.query(TeacherClass).filter(
            TeacherClass.teacher_id == teacher.id,
            TeacherClass.class_id == student.class_id
        ).first()
        if not teacher_class:
            raise HTTPException(status_code=403, detail="Not authorized to view this student's attendance")
    
    # Build query
    query = db.query(DailyAttendance).filter(DailyAttendance.student_id == student_id)
    
    if start_date:
        query = query.filter(DailyAttendance.attendance_date >= start_date)
    if end_date:
        query = query.filter(DailyAttendance.attendance_date <= end_date)
    
    attendance_records = query.order_by(DailyAttendance.attendance_date.desc()).all()
    
    return [AttendanceResponse.from_orm_with_names(record, db) for record in attendance_records]

@router.get("/class/{class_id}", response_model=List[AttendanceResponse])
def get_class_attendance_for_date(
    class_id: UUID,
    attendance_date: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all attendance records for a specific class on a specific date.
    Teachers can only view attendance for their own classes.
    """
    # Check if class exists
    class_ = db.query(Class).filter(Class.id == class_id).first()
    if not class_:
        raise HTTPException(status_code=404, detail="Class not found")
    
    # For teachers, verify they teach this class
    if current_user.role == UserRole.TEACHER:
        teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
        if not teacher:
            raise HTTPException(status_code=403, detail="Teacher profile not found")
        
        teacher_class = db.query(TeacherClass).filter(
            TeacherClass.teacher_id == teacher.id,
            TeacherClass.class_id == class_id
        ).first()
        if not teacher_class:
            raise HTTPException(status_code=403, detail="Not authorized to view attendance for this class")
    
    attendance_records = db.query(DailyAttendance).filter(
        DailyAttendance.class_id == class_id,
        DailyAttendance.attendance_date == attendance_date
    ).all()
    
    return [AttendanceResponse.from_orm_with_names(record, db) for record in attendance_records]

@router.get("/class/{class_id}/stats", response_model=AttendanceStatsResponse)
def get_class_attendance_stats(
    class_id: UUID,
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get attendance statistics for a class over a date range.
    Teachers can only view stats for their own classes.
    """
    # Check if class exists
    class_ = db.query(Class).filter(Class.id == class_id).first()
    if not class_:
        raise HTTPException(status_code=404, detail="Class not found")
    
    # For teachers, verify they teach this class
    if current_user.role == UserRole.TEACHER:
        teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
        if not teacher:
            raise HTTPException(status_code=403, detail="Teacher profile not found")
        
        teacher_class = db.query(TeacherClass).filter(
            TeacherClass.teacher_id == teacher.id,
            TeacherClass.class_id == class_id
        ).first()
        if not teacher_class:
            raise HTTPException(status_code=403, detail="Not authorized to view attendance for this class")
    
    # Get all attendance records for the class in the date range
    attendance_records = db.query(DailyAttendance).filter(
        DailyAttendance.class_id == class_id,
        DailyAttendance.attendance_date >= start_date,
        DailyAttendance.attendance_date <= end_date
    ).all()
    
    # Calculate statistics
    total_records = len(attendance_records)
    present_count = sum(1 for record in attendance_records if record.status == AttendanceStatus.PRESENT)
    absent_count = sum(1 for record in attendance_records if record.status == AttendanceStatus.ABSENT)
    late_count = sum(1 for record in attendance_records if record.status == AttendanceStatus.LATE)
    
    attendance_rate = (present_count / total_records * 100) if total_records > 0 else 0
    
    return AttendanceStatsResponse(
        class_id=class_id,
        class_name=class_.name,
        start_date=start_date,
        end_date=end_date,
        total_records=total_records,
        present_count=present_count,
        absent_count=absent_count,
        late_count=late_count,
        attendance_rate=round(attendance_rate, 2)
    )

@router.get("/student/{student_id}/summary", response_model=AttendanceSummaryResponse)
def get_student_attendance_summary(
    student_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get attendance summary for a student (current term/year).
    Teachers can only view attendance for students in their classes.
    """
    # Check if student exists
    student = db.query(Student).filter(Student.id == student_id).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    
    # For teachers, verify they teach this student's class
    if current_user.role == UserRole.TEACHER:
        teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
        if not teacher:
            raise HTTPException(status_code=403, detail="Teacher profile not found")
        
        teacher_class = db.query(TeacherClass).filter(
            TeacherClass.teacher_id == teacher.id,
            TeacherClass.class_id == student.class_id
        ).first()
        if not teacher_class:
            raise HTTPException(status_code=403, detail="Not authorized to view this student's attendance")
    
    # Get current term (simplified - in a real app you'd have a proper term system)
    current_year = date.today().year
    term_start_date = date(current_year, 1, 1)  # Example - adjust based on your term system
    term_end_date = date(current_year, 12, 31)  # Example
    
    # Get attendance records for current term
    attendance_records = db.query(DailyAttendance).filter(
        DailyAttendance.student_id == student_id,
        DailyAttendance.attendance_date >= term_start_date,
        DailyAttendance.attendance_date <= term_end_date
    ).all()
    
    # Calculate summary
    total_days = len(attendance_records)
    present_days = sum(1 for record in attendance_records if record.status == AttendanceStatus.PRESENT)
    absent_days = sum(1 for record in attendance_records if record.status == AttendanceStatus.ABSENT)
    late_days = sum(1 for record in attendance_records if record.status == AttendanceStatus.LATE)
    
    attendance_percentage = (present_days / total_days * 100) if total_days > 0 else 0
    
    return AttendanceSummaryResponse(
        student_id=student_id,
        student_name=f"{student.first_name} {student.last_name}",
        class_id=student.class_id,
        class_name=student.class_.name if student.class_ else None,
        term_start_date=term_start_date,
        term_end_date=term_end_date,
        total_days=total_days,
        present_days=present_days,
        absent_days=absent_days,
        late_days=late_days,
        attendance_percentage=round(attendance_percentage, 2)
    )

@router.put("/{attendance_id}", response_model=AttendanceResponse)
def update_attendance_record(
    attendance_id: UUID,
    attendance_update: AttendanceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update an existing attendance record.
    Teachers can only update records for their own classes.
    """
    attendance_record = db.query(DailyAttendance).filter(DailyAttendance.id == attendance_id).first()
    if not attendance_record:
        raise HTTPException(status_code=404, detail="Attendance record not found")
    
    # For teachers, verify they teach this class
    if current_user.role == UserRole.TEACHER:
        teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
        if not teacher:
            raise HTTPException(status_code=403, detail="Teacher profile not found")
        
        teacher_class = db.query(TeacherClass).filter(
            TeacherClass.teacher_id == teacher.id,
            TeacherClass.class_id == attendance_record.class_id
        ).first()
        if not teacher_class:
            raise HTTPException(status_code=403, detail="Not authorized to update this attendance record")
    
    # Update record
    if attendance_update.status:
        attendance_record.status = attendance_update.status
    if attendance_update.notes is not None:
        attendance_record.notes = attendance_update.notes
    
    db.commit()
    db.refresh(attendance_record)
    
    return AttendanceResponse.from_orm_with_names(attendance_record, db)

@router.delete("/{attendance_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attendance_record(
    attendance_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete an attendance record.
    Only admins and the teacher who created the record can delete it.
    """
    attendance_record = db.query(DailyAttendance).filter(DailyAttendance.id == attendance_id).first()
    if not attendance_record:
        raise HTTPException(status_code=404, detail="Attendance record not found")
    
    # Check permissions
    if current_user.role == UserRole.TEACHER:
        teacher = db.query(Teacher).filter(Teacher.user_id == current_user.id).first()
        if not teacher:
            raise HTTPException(status_code=403, detail="Teacher profile not found")
        
        # Check if teacher is assigned to this class
        teacher_class = db.query(TeacherClass).filter(
            TeacherClass.teacher_id == teacher.id,
            TeacherClass.class_id == attendance_record.class_id
        ).first()
        if not teacher_class:
            raise HTTPException(status_code=403, detail="Not authorized to delete this attendance record")
        
        # Check if this teacher created the record
        if attendance_record.marked_by_teacher_id != teacher.id:
            raise HTTPException(status_code=403, detail="Can only delete attendance records you created")
    
    db.delete(attendance_record)
    db.commit()
    
    return None
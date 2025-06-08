from datetime import datetime, date
from uuid import uuid4
from pytz import timezone
from sqlalchemy.orm import Session
from app.database import get_db

from app.models.all_models import Gender, User, UserRole, Teacher
from app.utils.auth import get_password_hash


# Create a new teacher with user data
def create_teacher_with_user(db: Session,
    username,
    email,
    password_hash,
    first_name,
    last_name,
    phone_number=None,
    date_of_birth=None,
    gender=None,
    address=None,
    hire_date=None,
    qualification=None,
    experience_years=None
):
    try:
        # Create User first
        new_user = User(
            id=uuid4(),
            username=username,
            email=email,
            password_hash=password_hash,
            role=UserRole.ADMIN,
            is_active=True,
            created_at=datetime.now(timezone("Africa/Harare")),
            updated_at=datetime.now(timezone("Africa/Harare"))
        )
        
        # Create Teacher
        new_teacher = Teacher(
            id=uuid4(),
            user_id=new_user.id,
            first_name=first_name,
            last_name=last_name,
            phone_number=phone_number,
            date_of_birth=date_of_birth,
            gender=gender,
            address=address,
            hire_date=hire_date or date.today(timezone("Africa/Harare")), 
            qualification=qualification,
            experience_years=experience_years,
            created_at=datetime.now(timezone("Africa/Harare")),
            updated_at=datetime.now(timezone("Africa/Harare"))
        )
        
        # Add to db and commit
        db.add(new_user)
        db.add(new_teacher)
        db.commit()
        
        return new_teacher
        
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()

# Example usage
if __name__ == "__main__":
    teacher = create_teacher_with_user(db=next(get_db()),
        username="admin",
        email="admin@malivenji.com",
        password_hash=get_password_hash("password123"), 
        first_name="Sibongile",
        last_name="Malama",
        phone_number="+265993453670",
        date_of_birth=date(2000, 10, 16),
        gender=Gender.FEMALE,
        address="Mchengautuba, Malivenji",
        hire_date=date(2020, 1, 10),
        qualification="BSc. in Data Science",
        experience_years=10
    )
    
    print(f"Created teacher {teacher.first_name} {teacher.last_name} with user ID {teacher.user_id}")
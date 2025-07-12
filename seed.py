import logging
from pytz import timezone
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from datetime import date, datetime
import uuid
from app.database import SessionLocal, engine
from app.models.all_models import Base, User, Teacher, Class, TeacherClass, Guardian, Student, Subject, AcademicTerm, SubjectScore, BullyingIncident, DropoutPrediction
from enum import Enum
from app.schemas.related_schemas import GenderEnum, UserRoleEnum
from app.utils.auth import get_password_hash

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('database_seed.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def clear_database_tables(db):
    """Clear all tables and enum types in the correct order"""
    try:
        logger.info("Dropping all tables and enums with CASCADE...")
        
        # Disable foreign key checks temporarily (PostgreSQL)
        db.execute(text("SET session_replication_role = 'replica';"))
        
        # Drop all tables
        tables = db.execute(text("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            AND table_type = 'BASE TABLE'
        """)).fetchall()
        
        for table in tables:
            table_name = table[0]
            try:
                db.execute(text(f'DROP TABLE IF EXISTS "{table_name}" CASCADE;'))
                logger.debug(f"Dropped table: {table_name}")
            except Exception as e:
                logger.warning(f"Error dropping table {table_name}: {str(e)}")
                db.rollback()

        # Drop all custom enum types
        enums = db.execute(text("""
            SELECT typname 
            FROM pg_type 
            WHERE typtype = 'e' 
            AND typnamespace = (
                SELECT oid FROM pg_namespace WHERE nspname = 'public'
            )
        """)).fetchall()
        
        for enum in enums:
            enum_name = enum[0]
            try:
                db.execute(text(f'DROP TYPE IF EXISTS "{enum_name}" CASCADE;'))
                logger.debug(f"Dropped enum: {enum_name}")
            except Exception as e:
                logger.warning(f"Error dropping enum {enum_name}: {str(e)}")
                db.rollback()

        # Re-enable foreign key constraints
        db.execute(text("SET session_replication_role = 'origin';"))
        db.commit()
        logger.info("Successfully cleared all tables and enums")
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error clearing tables/enums: {str(e)}", exc_info=True)
        raise
    
    
def seed_database():
    db = SessionLocal()
    
    try:
        logger.info("Starting database seeding process...")
        
        # Clear existing data
        clear_database_tables(db)
        
        # Recreate all tables
        logger.info("Creating database tables...")
        Base.metadata.create_all(bind=engine)
        
        # 1. Create Users
        logger.info("Creating users...")
        users = [
            User(
                id=uuid.uuid4(),
                username="admin_sibo",
                email="admin@malivenji.edu.mw",
                password_hash=get_password_hash("password1234"),
                role=UserRoleEnum.ADMIN.value,
            ),
            User(
                id=uuid.uuid4(),
                username="ht_kamanga",
                email="kamanga@malivenji.edu.mw",
                password_hash=get_password_hash("password1234"),
                role=UserRoleEnum.HEADTEACHER.value,
            ),
            User(
                id=uuid.uuid4(),
                username="teacher_mwawi",
                email="mwawi@malivenji.edu.mw",
                password_hash=get_password_hash("password1234"),
                role=UserRoleEnum.TEACHER.value,
            ),
            User(
                id=uuid.uuid4(),
                username="teacher_chimango",
                email="chimango@malivenji.edu.mw",
                password_hash=get_password_hash("password1234"),
                role=UserRoleEnum.TEACHER.value,
            )
        ]
        db.add_all(users)
        db.commit()
        logger.info(f"Created {len(users)} users")

        # 2. Create Teachers
        logger.info("Creating teachers...")
        teachers = [
            Teacher(
                id=uuid.uuid4(),
                user_id=users[1].id,
                first_name="Edson",
                last_name="Kamanga",
                phone_number="+265 991 112 233",
                date_of_birth=date(1975, 5, 15),
                gender=GenderEnum.MALE.value,
                address="Hilltop, Mzuzu",
                hire_date=date(2010, 1, 10),
                qualification="Bachelor of Education",
                experience_years=13
            ),
            Teacher(
                id=uuid.uuid4(),
                user_id=users[2].id,
                first_name="Mwawi",
                last_name="Nyirenda",
                phone_number="+265 881 234 567",
                date_of_birth=date(1988, 3, 12),
                gender=GenderEnum.FEMALE.value,
                address="Chibavi, Mzuzu",
                hire_date=date(2016, 2, 1),
                qualification="Diploma in Primary Education",
                experience_years=7
            ),
            Teacher(
                id=uuid.uuid4(),
                user_id=users[3].id,
                first_name="Chimango",
                last_name="Mhango",
                phone_number="+265 992 345 678",
                date_of_birth=date(1992, 7, 25),
                gender="male",
                address="Zolozolo, Mzuzu",
                hire_date=date(2019, 1, 15),
                qualification="Bachelor of Education",
                experience_years=4
            )
        ]
        db.add_all(teachers)
        db.commit()
        logger.info(f"Created {len(teachers)} teachers")

        # 3. Create Classes with shortened codes
        logger.info("Creating classes...")
        classes = [
            Class(
                id=uuid.uuid4(),
                name="Standard 1",
                code="STD1-2023",  # Shortened to fit varchar(10)
                academic_year="2023-2024",
                capacity=70,
                is_active=True
            ),
            Class(
                id=uuid.uuid4(),
                name="Standard 2",
                code="STD2-2023",  # Shortened to fit varchar(10)
                academic_year="2023-2024",
                capacity=70,
                is_active=True
            ),
            Class(
                id=uuid.uuid4(),
                name="Standard 5",
                code="STD5-2023",  # Shortened to fit varchar(10)
                academic_year="2023-2024",
                capacity=65,
                is_active=True
            )
        ]
        db.add_all(classes)
        db.commit()
        logger.info(f"Created {len(classes)} classes")

        # 4. Create Teacher-Class Assignments
        logger.info("Creating teacher-class assignments...")
        teacher_classes = [
            TeacherClass(
                id=uuid.uuid4(),
                teacher_id=teachers[1].id,
                class_id=classes[0].id,
                is_class_teacher=True
            ),
            TeacherClass(
                id=uuid.uuid4(),
                teacher_id=teachers[2].id,
                class_id=classes[2].id,
                is_class_teacher=True
            )
        ]
        db.add_all(teacher_classes)
        db.commit()
        logger.info(f"Created {len(teacher_classes)} teacher-class assignments")

        # 5. Create Guardians
        logger.info("Creating guardians...")
        guardians = [
            Guardian(
                id=uuid.uuid4(),
                first_name="Grace",
                last_name="Kanyinji",
                relationship_to_student="parent",
                phone_number="+265 888 112 233",
                email="gracek@gmail.com",
                address="Chibanja, Mzuzu",
                occupation="Shopkeeper"
            ),
            Guardian(
                id=uuid.uuid4(),
                first_name="Yohane",
                last_name="Jere",
                relationship_to_student="guardian",
                phone_number="+265 999 223 344",
                address="Masasa, Mzuzu",
                occupation="Farmer"
            ),
            Guardian(
                id=uuid.uuid4(),
                first_name="Tionge",
                last_name="Mvula",
                relationship_to_student="relative",
                phone_number="+265 997 334 455",
                email="tiongem@yahoo.com",
                address="Katoto, Mzuzu",
                occupation="Nurse"
            )
        ]
        db.add_all(guardians)
        db.commit()
        logger.info(f"Created {len(guardians)} guardians")

        # 6. Create Students with corrected status values
        logger.info("Creating students...")
        students = [
            Student(
                id=uuid.uuid4(),
                student_id="MLV-2023-001",
                first_name="Tawonga",
                last_name="Kanyinji",
                date_of_birth=date(2016, 5, 15),
                age=7,
                gender="female",
                class_id=classes[0].id,
                guardian_id=guardians[0].id,
                home_address="Chibanja, Mzuzu",
                distance_to_school=1.2,
                transport_method="walking",
                enrollment_date=date(2023, 1, 9),
                start_year=2023,
                last_year=None,
                status="active",  # Changed to lowercase
                special_learning=False,
                textbook_availability=True,
                class_repetitions=0,
                household_income="medium",
                created_at=datetime.now(timezone("Africa/Blantyre")),
                updated_at=datetime.now(timezone("Africa/Blantyre"))
            ),
            Student(
                id=uuid.uuid4(),
                student_id="MLV-2023-002",
                first_name="Lusungu",
                last_name="Jere",
                date_of_birth=date(2014, 8, 22),
                age=9,
                gender="male",
                class_id=classes[2].id,
                guardian_id=guardians[1].id,
                home_address="Masasa, Mzuzu",
                distance_to_school=3.5,
                transport_method="bicycle",
                enrollment_date=date(2020, 1, 12),
                start_year=2020,
                last_year=None,
                status="active",  # Changed to lowercase
                special_learning=False,
                textbook_availability=False,
                class_repetitions=1,
                household_income="low",
                created_at=datetime.now(timezone("Africa/Blantyre")),
                updated_at=datetime.now(timezone("Africa/Blantyre"))
            ),
            Student(
                id=uuid.uuid4(),
                student_id="MLV-2023-003",
                first_name="Mphatso",
                last_name="Mvula",
                date_of_birth=date(2015, 11, 3),
                age=8,
                gender="female",
                class_id=classes[0].id,
                guardian_id=guardians[2].id,
                home_address="Katoto, Mzuzu",
                distance_to_school=2.8,
                transport_method="public_transport",
                enrollment_date=date(2023, 1, 10),
                start_year=2023,
                last_year=None,
                status="active",  # Changed to lowercase
                special_learning=False,
                textbook_availability=True,
                class_repetitions=0,
                household_income="high",
                created_at=datetime.now(timezone("Africa/Blantyre")),
                updated_at=datetime.now(timezone("Africa/Blantyre"))
            )
        ]
        db.add_all(students)
        db.commit()
        logger.info(f"Created {len(students)} students")

        # 7. Create Subjects
        logger.info("Creating subjects...")
        subjects = [
            Subject(
                id=uuid.uuid4(),
                name="English",
                code="ENG",
                description="English language studies",
                type="core"
            ),
            Subject(
                id=uuid.uuid4(),
                name="Chichewa",
                code="CHI",
                description="Chichewa language studies",
                type="core"
            ),
            Subject(
                id=uuid.uuid4(),
                name="Mathematics",
                code="MATH",
                description="Mathematics studies",
                type="core"
            ),
            Subject(
                id=uuid.uuid4(),
                name="Science",
                code="SCI",
                description="Science and technology",
                type="core"
            ),
            Subject(
                id=uuid.uuid4(),
                name="Social Studies",
                code="SOC",
                description="Social and environmental studies",
                type="core"
            ),
            Subject(
                id=uuid.uuid4(),
                name="Physical Education",
                code="PE",
                description="Sports and physical activities",
                type="extracurricular"
            )
        ]
        db.add_all(subjects)
        db.commit()
        logger.info(f"Created {len(subjects)} subjects")

        # 8. Create Academic Terms with shortened term IDs
        logger.info("Creating academic terms...")
        academic_terms = [
            AcademicTerm(
                id=uuid.uuid4(),
                student_id=students[0].id,
                term_id="STD1-T1-2023",  # Shortened term ID
                term_type="term1",
                academic_year="2023-2024",
                standard=1,
                term_avg_score=72.5,
                present_days=88,
                absent_days=2
            ),
            AcademicTerm(
                id=uuid.uuid4(),
                student_id=students[1].id,
                term_id="STD5-T1-2023",  # Shortened term ID
                term_type="term1",
                academic_year="2023-2024",
                standard=5,
                term_avg_score=54.0,
                present_days=70,
                absent_days=20
            )
        ]
        db.add_all(academic_terms)
        db.commit()
        logger.info(f"Created {len(academic_terms)} academic terms")

        # 9. Create Subject Scores
        logger.info("Creating subject scores...")
        subject_scores = [
            SubjectScore(
                id=uuid.uuid4(),
                academic_term_id=academic_terms[0].id,
                subject_id=subjects[0].id,
                score=68,
                grade="C"
            ),
            SubjectScore(
                id=uuid.uuid4(),
                academic_term_id=academic_terms[0].id,
                subject_id=subjects[1].id,
                score=85,
                grade="A"
            ),
            SubjectScore(
                id=uuid.uuid4(),
                academic_term_id=academic_terms[0].id,
                subject_id=subjects[2].id,
                score=72,
                grade="B"
            ),
            SubjectScore(
                id=uuid.uuid4(),
                academic_term_id=academic_terms[1].id,
                subject_id=subjects[0].id,
                score=52,
                grade="D"
            ),
            SubjectScore(
                id=uuid.uuid4(),
                academic_term_id=academic_terms[1].id,
                subject_id=subjects[2].id,
                score=48,
                grade="E"
            )
        ]
        db.add_all(subject_scores)
        db.commit()
        logger.info(f"Created {len(subject_scores)} subject scores")

        # 10. Create Bullying Incidents
        logger.info("Creating bullying incidents...")
        bullying_incidents = [
            BullyingIncident(
                id=uuid.uuid4(),
                student_id=students[1].id,
                incident_date=date(2023, 5, 20),
                incident_type="verbal",
                description="Called 'dumb' repeatedly by classmates for failing exams",
                location="Classroom during break",
                severity_level="medium",
                reported_by_teacher_id=teachers[1].id,
                action_taken="Peer counseling and parent meeting",
                is_addressed=True
            ),
            BullyingIncident(
                id=uuid.uuid4(),
                student_id=students[0].id,
                incident_date=date(2023, 6, 10),
                incident_type="physical",
                description="Pushed down during lunch queue at school feeding program",
                location="School kitchen area",
                severity_level="high",
                reported_by_teacher_id=teachers[2].id,
                action_taken="Disciplinary committee meeting held",
                is_addressed=True
            )
        ]
        db.add_all(bullying_incidents)
        db.commit()
        logger.info(f"Created {len(bullying_incidents)} bullying incidents")

        logger.info("Successfully completed database seeding!")
        logger.info(f"Total records created: {sum([len(users), len(teachers), len(classes), len(teacher_classes), len(guardians), len(students), len(subjects), len(academic_terms), len(subject_scores), len(bullying_incidents)])}")

    except Exception as e:
        db.rollback()
        logger.error(f"Error during database seeding: {str(e)}", exc_info=True)
        raise
    finally:
        db.close()
        logger.info("Database connection closed")

if __name__ == "__main__":
    try:
        seed_database()
    except Exception as e:
        logger.critical(f"Fatal error in seeding process: {str(e)}", exc_info=True)
        exit(1)
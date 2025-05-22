from fastapi import FastAPI
from app.routes import auth, teacher, students

app = FastAPI(title="School Management System", description="A system for managing a school", version="1.0.0")

app.include_router(auth.router)
app.include_router(teacher.router)
app.include_router(students.router)






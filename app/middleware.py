from fastapi.middleware.cors import CORSMiddleware

origins = [
    "http://localhost",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:3000",
    "http://localhost:8080",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://school-dropout-risk-assessment.vercel.app/",
    "https://school-dropout-risk-assessment.vercel.app"
    "https://malimvenji-school-dropout-risk-asse.vercel.app/",
    "https://malimvenji-school-dropout-risk-asse.vercel.app/api/predict",
    "https://malimvenji-school-dropout-risk-asse.vercel.app/api/predict",
    "https://malimvenji-school-dropout-risk-asse.vercel.app",
    ]

def add_cors_middleware(app):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins, 
        allow_credentials=True,
        allow_methods=["*"],  
        allow_headers=["*"], 
    )

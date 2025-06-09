from fastapi.middleware.cors import CORSMiddleware

origins = [
    "http://localhost",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://127.0.0.1:3000",
    "https://tot-35es.onrender.com/",
    "https://tot-35es.onrender.com"
    "http://localhost:8080",
    "http://localhost:3000",
    "http://lihess.lighthouse.org.mw/",
    "http://lihess.lighthouse.org.mw",
    "http://192.168.3.44:3000",
    "http://192.168.3.44:8000",
    ]

def add_cors_middleware(app):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins, 
        allow_credentials=True,
        allow_methods=["*"],  
        allow_headers=["*"], 
    )

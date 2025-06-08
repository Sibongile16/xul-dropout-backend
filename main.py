from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from app.routes import auth

app = FastAPI(title="School Management System", description="A system for managing a school", version="1.0.0")

app.include_router(auth.router)


@app.get("/", include_in_schema=False)
async def root():
    """
    Root endpoint that redirects to the API documentation
    """
    return RedirectResponse(url="/docs")







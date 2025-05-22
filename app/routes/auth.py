from fastapi import APIRouter, Depends, HTTPException, status
from app.models.all_models import User
from app.database import get_db
from app.utils.security import hash_password, verify_password, create_access_token
from app.schemas.auth import LoginRequest, UserCreate, Token, UserResponse
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from app.utils.security import get_current_user 

router = APIRouter(prefix="/auth", tags=["auth"]    )

@router.post("/register", response_model=Token)
async def register(user: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.username == user.username).first()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")
        
    hashed_password = hash_password(user.password)
    new_user = User(username=user.username, email=user.email, hashed_password=hashed_password)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    access_token = create_access_token({"user_id": new_user.id})
    return Token(access_token=access_token)

@router.post("/login", response_model=Token)
async def login(login_request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == login_request.username).first()
    if not user or not verify_password(login_request.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    
    access_token = create_access_token({"user_id": user.id,
                                        "role": user.role})
    return Token(access_token=access_token)


@router.get("/me", response_model=UserResponse)
async def get_current_user(current_user: User = Depends(get_current_user)):
    return current_user





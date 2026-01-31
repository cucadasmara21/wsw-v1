"""
Endpoints de autenticación
SQLAlchemy 2.x compatible
"""
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from database import get_db
from models import User
from schemas import User as UserSchema, Token, UserCreate
from config import settings

router = APIRouter(tags=["auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)


def get_password_hash(password):
    return pwd_context.hash(password)


def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    # DEBUG bypass: GET requests in development mode
    is_dev = settings.DEBUG or settings.ENVIRONMENT == "development"
    if is_dev and request.method == "GET":
        # Return mock sovereign admin user for GET requests in DEBUG mode
        mock_user = User(
            id=1,
            username="sovereign",
            email="sovereign@local",
            hashed_password="",
            role="admin",
            is_active=True,
            full_name="Sovereign User"
        )
        return mock_user
    
    # Normal JWT authentication for POST/PUT/DELETE or non-DEBUG
    if token is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user


@router.post("/register", response_model=UserSchema)
async def register(user_data: UserCreate, db: Session = Depends(get_db)):
    """
    Register a new user account.
    
    Args:
        user_data (UserCreate): User registration data including username, email, password, full_name, and role.
        db (Session): Database session (dependency injected).
    
    Returns:
        UserSchema: The newly created user object.
    
    Raises:
        HTTPException: 400 if username or email already exists.
    """
    existing = db.query(User).filter(
        (User.username == user_data.username) | (User.email == user_data.email)
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="User already exists")

    hashed_password = get_password_hash(user_data.password)
    db_user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_password,
        full_name=user_data.full_name,
        role=user_data.role
    )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


@router.post("/token", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    Authenticate user and return JWT access token.
    
    Args:
        form_data (OAuth2PasswordRequestForm): Username and password from form submission.
        db (Session): Database session (dependency injected).
    
    Returns:
        Token: Object containing access_token and token_type ("bearer").
    
    Raises:
        HTTPException: 401 if username not found or password verification fails.
    """
    try:
        user = db.query(User).filter(User.username == form_data.username).first()
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user.last_login = datetime.utcnow()
    db.commit()

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=access_token_expires
    )

    return {
        "access_token": access_token,
        "token_type": "bearer"
    }


@router.get("/me", response_model=UserSchema)
async def read_users_me(current_user: User = Depends(get_current_user)):
    """Obtener usuario actual"""
    return current_user

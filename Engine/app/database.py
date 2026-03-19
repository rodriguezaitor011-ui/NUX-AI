"""
Database module — PostgreSQL con SQLAlchemy
Migrado desde JSON files a Supabase PostgreSQL
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict

from sqlalchemy import (
    create_engine, Column, Integer, String,
    Boolean, DateTime, Text, event
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.pool import StaticPool

from app.config import settings

logger = logging.getLogger(__name__)

# ============================================================
# ENGINE — detecta SQLite (local) vs PostgreSQL (producción)
# ============================================================

DATABASE_URL = settings.DATABASE_URL

# SQLite necesita configuración especial para async + threads
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    # PostgreSQL / Supabase
    # Supabase a veces devuelve postgres:// en vez de postgresql://
    # SQLAlchemy 2.x requiere postgresql://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,      # reconecta si la conexión cae
        pool_size=5,             # conexiones en pool
        max_overflow=10,         # conexiones extra bajo carga
        pool_recycle=300,        # recicla conexiones cada 5min
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ============================================================
# MODELOS
# ============================================================

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "hashed_password": self.hashed_password,
            "is_admin": self.is_admin,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)
    username = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    response = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.username,
            "message": self.message,
            "response": self.response,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


# ============================================================
# CREAR TABLAS AL ARRANCAR
# ============================================================

def init_db():
    """Crea las tablas si no existen. Se llama en el lifespan de FastAPI."""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Tablas PostgreSQL inicializadas correctamente")
    except Exception as e:
        logger.error(f"❌ Error inicializando base de datos: {e}")
        raise


# ============================================================
# DEPENDENCY — para inyectar sesión en rutas (opcional)
# ============================================================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================
# FUNCIONES DE USUARIOS
# (misma interfaz que antes para no romper routes.py)
# ============================================================

def get_user_by_email(email: str) -> Optional[Dict]:
    """Busca usuario por email. Devuelve dict o None."""
    with SessionLocal() as db:
        user = db.query(User).filter(User.email == email).first()
        return user.to_dict() if user else None


def get_user_by_username(username: str) -> Optional[Dict]:
    """Busca usuario por username. Devuelve dict o None."""
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == username).first()
        return user.to_dict() if user else None


def get_user_by_id(user_id: int) -> Optional[Dict]:
    """Busca usuario por ID. Devuelve dict o None."""
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == user_id).first()
        return user.to_dict() if user else None


def create_user(username: str, email: str, hashed_password: str) -> Dict:
    """Crea un nuevo usuario. Devuelve el dict del usuario creado."""
    with SessionLocal() as db:
        user = User(
            username=username,
            email=email,
            hashed_password=hashed_password,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"✅ Usuario creado: {username} ({email})")
        return user.to_dict()


def load_users() -> List[Dict]:
    """Devuelve todos los usuarios como lista de dicts."""
    with SessionLocal() as db:
        users = db.query(User).all()
        return [u.to_dict() for u in users]


# ============================================================
# FUNCIONES DE HISTORIAL DE CHAT
# ============================================================

def save_chat_message(username: str, message: str, response: str) -> Dict:
    """Guarda un mensaje de chat en la base de datos."""
    with SessionLocal() as db:
        # Intentar obtener user_id
        user = db.query(User).filter(User.username == username).first()
        user_id = user.id if user else None

        chat = ChatHistory(
            user_id=user_id,
            username=username,
            message=message,
            response=response,
        )
        db.add(chat)
        db.commit()
        db.refresh(chat)
        return chat.to_dict()


def load_chat_history() -> List[Dict]:
    """Devuelve todo el historial como lista de dicts."""
    with SessionLocal() as db:
        history = db.query(ChatHistory).order_by(
            ChatHistory.timestamp.desc()
        ).limit(1000).all()
        return [h.to_dict() for h in history]


def get_user_chat_history(username: str, limit: int = 50) -> List[Dict]:
    """Devuelve el historial de un usuario específico."""
    with SessionLocal() as db:
        history = (
            db.query(ChatHistory)
            .filter(ChatHistory.username == username)
            .order_by(ChatHistory.timestamp.desc())
            .limit(limit)
            .all()
        )
        return [h.to_dict() for h in history]
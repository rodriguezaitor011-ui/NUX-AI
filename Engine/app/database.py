"""
Database module — PostgreSQL con SQLAlchemy
Optimizado para Supabase y robustez en errores 500/401
"""

import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict
from contextlib import contextmanager

from sqlalchemy import (
    create_engine, Column, Integer, String,
    Boolean, DateTime, Text, Index, text
)
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool, QueuePool
from sqlalchemy.exc import SQLAlchemyError, OperationalError, IntegrityError

from app.config import settings

logger = logging.getLogger(__name__)

# ============================================================
# ENGINE — Configuración de conexión
# ============================================================

DATABASE_URL = settings.DATABASE_URL

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=settings.DEBUG,
    )
    logger.info("✅ Usando SQLite para desarrollo local")
else:
    # Soporte para Render/Heroku que usan postgres://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,  # Verifica conexión antes de usarla (evita 500s por timeout)
        pool_size=10,
        max_overflow=20,
        pool_recycle=1800,
        pool_timeout=30,
        echo=settings.DEBUG,
        poolclass=QueuePool,
    )
    logger.info("✅ Usando PostgreSQL con pool optimizado")

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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_login = Column(DateTime, nullable=True)

    __table_args__ = (
        Index('idx_user_created_at', 'created_at'),
    )

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "is_admin": self.is_admin,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    username = Column(String(50), nullable=False, index=True)
    message = Column(Text, nullable=False)
    response = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    session_id = Column(String(100), nullable=True, index=True)
    message_type = Column(String(20), default="chat")

    __table_args__ = (
        Index('idx_chat_user_timestamp', 'user_id', 'timestamp'),
        Index('idx_chat_username_timestamp', 'username', 'timestamp'),
        Index('idx_chat_session', 'session_id', 'timestamp'),
    )

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "username": self.username,
            "message": self.message[:500] + "..." if len(self.message) > 500 else self.message,
            "response": self.response[:500] + "..." if len(self.response) > 500 else self.response,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "session_id": self.session_id,
            "message_type": self.message_type,
        }


# ============================================================
# GESTIÓN DE SESIONES Y DB
# ============================================================

def init_db():
    """Inicializa tablas con reintentos para evitar fallos en el despliegue"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("✅ Tablas inicializadas correctamente")
            return
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"⚠️ Reintentando conexión DB ({attempt + 1}/{max_retries})...")
                time.sleep(3)
            else:
                logger.error(f"❌ Error crítico inicializando DB: {e}")
                raise

@contextmanager
def db_session():
    """Context manager seguro para operaciones atómicas"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Database session error: {e}")
        raise
    finally:
        db.close()


# ============================================================
# FUNCIONES DE USUARIOS (Corregidas para evitar 500s)
# ============================================================

def create_user(username: str, email: str, hashed_password: str) -> Optional[Dict]:
    try:
        with db_session() as db:
            # Verificación proactiva para evitar IntegrityError (Error 500)
            existing = db.query(User).filter((User.username == username) | (User.email == email)).first()
            if existing:
                return None # O podrías lanzar una excepción personalizada
            
            user = User(
                username=username,
                email=email,
                hashed_password=hashed_password,
            )
            db.add(user)
            db.flush() 
            db.refresh(user)
            return user.to_dict()
    except IntegrityError:
        logger.error(f"❌ Usuario o email ya existe: {username}")
        return None
    except Exception as e:
        logger.error(f"❌ Error inesperado en create_user: {e}")
        return None

def get_user_by_email(email: str) -> Optional[Dict]:
    try:
        with db_session() as db:
            user = db.query(User).filter(User.email == email).first()
            return user.to_dict() if user else None
    except Exception:
        return None

def get_user_by_username(username: str) -> Optional[Dict]:
    try:
        with db_session() as db:
            user = db.query(User).filter(User.username == username).first()
            return user.to_dict() if user else None
    except Exception:
        return None

# ============================================================
# ESTADÍSTICAS (Universal para SQLite/Postgres)
# ============================================================

def get_database_stats() -> Dict:
    try:
        with engine.connect() as conn:
            stats = {}
            # Conteo básico
            stats['user_count'] = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
            stats['chat_count'] = conn.execute(text("SELECT COUNT(*) FROM chat_history")).scalar()
            
            # Filtros temporales usando parámetros (Evita el error de INTERVAL en SQLite)
            h24 = datetime.now(timezone.utc) - timedelta(hours=24)
            d7 = datetime.now(timezone.utc) - timedelta(days=7)
            
            stats['chats_last_24h'] = conn.execute(
                text("SELECT COUNT(*) FROM chat_history WHERE timestamp > :limit"),
                {"limit": h24}
            ).scalar()
            
            stats['active_users_7d'] = conn.execute(
                text("SELECT COUNT(DISTINCT username) FROM chat_history WHERE timestamp > :limit"),
                {"limit": d7}
            ).scalar()
            
            return stats
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas: {e}")
        return {"error": str(e)}

# ============================================================
# HISTORIAL DE CHAT
# ============================================================

def save_chat_message(username: str, message: str, response: str, session_id: str = None, message_type: str = "chat") -> Optional[Dict]:
    try:
        with db_session() as db:
            user = db.query(User).filter(User.username == username).first()
            chat = ChatHistory(
                user_id=user.id if user else None,
                username=username,
                message=message,
                response=response,
                session_id=session_id,
                message_type=message_type,
            )
            db.add(chat)
            db.flush()
            db.refresh(chat)
            return chat.to_dict()
    except Exception as e:
        logger.error(f"Error guardando chat: {e}")
        return None
    
# ============================================================
# FUNCIONES ADICIONALES (Requeridas por routes.py)
# ============================================================

def update_user_last_login(user_id: int) -> bool:
    """Actualiza la fecha del último acceso del usuario"""
    try:
        with db_session() as db:
            from sqlalchemy import select
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user.last_login = datetime.now(timezone.utc)
                return True
        return False
    except Exception as e:
        logger.error(f"Error actualizando último login para ID {user_id}: {e}")
        return False

def get_user_by_id(user_id: int) -> Optional[Dict]:
    """Busca un usuario por su ID primario"""
    try:
        with db_session() as db:
            user = db.query(User).filter(User.id == user_id).first()
            return user.to_dict() if user else None
    except Exception as e:
        logger.error(f"Error buscando usuario por ID {user_id}: {e}")
        return None

def load_chat_history(limit: int = 1000, offset: int = 0) -> List[Dict]:
    """Carga el historial global de chats (para admin)"""
    try:
        with db_session() as db:
            history = db.query(ChatHistory).order_by(
                ChatHistory.timestamp.desc()
            ).offset(offset).limit(limit).all()
            return [h.to_dict() for h in history]
    except Exception as e:
        logger.error(f"Error cargando historial global: {e}")
        return []
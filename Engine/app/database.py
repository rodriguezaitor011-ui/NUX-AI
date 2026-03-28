"""
Database module — PostgreSQL con SQLAlchemy
Migrado desde JSON files a Supabase PostgreSQL
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict
from contextlib import contextmanager

from sqlalchemy import (
    create_engine, Column, Integer, String,
    Boolean, DateTime, Text, Index, event,
    text
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.pool import StaticPool, QueuePool
from sqlalchemy.exc import SQLAlchemyError, OperationalError

from app.config import settings

logger = logging.getLogger(__name__)

# ============================================================
# ENGINE — detecta SQLite (local) vs PostgreSQL (producción)
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
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
        logger.info("✅ URL de PostgreSQL normalizada")

    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
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

    # ✅ Solo índices estáticos — sin funciones no-immutable
    __table_args__ = (
        Index('idx_user_created_at', 'created_at'),
    )

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "hashed_password": self.hashed_password,
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

    # ✅ Solo índices estáticos — sin NOW() ni funciones dinámicas
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
# CREAR TABLAS AL ARRANCAR
# ============================================================

def init_db():
    """Crea las tablas si no existen. Se llama en el lifespan de FastAPI."""
    max_retries = 3
    retry_delay = 2

    for attempt in range(max_retries):
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("✅ Tablas de base de datos inicializadas correctamente")
            return

        except OperationalError as e:
            if attempt < max_retries - 1:
                logger.warning(
                    f"⚠️ Error de conexión (intento {attempt + 1}/{max_retries}): {e}"
                )
                import time
                time.sleep(retry_delay * (attempt + 1))
                continue
            else:
                logger.error(
                    f"❌ Error inicializando base de datos después de {max_retries} intentos: {e}"
                )
                raise
        except Exception as e:
            logger.error(f"❌ Error inicializando base de datos: {e}")
            raise


# ============================================================
# DEPENDENCY
# ============================================================

def get_db():
    db = SessionLocal()
    try:
        yield db
    except SQLAlchemyError as e:
        logger.error(f"Database error in session: {e}")
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def db_session():
    """Context manager con rollback automático en caso de error"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Database session error: {e}")
        raise
    finally:
        db.close()


# ============================================================
# FUNCIONES DE USUARIOS
# ============================================================

def get_user_by_email(email: str) -> Optional[Dict]:
    try:
        with db_session() as db:
            user = db.query(User).filter(User.email == email).first()
            return user.to_dict() if user else None
    except SQLAlchemyError as e:
        logger.error(f"Error buscando usuario por email {email}: {e}")
        return None


def get_user_by_username(username: str) -> Optional[Dict]:
    try:
        with db_session() as db:
            user = db.query(User).filter(User.username == username).first()
            return user.to_dict() if user else None
    except SQLAlchemyError as e:
        logger.error(f"Error buscando usuario por username {username}: {e}")
        return None


def get_user_by_id(user_id: int) -> Optional[Dict]:
    try:
        with db_session() as db:
            user = db.query(User).filter(User.id == user_id).first()
            return user.to_dict() if user else None
    except SQLAlchemyError as e:
        logger.error(f"Error buscando usuario por ID {user_id}: {e}")
        return None


def create_user(username: str, email: str, hashed_password: str) -> Optional[Dict]:
    try:
        with db_session() as db:
            user = User(
                username=username,
                email=email,
                hashed_password=hashed_password,
            )
            db.add(user)
            db.flush()
            db.refresh(user)
            logger.info(f"✅ Usuario creado: {username} ({email})")
            return user.to_dict()
    except SQLAlchemyError as e:
        logger.error(f"Error creando usuario {username}: {e}")
        return None


def update_user_last_login(user_id: int) -> bool:
    try:
        with db_session() as db:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                user.last_login = datetime.now(timezone.utc)
                db.add(user)
                return True
        return False
    except SQLAlchemyError as e:
        logger.error(f"Error actualizando último login: {e}")
        return False


def load_users(limit: int = 100, offset: int = 0) -> List[Dict]:
    try:
        with db_session() as db:
            users = db.query(User).order_by(
                User.created_at.desc()
            ).offset(offset).limit(limit).all()
            return [u.to_dict() for u in users]
    except SQLAlchemyError as e:
        logger.error(f"Error cargando usuarios: {e}")
        return []


# ============================================================
# FUNCIONES DE HISTORIAL DE CHAT
# ============================================================

def save_chat_message(
    username: str,
    message: str,
    response: str,
    session_id: Optional[str] = None,
    message_type: str = "chat"
) -> Optional[Dict]:
    try:
        with db_session() as db:
            user = db.query(User).filter(User.username == username).first()
            user_id = user.id if user else None

            chat = ChatHistory(
                user_id=user_id,
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
    except SQLAlchemyError as e:
        logger.error(f"Error guardando mensaje de chat para {username}: {e}")
        return None


def load_chat_history(limit: int = 1000, offset: int = 0) -> List[Dict]:
    try:
        with db_session() as db:
            history = db.query(ChatHistory).order_by(
                ChatHistory.timestamp.desc()
            ).offset(offset).limit(limit).all()
            return [h.to_dict() for h in history]
    except SQLAlchemyError as e:
        logger.error(f"Error cargando historial: {e}")
        return []


def get_user_chat_history(
    username: str,
    limit: int = 50,
    offset: int = 0
) -> List[Dict]:
    try:
        with db_session() as db:
            history = (
                db.query(ChatHistory)
                .filter(ChatHistory.username == username)
                .order_by(ChatHistory.timestamp.desc())
                .offset(offset)
                .limit(limit)
                .all()
            )
            return [h.to_dict() for h in history]
    except SQLAlchemyError as e:
        logger.error(f"Error cargando historial de {username}: {e}")
        return []


def get_recent_sessions(username: str, days: int = 7) -> List[str]:
    try:
        with db_session() as db:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            sessions = (
                db.query(ChatHistory.session_id)
                .filter(
                    ChatHistory.username == username,
                    ChatHistory.session_id.isnot(None),
                    ChatHistory.timestamp > cutoff
                )
                .distinct()
                .order_by(ChatHistory.timestamp.desc())
                .limit(20)
                .all()
            )
            return [s[0] for s in sessions if s[0]]
    except SQLAlchemyError as e:
        logger.error(f"Error obteniendo sesiones recientes: {e}")
        return []


def cleanup_old_chats(days: int = 90) -> int:
    try:
        with db_session() as db:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
            result = db.query(ChatHistory).filter(
                ChatHistory.timestamp < cutoff_date
            ).delete(synchronize_session=False)
            if result > 0:
                logger.info(f"🧹 Eliminados {result} chats antiguos")
            return result
    except SQLAlchemyError as e:
        logger.error(f"Error limpiando chats antiguos: {e}")
        return 0


def get_database_stats() -> Dict:
    try:
        with engine.connect() as conn:
            stats = {}
            result = conn.execute(text("SELECT COUNT(*) FROM users"))
            stats['user_count'] = result.scalar()
            result = conn.execute(text("SELECT COUNT(*) FROM chat_history"))
            stats['chat_count'] = result.scalar()
            result = conn.execute(text("""
                SELECT COUNT(*) FROM chat_history
                WHERE timestamp > NOW() - INTERVAL '24 hours'
            """))
            stats['chats_last_24h'] = result.scalar()
            result = conn.execute(text("""
                SELECT COUNT(DISTINCT username) FROM chat_history
                WHERE timestamp > NOW() - INTERVAL '7 days'
            """))
            stats['active_users_7d'] = result.scalar()
            return stats
    except Exception as e:
        logger.error(f"Error obteniendo estadísticas: {e}")
        return {}
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
    Boolean, DateTime, Text, Index, text, ForeignKey
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
            "hashed_password": self.hashed_password,
            "is_admin": self.is_admin,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }

    def to_safe_dict(self) -> Dict:
        """Dict sin datos sensibles, apto para respuestas API"""
        d = self.to_dict()
        d.pop("hashed_password", None)
        return d


class Notebook(Base):
    __tablename__ = "notebooks"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False)
    title = Column(String(255), nullable=False)
    emoji = Column(String(10), nullable=True, default="📓")
    color = Column(String(50), nullable=True, default="blue")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "emoji": self.emoji,
            "color": self.color,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

class NotebookDocument(Base):
    __tablename__ = "notebook_documents"

    id = Column(Integer, primary_key=True, index=True)
    notebook_id = Column(Integer, ForeignKey('notebooks.id', ondelete='CASCADE'), index=True, nullable=False)
    filename = Column(String(255), nullable=True)
    content = Column(Text, nullable=False)
    structure = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "notebook_id": self.notebook_id,
            "filename": self.filename,
            "content": self.content[:500] + "..." if self.content and len(self.content) > 500 else self.content,
            "structure": self.structure,
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
    notebook_id = Column(Integer, ForeignKey('notebooks.id', ondelete='CASCADE'), nullable=True, index=True)
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
            "notebook_id": self.notebook_id,
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
            # Intento manual de agregar la columna por si la tabla ya existía
            try:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE chat_history ADD COLUMN notebook_id INTEGER REFERENCES notebooks(id) ON DELETE CASCADE;"))
            except Exception:
                pass # Ya existe o el driver no lo permite así, lo ignoramos

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

def save_chat_message(username: str, message: str, response: str, session_id: str = None, notebook_id: int = None, message_type: str = "chat") -> Optional[Dict]:
    try:
        with db_session() as db:
            user = db.query(User).filter(User.username == username).first()
            chat = ChatHistory(
                user_id=user.id if user else None,
                username=username,
                message=message,
                response=response,
                session_id=session_id,
                notebook_id=notebook_id,
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


def get_user_chat_history(username: str, limit: int = 50, offset: int = 0) -> List[Dict]:
    """Historial de chats de un usuario específico"""
    try:
        with db_session() as db:
            history = db.query(ChatHistory).filter(
                ChatHistory.username == username
            ).order_by(
                ChatHistory.timestamp.desc()
            ).offset(offset).limit(limit).all()
            return [h.to_dict() for h in history]
    except Exception as e:
        logger.error(f"Error cargando historial de {username}: {e}")
        return []


def get_recent_sessions(username: str, days: int = 7) -> List[Dict]:
    """Sesiones recientes de un usuario (agrupadas por session_id)"""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        with db_session() as db:
            sessions = db.query(
                ChatHistory.session_id,
                ChatHistory.message_type,
                ChatHistory.timestamp
            ).filter(
                ChatHistory.username == username,
                ChatHistory.timestamp > cutoff,
                ChatHistory.session_id.isnot(None)
            ).order_by(
                ChatHistory.timestamp.desc()
            ).all()

            seen = {}
            for s in sessions:
                sid = s.session_id
                if sid and sid not in seen:
                    seen[sid] = {
                        "session_id": sid,
                        "message_type": s.message_type,
                        "last_activity": s.timestamp.isoformat() if s.timestamp else None,
                    }
            return list(seen.values())
    except Exception as e:
        logger.error(f"Error obteniendo sesiones de {username}: {e}")
        return []


# ============================================================
# FUNCIONES PARA ADMIN (SQL)
# ============================================================

def get_all_users_paginated(page: int = 1, limit: int = 20, search: str = None) -> Dict:
    """Devuelve usuarios paginados con conteo de chats"""
    try:
        with db_session() as db:
            query = db.query(User)
            if search:
                pattern = f"%{search}%"
                query = query.filter(
                    (User.username.ilike(pattern)) | (User.email.ilike(pattern))
                )
            total = query.count()
            offset = (page - 1) * limit
            users = query.order_by(User.created_at.desc()).offset(offset).limit(limit).all()

            users_data = []
            for u in users:
                chat_count = db.query(ChatHistory).filter(
                    ChatHistory.username == u.username
                ).count()
                last_chat = db.query(ChatHistory.timestamp).filter(
                    ChatHistory.username == u.username
                ).order_by(ChatHistory.timestamp.desc()).first()

                d = u.to_safe_dict()
                d["chat_count"] = chat_count
                d["last_activity"] = last_chat[0].isoformat() if last_chat and last_chat[0] else None
                users_data.append(d)

            return {
                "users": users_data,
                "total": total,
                "page": page,
                "pages": max(1, (total + limit - 1) // limit),
            }
    except Exception as e:
        logger.error(f"Error listando usuarios: {e}")
        return {"users": [], "total": 0, "page": 1, "pages": 1}


def get_activity_by_day(days: int = 7) -> List[Dict]:
    """Actividad de chats agrupada por día"""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        with db_session() as db:
            chats = db.query(ChatHistory).filter(
                ChatHistory.timestamp > cutoff
            ).all()

            activity_map: Dict[str, int] = {}
            for c in chats:
                if c.timestamp:
                    day_str = c.timestamp.strftime("%Y-%m-%d")
                    activity_map[day_str] = activity_map.get(day_str, 0) + 1

            result = []
            for i in range(days):
                date = (datetime.now(timezone.utc) - timedelta(days=days - i - 1)).strftime("%Y-%m-%d")
                result.append({"date": date, "count": activity_map.get(date, 0)})
            return result
    except Exception as e:
        logger.error(f"Error obteniendo actividad diaria: {e}")
        return []
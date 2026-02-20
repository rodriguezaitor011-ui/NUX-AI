"""
Database module - Simplified version using JSON files
NO SQLAlchemy required
"""

import json
import os
from datetime import datetime
from typing import Optional, List, Dict

# Directorio de datos
DATA_DIR = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.json")
CHAT_HISTORY_FILE = os.path.join(DATA_DIR, "chat_history.json")

# Crear directorio si no existe
os.makedirs(DATA_DIR, exist_ok=True)

# Inicializar archivos si no existen
if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, 'w') as f:
        json.dump([], f)

if not os.path.exists(CHAT_HISTORY_FILE):
    with open(CHAT_HISTORY_FILE, 'w') as f:
        json.dump([], f)


# Clases simuladas (para compatibilidad)
class User:
    """Simulated User class"""
    def __init__(self, id, username, email, hashed_password, created_at):
        self.id = id
        self.username = username
        self.email = email
        self.hashed_password = hashed_password
        self.created_at = created_at


class ChatHistory:
    """Simulated ChatHistory class"""
    def __init__(self, id, user_id, username, message, response, timestamp):
        self.id = id
        self.user_id = user_id
        self.username = username
        self.message = message
        self.response = response
        self.timestamp = timestamp


def get_db():
    """Simulated database session - returns None"""
    return None


def load_users() -> List[Dict]:
    """Load users from JSON"""
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError, OSError) as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error cargando usuarios: {e}")
        return []


def save_users(users: List[Dict]):
    """Save users to JSON con escritura atómica"""
    try:
        import tempfile
        import shutil
        
        temp_file = USERS_FILE + '.tmp'
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(users, f, indent=2, ensure_ascii=False)
        shutil.move(temp_file, USERS_FILE)
    except (IOError, OSError, json.JSONEncodeError) as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error guardando usuarios: {e}")
        raise


def load_chat_history() -> List[Dict]:
    """Load chat history from JSON"""
    try:
        with open(CHAT_HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError, OSError) as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error cargando historial: {e}")
        return []


def save_chat_history(history: List[Dict]):
    """Save chat history to JSON con escritura atómica"""
    try:
        import tempfile
        import shutil
        
        temp_file = CHAT_HISTORY_FILE + '.tmp'
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        shutil.move(temp_file, CHAT_HISTORY_FILE)
    except (IOError, OSError, json.JSONEncodeError) as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error guardando historial: {e}")
        raise


def get_user_by_username(username: str) -> Optional[Dict]:
    """Get user by username"""
    users = load_users()
    for user in users:
        if user.get('username') == username:
            return user
    return None


def get_user_by_email(email: str) -> Optional[Dict]:
    """Get user by email"""
    users = load_users()
    for user in users:
        if user.get('email') == email:
            return user
    return None


def create_user(username: str, email: str, hashed_password: str) -> Dict:
    """Create new user"""
    users = load_users()
    
    user = {
        'id': len(users) + 1,
        'username': username,
        'email': email,
        'hashed_password': hashed_password,
        'created_at': datetime.now().isoformat()
    }
    
    users.append(user)
    save_users(users)
    
    return user


def save_chat_message(username: str, message: str, response: str):
    """Save chat message"""
    history = load_chat_history()
    
    chat = {
        'id': len(history) + 1,
        'username': username,
        'message': message,
        'response': response,
        'timestamp': datetime.now().isoformat()
    }
    
    history.append(chat)
    save_chat_history(history)
    
    return chat

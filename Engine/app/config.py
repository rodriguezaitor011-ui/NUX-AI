import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Configuración centralizada de la aplicación"""

    # Groq (multi-modelo)
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    
    # DeepSeek (chat + flashcards)
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    
    SECRET_KEY: str = os.getenv("SECRET_KEY", "default-insecure-key")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///database/studia.db")
    
    # Parámetros de generación
    MAX_TOKENS: int = 2048
    TEMPERATURE: float = 0.7

    # Validación de inputs
    MAX_TEXT_LENGTH: int = int(os.getenv("MAX_TEXT_LENGTH", "500000"))
    MAX_INSTRUCTIONS_LENGTH: int = int(os.getenv("MAX_INSTRUCTIONS_LENGTH", "200"))

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))

    # App - ACTUALIZADO CON NUX IA
    APP_NAME: str = "NUX IA"
    COMPANY_NAME: str = "NXUS"
    ENGINE_VERSION: str = "NXUS o.0.1"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"

    @classmethod
    def validate(cls):
        """Valida que las API keys estén configuradas"""
        if not cls.GROQ_API_KEY:
            raise ValueError(
                "GROQ_API_KEY no está configurada en tu archivo .env\n"
                "Consigue tu key gratis en: https://console.groq.com/keys"
            )
        if not cls.DEEPSEEK_API_KEY:
            raise ValueError(
                "DEEPSEEK_API_KEY no está configurada en tu archivo .env\n"
                "Consigue tu key en: https://platform.deepseek.com/api_keys"
            )


settings = Settings()

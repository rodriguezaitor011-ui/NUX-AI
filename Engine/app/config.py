import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Configuración centralizada de la aplicación"""

    # Groq (multi-modelo)
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    
    # DeepSeek (chat + flashcards)
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")

    # OpenAI (OCR apuntes manuscritos - Vision)
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_OCR_MODEL: str = os.getenv("OPENAI_OCR_MODEL", "gpt-4o")
    # Límite tamaño imagen para OCR (bytes). Por defecto 10 MB.
    OCR_MAX_IMAGE_SIZE: int = int(os.getenv("OCR_MAX_IMAGE_SIZE", str(10 * 1024 * 1024)))
    # Tipos MIME permitidos para OCR
    OCR_ALLOWED_MIME_TYPES: tuple = ("image/jpeg", "image/png", "image/webp", "image/gif")

    SECRET_KEY: str = os.getenv("SECRET_KEY", "")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///database/studia.db")
    
    # Admin configuration
    ADMIN_EMAILS: list = os.getenv("ADMIN_EMAILS", "").split(",") if os.getenv("ADMIN_EMAILS") else []
    
    # CORS configuration
    CORS_ORIGINS: list = os.getenv("CORS_ORIGINS", "*").split(",") if os.getenv("CORS_ORIGINS") else ["*"]
    
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
        """Valida que las API keys y configuración crítica estén configuradas"""
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
        if not cls.SECRET_KEY or cls.SECRET_KEY == "default-insecure-key":
            raise ValueError(
                "SECRET_KEY no está configurada o usa el valor por defecto inseguro.\n"
                "Genera una clave segura con: python -c 'import secrets; print(secrets.token_urlsafe(32))'\n"
                "Y añádela a tu archivo .env como SECRET_KEY=..."
            )
        if cls.ENVIRONMENT == "production" and "*" in cls.CORS_ORIGINS:
            raise ValueError(
                "⚠️ ADVERTENCIA: CORS permite todos los orígenes en producción.\n"
                "Configura CORS_ORIGINS en .env con dominios específicos separados por comas."
            )

    @classmethod
    def validate_openai_ocr(cls) -> None:
        """Valida que OpenAI esté configurado para usar la feature OCR de apuntes."""
        if not cls.OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY no está configurada en tu archivo .env\n"
                "Consigue tu key en: https://platform.openai.com/api/keys"
            )


settings = Settings()

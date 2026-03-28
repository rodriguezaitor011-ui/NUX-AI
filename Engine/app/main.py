import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
import time

from app.config import settings
from app.routes import router, limiter

# Configurar logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ejecuta al inicio y cierre de la aplicación"""

    # ── Startup ──────────────────────────────────────────
    logger.info("Iniciando aplicación...")

    # 1. Validar configuración
    try:
        settings.validate()
        logger.info("✅ Configuración validada correctamente")
    except ValueError as e:
        logger.error(f"❌ Error de configuración: {e}")
        raise

    # 2. Inicializar base de datos
    try:
        from app.database import init_db
        init_db()
        logger.info("✅ Base de datos inicializada correctamente")
    except Exception as e:
        logger.error(f"❌ Error inicializando base de datos: {e}")
        # Sin raise — la app arranca aunque la DB falle

    yield

    # ── Shutdown ──────────────────────────────────────────
    logger.info("Cerrando aplicación...")


# ── Crear app ─────────────────────────────────────────────
app = FastAPI(
    title=settings.APP_NAME,
    description="Aplicación para resumir textos usando IA",
    version="2.0.0",
    lifespan=lifespan,
    redoc_url=None if settings.ENVIRONMENT == "production" else "/redoc",
    docs_url=None if settings.ENVIRONMENT == "production" else "/docs",
)

# Rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Compression middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORS
cors_origins = settings.CORS_ORIGINS if settings.CORS_ORIGINS != ["*"] else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Archivos estáticos
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Rutas principales
app.include_router(router)

# Rutas de admin
from app.admin_routes import router as admin_router
app.include_router(admin_router)

# ← user_routes ELIMINADO — causaba el 422 en la landing


# Security headers + request logging
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    start_time = time.time()
    request_id = request.headers.get("X-Request-ID") or str(int(time.time() * 1000))

    response = await call_next(request)

    # Headers de seguridad
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Request-ID"] = request_id

    if settings.ENVIRONMENT == "production":
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' "
            "https://cdn.jsdelivr.net https://unpkg.com "
            "https://pagead2.googlesyndication.com "
            "https://www.googletagmanager.com; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https:; "
            "font-src 'self' https://cdn.jsdelivr.net; "
            "connect-src 'self' https://api.groq.com "
            "https://api.deepseek.com https://api.openai.com;"
        )

    # Log request
    process_time = time.time() - start_time
    logger.info(
        f"Request: {request.method} {request.url.path} "
        f"Status: {response.status_code} "
        f"Time: {process_time:.3f}s "
        f"IP: {request.client.host if request.client else 'unknown'} "
        f"ID: {request_id}"
    )

    return response


@app.get("/health")
async def health_check():
    """Health check — verifica conexión a la DB"""
    db_status = "disconnected"
    db_error = None

    try:
        from app.database import SessionLocal, User
        with SessionLocal() as db:
            db.query(User).limit(1).all()
        db_status = "connected"
    except Exception as e:
        db_error = str(e)[:100]
        logger.error(f"Health check DB error: {e}")

    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "app": settings.APP_NAME,
        "version": "2.0.0",
        "database": db_status,
        "database_error": db_error if db_status != "connected" else None,
        "environment": settings.ENVIRONMENT,
        "timestamp": time.time(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
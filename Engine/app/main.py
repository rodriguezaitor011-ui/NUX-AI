import logging
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

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
    logger.info("🚀 Iniciando NUX IA v2.0...")

    try:
        settings.validate()
        logger.info("✅ Configuración validada")
    except ValueError as e:
        logger.error(f"❌ Error de configuración: {e}")
        raise

    try:
        from app.database import init_db
        init_db()
        logger.info("✅ Base de datos sincronizada")
    except Exception as e:
        logger.error(f"❌ Fallo al conectar con la DB: {e}")
        # Permitimos que arranque para poder ver el error en /health

    yield
    logger.info("🛑 Cerrando aplicación...")

app = FastAPI(
    title=settings.APP_NAME,
    version="2.0.0",
    lifespan=lifespan,
    docs_url=None if settings.ENVIRONMENT == "production" else "/docs",
    redoc_url=None if settings.ENVIRONMENT == "production" else "/redoc",
)

# Rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Gzip Compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORS — Configuración robusta
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Estáticos
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Inclusión de Routers
app.include_router(router)
from app.admin_routes import router as admin_router
app.include_router(admin_router, prefix="/admin", tags=["admin"])

# Middleware de Seguridad y Logs corregido
@app.middleware("http")
async def security_and_logging_middleware(request: Request, call_next):
    start_time = time.time()
    
    # Ejecutar la petición
    try:
        response: Response = await call_next(request)
    except Exception as e:
        logger.error(f"🔥 Error no controlado en middleware: {e}")
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})

    # Headers de Seguridad Estándar
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"

    # Corregir CSP para permitir Supabase y APIs externas
    if settings.ENVIRONMENT == "production":
        # Extraer el dominio de la DB para la CSP (ej: supabase.co)
        db_domain = "*.supabase.co" 
        
        csp_rules = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://unpkg.com",
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com",
            "font-src 'self' data: https://cdn.jsdelivr.net https://fonts.gstatic.com",
            "img-src 'self' data: https:",
            f"connect-src 'self' https://api.groq.com https://api.deepseek.com https://api.openai.com {db_domain} *.onrender.com",
            "frame-ancestors 'none'"
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_rules)

    # Logging de la petición
    process_time = time.time() - start_time
    logger.info(
        f"Method: {request.method} | Path: {request.url.path} | "
        f"Status: {response.status_code} | Time: {process_time:.3f}s"
    )

    return response

@app.get("/health")
async def health_check():
    """Verifica si la app y la DB están vivas"""
    db_alive = False
    try:
        from app.database import SessionLocal, text
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            db_alive = True
    except Exception as e:
        logger.error(f"Healthcheck failed: {e}")

    return {
        "status": "online" if db_alive else "degraded",
        "database": "connected" if db_alive else "error",
        "environment": settings.ENVIRONMENT
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
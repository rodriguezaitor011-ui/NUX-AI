import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
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
    # Startup
    logger.info("Iniciando aplicación...")
    try:
        settings.validate()
        logger.info("✅ Configuración validada correctamente")
    except ValueError as e:
        logger.error(f"❌ Error de configuración: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Cerrando aplicación...")


# Crear app
app = FastAPI(
    title=settings.APP_NAME,
    description="Aplicación para resumir textos usando IA",
    version="2.0.0",
    lifespan=lifespan
)

# Rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS (configurar según tus necesidades)
cors_origins = settings.CORS_ORIGINS if settings.CORS_ORIGINS != ["*"] else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Montar archivos estáticos
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Incluir rutas principales
app.include_router(router)

# Incluir rutas de admin
from app.admin_routes import router as admin_router
app.include_router(admin_router)


@app.get("/health")
async def health_check():
    """Endpoint de health check"""
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": "2.0.0"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )

#!/usr/bin/env python3
"""
Script para ejecutar la aplicación fácilmente
"""
import uvicorn
from app.config import settings

if __name__ == "__main__":
    print(f"""
╔══════════════════════════════════════════╗
║        🚀 NUX IA - v2.0.0               ║
╚══════════════════════════════════════════╝

📍 Servidor: http://localhost:8000
🔧 Modo: {'DEBUG' if settings.DEBUG else 'PRODUCTION'}
⚡ Recarga automática: {'Activada' if settings.DEBUG else 'Desactivada'}

Presiona Ctrl+C para detener el servidor
    """)
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level="info"
    )

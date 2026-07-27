#!/usr/bin/env python3
# ============================================================
# main.py — Servidor Principal do Future Lab Control Center (FastAPI)
# ============================================================
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.settings_routes import router as settings_router
from backend.api.health_routes import router as health_router

app = FastAPI(
    title="Future Lab Control Center API",
    description="API de Gerenciamento e Controle Unificado da Célula (MyCobot 280 + TurtleBot 4)",
    version="1.0.0",
)

# Permite conexões do frontend web
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registra os roteadores de API
app.include_router(settings_router)
app.include_router(health_router)

@app.get("/")
def read_root():
    return {
        "status": "online",
        "system": "Future Lab Control Center API",
        "version": "1.0.0",
        "endpoints": [
            "/api/v1/health",
            "/api/v1/settings"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    from backend.config.settings import get_settings
    settings = get_settings()
    uvicorn.run("main:app", host="0.0.0.0", port=settings.BACKEND_PORT, reload=True)

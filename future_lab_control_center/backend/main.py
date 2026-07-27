#!/usr/bin/env python3
# ============================================================
# main.py — Servidor Principal do Future Lab Control Center (FastAPI)
# ============================================================
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

@app.get("/")
def read_root():
    return {
        "status": "online",
        "system": "Future Lab Control Center API",
        "version": "1.0.0"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

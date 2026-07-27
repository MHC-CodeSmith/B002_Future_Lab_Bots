#!/bin/bash
# ============================================================
# LAUNCH_GUI.sh — Script de 1-Clique do Future Lab Control Center
#
# Sobe os contêineres Docker do Backend e Frontend em 1 clique
# ============================================================
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [ ! -f .env ]; then
    echo "[setup] Arquivo .env não encontrado. Gerando a partir do .env.example..."
    cp .env.example .env
fi

echo "=================================================="
echo "      INICIANDO FUTURE LAB CONTROL CENTER (DOCKER) "
echo "=================================================="

docker compose up --build -d

echo ""
echo "✓ Aplicação iniciada com sucesso via Docker Compose!"
echo "👉 Frontend (Dashboard): http://localhost:3000"
echo "👉 Backend (API REST):   http://localhost:8000"
echo "=================================================="

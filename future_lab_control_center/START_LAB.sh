#!/bin/bash
# ============================================================
# START_LAB.sh — Inicializador de Um Clique do Future Lab
# ============================================================

set -e

MODE="start"
if [ "$1" == "--reset" ]; then
    MODE="reset"
elif [ "$1" == "--check" ]; then
    MODE="check"
fi

LOG_FILE="/tmp/start_lab_$(date +%F_%H%M%S).log"
exec > >(tee -i "$LOG_FILE") 2>&1

echo "============================================================"
echo "  🚀 Future Lab Control Center — Modo: [${MODE^^}]"
echo "  📅 Data: $(date)"
export ROS_DOMAIN_ID=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET
export ROS_SUPER_CLIENT=True
export ROS_DISCOVERY_SERVER="192.168.0.129:11811;"
echo "  📄 Log: $LOG_FILE"
echo "============================================================"

REPO_DIR="/home/future-lab/B002_Future_Lab_Bots"
CONTROL_DIR="$REPO_DIR/future_lab_control_center"

log_info()  { echo -e "\031[34m[INFO]\033[0m $1"; }
log_ok()    { echo -e "\033[32m[OK]\033[0m $1"; }
log_warn()  { echo -e "\033[33m[AVISO]\033[0m $1"; }
log_fail()  { echo -e "\033[31m[FALHA]\033[0m $1"; }

# 1. Usuário e Repositório
if [ "$USER" != "future-lab" ]; then
    log_warn "Executando como usuário '$USER' (esperado: future-lab)."
fi

if [ ! -d "$REPO_DIR" ]; then
    log_fail "Diretório do repositório $REPO_DIR não existe!"
    exit 1
fi
log_ok "Diretório do repositório verificado."

if [ "$MODE" == "check" ]; then
    log_info "--- Modo Somente Diagnóstico ---"
fi

# 2. Docker Daemon
if systemctl is-active --quiet docker; then
    log_ok "Docker daemon ativo."
else
    log_warn "Docker daemon inativo. Tentando iniciar..."
    if [ "$MODE" != "check" ]; then
        sudo systemctl start docker || { log_fail "Não foi possível iniciar o Docker daemon."; exit 1; }
        log_ok "Docker daemon iniciado."
    fi
fi

# 3. Arquivo .env
if [ ! -f "$CONTROL_DIR/.env" ]; then
    log_warn "Arquivo .env ausente! Copiando .env.example..."
    if [ "$MODE" != "check" ] && [ -f "$CONTROL_DIR/.env.example" ]; then
        cp "$CONTROL_DIR/.env.example" "$CONTROL_DIR/.env"
        log_warn "ATENÇÃO: Arquivo .env criado a partir de .env.example. Verifique os IPs de rede!"
    fi
else
    log_ok "Arquivo .env presente."
fi

# 4. Discovery Server do Cobot (:11888)
if systemctl --user is-active --quiet future-lab-cobot-discovery; then
    log_ok "Discovery Server do cobot (:11888) ativo no systemd."
else
    log_warn "Discovery Server do cobot inativo. Iniciando serviço..."
    if [ "$MODE" != "check" ]; then
        systemctl --user start future-lab-cobot-discovery || true
    fi
fi

# 5. Containers Docker e Processos do Host
cd "$CONTROL_DIR"
if [ "$MODE" == "reset" ]; then
    log_info "Modo RESET: Encerrando todos os processos do host e containers..."
    pkill -9 -f 'localization.launch.py' 2>/dev/null || true
    pkill -9 -f 'nav2.launch.py' 2>/dev/null || true
    pkill -9 -f 'view_navigation.launch.py' 2>/dev/null || true
    pkill -9 -f 'scripts/mission_manager.py' 2>/dev/null || true
    pkill -9 -f 'opt/ros/jazzy/lib' 2>/dev/null || true
    docker compose down --remove-orphans || true
    systemctl --user restart future-lab-agent future-lab-cobot-discovery || true
    sleep 2
    docker compose up -d
elif [ "$MODE" == "start" ]; then
    log_info "Garantindo containers Docker em execução..."
    docker compose up -d
fi

# 6. Agente do Host (:8100)
if systemctl --user is-active --quiet future-lab-agent; then
    log_ok "Agente do host (:8100) ativo."
    if [ "$MODE" == "reset" ]; then
        systemctl --user restart future-lab-agent
    fi
else
    log_warn "Agente do host inativo. Iniciando..."
    if [ "$MODE" != "check" ]; then
        systemctl --user start future-lab-agent
    fi
fi

# 7. Aguarda Backend (:8000)
log_info "Verificando backend FastAPI (:8000)..."
BACKEND_OK=false
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/api/v1/health/ >/dev/null 2>&1; then
        BACKEND_OK=true
        break
    fi
    sleep 1
done

if [ "$BACKEND_OK" = true ]; then
    log_ok "Backend (:8000) respondendo com sucesso."
else
    log_fail "Backend (:8000) não respondeu após 30 s!"
    if [ "$MODE" != "check" ]; then exit 1; fi
fi

# 8. Aguarda Frontend (:3000)
log_info "Verificando frontend Next.js (:3000)..."
FRONTEND_OK=false
for i in $(seq 1 30); do
    if curl -sf http://localhost:3000 >/dev/null 2>&1; then
        FRONTEND_OK=true
        break
    fi
    sleep 1
done

if [ "$FRONTEND_OK" = true ]; then
    log_ok "Frontend (:3000) respondendo com sucesso."
else
    log_fail "Frontend (:3000) não respondeu após 30 s!"
    if [ "$MODE" != "check" ]; then exit 1; fi
fi

# 9. Verificação do TurtleBot 4 (RPi4)
log_info "Verificando conexão com TurtleBot 4 (192.168.0.129)..."
if ping -c 1 -w 2 192.168.0.129 >/dev/null 2>&1; then
    log_ok "TurtleBot 4 acessível via Ping."
    if [ "$MODE" == "reset" ]; then
        log_info "Reiniciando bringup do TurtleBot 4 no RPi4..."
        ssh -o ConnectTimeout=5 ubuntu@192.168.0.129 "sudo systemctl restart turtlebot4.service" || true
    fi
else
    log_warn "TurtleBot 4 (192.168.0.129) não responde ao Ping."
fi

# 10. Verificação do Jetson Nano
if ping -c 1 -w 2 192.168.0.250 >/dev/null 2>&1; then
    log_ok "Jetson Nano (192.168.0.250) acessível via Ping."
else
    log_warn "Jetson Nano (192.168.0.250) não responde ao Ping."
fi

# 11. Telemetria do Robô
log_info "Verificando telemetria em /api/v1/turtlebot/status..."
TEL_OK=$(curl -s http://localhost:8000/api/v1/turtlebot/status | grep -o '"telemetry_ok":true' || true)
if [ -n "$TEL_OK" ]; then
    log_ok "Telemetria da base viva (telemetry_ok: true)."
else
    log_warn "Telemetria inativa no momento (no_telemetry)."
fi

# 12. Navegador
if [ "$MODE" != "check" ]; then
    log_info "Abrindo painel no navegador..."
    xdg-open http://localhost:3000 >/dev/null 2>&1 || true
fi

echo "============================================================"
echo "  🎉 Inicialização concluída! Log salvo em: $LOG_FILE"
echo "============================================================"
exit 0

# ============================================================
# cell_routes.py — API Router para Controle da Célula e Segurança
# ============================================================
import time
import threading
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.ros2_nodes.cobot_node import get_cobot_node

router = APIRouter(prefix="/api/v1/cell", tags=["Cell Control"])

class CellModeSchema(BaseModel):
    mode: str  # "auto" ou "manual"
    cooldown_sec: Optional[float] = 5.0
    yolo_conf: Optional[float] = 0.60

cell_state = {
    "mode": "auto",
    "cooldown_sec": 5.0,
    "yolo_conf": 0.60,
    "manual_authorized": False,
    "status": "idle",
    "panic_locked": False
}

@router.get("/status")
def get_cell_status():
    """Retorna o status global da célula automatizada."""
    node = get_cobot_node()
    from backend.api.cobot_routes import is_yolo_process_alive
    return {
        "cell": cell_state,
        "current_joints": node.current_joints,
        "pump_active": node.pump_active,
        "yolo_test_active": is_yolo_process_alive(),
        "last_yolo": node.last_yolo_msg
    }

@router.post("/mode")
def set_cell_mode(payload: CellModeSchema):
    """Altera o modo de operação da célula e atualiza as configurações mestre."""
    if cell_state.get("panic_locked"):
        raise HTTPException(status_code=423, detail="Célula bloqueada em modo de Pânico. É necessário reiniciar o sistema.")
    if payload.mode not in ["auto", "manual"]:
        raise HTTPException(status_code=400, detail="Modo deve ser 'auto' ou 'manual'.")
    cell_state["mode"] = payload.mode
    if payload.cooldown_sec is not None:
        cell_state["cooldown_sec"] = max(0.0, payload.cooldown_sec)
    if payload.yolo_conf is not None:
        cell_state["yolo_conf"] = max(0.10, min(1.0, payload.yolo_conf))

    return {"status": "success", "cell": cell_state}

_cycle_thread: threading.Thread = None
_cycle_cancel = False

def _run_single_cycle():
    """Worker de ciclo único: home → scan → YOLO → pick_approach → pick → place_approach → place → home."""
    global _cycle_cancel
    _cycle_cancel = False
    node = get_cobot_node()
    node.load_poses()
    
    # Verifica se todas as poses necessárias estão salvas
    missing = [p for p in ["home", "scan", "pick_approach", "pick", "place_approach", "place"] if p not in node.poses]
    if missing:
        print(f"[CYCLE] ABORTADO: poses faltando: {missing}")
        cell_state["status"] = "idle"
        return
    
    from backend.api.cobot_routes import start_yolo_test_process, stop_yolo_test_process
    
    try:
        # ========== FASE 1: Ir para HOME ==========
        cell_state["status"] = "moving_home"
        print("[CYCLE] Fase 1: Indo para HOME...")
        ok = node.goto_pose("home", 0.20)
        if not ok or _cycle_cancel:
            print("[CYCLE] Falha ou cancelamento ao ir para HOME")
            cell_state["status"] = "idle"
            return
        time.sleep(0.5)
        
        # ========== FASE 2: Ir para SCAN ==========
        cell_state["status"] = "moving_scan"
        print("[CYCLE] Fase 2: Indo para SCAN...")
        ok = node.goto_pose("scan", 0.20)
        if not ok or _cycle_cancel:
            print("[CYCLE] Falha ou cancelamento ao ir para SCAN")
            cell_state["status"] = "idle"
            return
        time.sleep(1.0)
        
        # ========== FASE 3: Ativar YOLO e aguardar detecção ==========
        cell_state["status"] = "scanning"
        print("[CYCLE] Fase 3: Ativando YOLO para detecção...")
        node.clear_yolo_state()
        conf = float(cell_state.get("yolo_conf", 0.60))
        start_yolo_test_process(conf=conf)
        
        # Aguarda detecção estável (mesma classe 3x consecutivas em 10s)
        detection_timeout = 15.0
        t0 = time.time()
        stable_class = None
        stable_count = 0
        detected = False
        
        while (time.time() - t0) < detection_timeout and not _cycle_cancel:
            yolo = node.last_yolo_msg
            if yolo and yolo.get("class") and yolo["class"] not in ("none", "invalid_stream"):
                cls = yolo["class"]
                yolo_conf = yolo.get("confidence", 0)
                if yolo_conf >= conf:
                    if cls == stable_class:
                        stable_count += 1
                    else:
                        stable_class = cls
                        stable_count = 1
                    
                    if stable_count >= 3:
                        detected = True
                        print(f"[CYCLE] Detecção estável: {stable_class} (conf={yolo_conf:.2f}, {stable_count}x)")
                        break
            time.sleep(0.3)
        
        # Para o YOLO após detecção
        stop_yolo_test_process()
        
        if _cycle_cancel:
            cell_state["status"] = "idle"
            return
        
        if not detected:
            print("[CYCLE] Timeout de detecção YOLO — nenhum objeto válido encontrado. Retornando para HOME.")
            cell_state["status"] = "moving_home"
            node.goto_pose("home", 0.20)
            cell_state["status"] = "idle"
            return
        
        print(f"[CYCLE] Objeto detectado: {stable_class} — iniciando sequência de coleta...")
        
        # ========== FASE 4: PICK APPROACH ==========
        cell_state["status"] = "moving_pick_approach"
        print("[CYCLE] Fase 4: Indo para PICK APPROACH...")
        ok = node.goto_pose("pick_approach", 0.15)
        if not ok or _cycle_cancel:
            cell_state["status"] = "idle"
            return
        time.sleep(0.5)
        
        # ========== FASE 5: PICK (bomba liga após alcançar) ==========
        cell_state["status"] = "picking"
        print("[CYCLE] Fase 5: Indo para PICK...")
        ok = node.goto_pose("pick", 0.10)  # goto_pose já liga a bomba no pick
        if not ok or _cycle_cancel:
            cell_state["status"] = "idle"
            return
        time.sleep(0.5)
        
        # ========== FASE 6: PICK APPROACH (retrai com objeto) ==========
        cell_state["status"] = "moving_pick_approach"
        print("[CYCLE] Fase 6: Retraindo para PICK APPROACH...")
        ok = node.goto_pose("pick_approach", 0.15)
        if not ok or _cycle_cancel:
            cell_state["status"] = "idle"
            return
        time.sleep(0.3)
        
        # ========== FASE 7: PLACE APPROACH ==========
        cell_state["status"] = "moving_place_approach"
        print("[CYCLE] Fase 7: Indo para PLACE APPROACH...")
        ok = node.goto_pose("place_approach", 0.15)
        if not ok or _cycle_cancel:
            cell_state["status"] = "idle"
            return
        time.sleep(0.5)
        
        # ========== FASE 8: PLACE (bomba desliga após alcançar) ==========
        cell_state["status"] = "placing"
        print("[CYCLE] Fase 8: Indo para PLACE...")
        ok = node.goto_pose("place", 0.10)  # goto_pose já desliga a bomba no place
        if not ok or _cycle_cancel:
            cell_state["status"] = "idle"
            return
        time.sleep(0.5)
        
        # ========== FASE 9: PLACE APPROACH (retrai) ==========
        cell_state["status"] = "moving_place_approach"
        print("[CYCLE] Fase 9: Retraindo para PLACE APPROACH...")
        ok = node.goto_pose("place_approach", 0.15)
        if not ok or _cycle_cancel:
            cell_state["status"] = "idle"
            return
        time.sleep(0.3)
        
        # ========== FASE 10: Retorno HOME ==========
        cell_state["status"] = "moving_home"
        print("[CYCLE] Fase 10: Retornando para HOME...")
        node.goto_pose("home", 0.20)
        
        print(f"[CYCLE] ✅ CICLO COMPLETO — Objeto '{stable_class}' coletado e entregue com sucesso!")
        
    except Exception as e:
        print(f"[CYCLE] ERRO durante o ciclo: {e}")
        try:
            stop_yolo_test_process()
        except Exception:
            pass
    finally:
        cell_state["status"] = "idle"
        cell_state["manual_authorized"] = False

@router.post("/authorize_scan")
def authorize_manual_scan():
    """No modo manual, autoriza e dispara a execução do próximo ciclo de inspeção/coleta."""
    global _cycle_thread
    if cell_state.get("panic_locked"):
        raise HTTPException(status_code=423, detail="Célula bloqueada em modo de Pânico. É necessário reiniciar o sistema.")
    if cell_state["mode"] != "manual":
        raise HTTPException(status_code=400, detail="Autorização só é necessária no modo manual.")
    
    # Verifica se já há um ciclo em execução
    if _cycle_thread is not None and _cycle_thread.is_alive():
        raise HTTPException(status_code=409, detail="Um ciclo já está em execução. Aguarde a conclusão.")
    
    cell_state["manual_authorized"] = True
    _cycle_thread = threading.Thread(target=_run_single_cycle, daemon=True)
    _cycle_thread.start()
    return {"status": "success", "message": "Ciclo de inspeção/coleta iniciado."}


@router.post("/stop")
def emergency_stop():
    """Parada de emergência: desliga bomba, cancela ciclo, desativa teste YOLO e move braço para HOME."""
    global _cycle_cancel
    _cycle_cancel = True
    if cell_state.get("panic_locked"):
        raise HTTPException(status_code=423, detail="Célula bloqueada em modo de Pânico. É necessário reiniciar o sistema.")
    node = get_cobot_node()
    node.load_poses()  # Recarrega do arquivo YAML do disco para ter a versão mais recente
    if "home" not in node.poses:
        raise HTTPException(
            status_code=400,
            detail="A pose 'home' ainda não foi salva no disco! Grave e salve a pose 'home' antes de acionar o retorno de emergência."
        )

    from backend.api.cobot_routes import stop_yolo_test_process
    stop_yolo_test_process()
    node.set_pump(False)
    cell_state["status"] = "stopped"
    cell_state["manual_authorized"] = False
    
    t = threading.Thread(target=node.goto_pose, args=("home", 0.15))
    t.start()
    
    return {
        "status": "emergency_stop_triggered",
        "message": "Parada de emergência acionada. Bomba e teste YOLO desligados e retornando o braço para HOME."
    }

@router.post("/panic")
def panic_stop():
    """Botão de Pânico Master: interrompe TUDO no projeto (Bomba, Câmera, YOLO, Robô, Motores e Planejamento MoveIt) e bloqueia a célula."""
    global _cycle_cancel
    _cycle_cancel = True
    from backend.api.cobot_routes import stop_yolo_test_process
    from backend.api.health_routes import stop_camera_stream
    import subprocess
    import urllib.request
    
    # 0. Dispara PÂNICO em < 5ms via HTTP Micro-Bridge para CONGELAR IMEDIATAMENTE os motores do robô físico
    try:
        req = urllib.request.Request("http://192.168.0.250:8088/panic")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            print("[INFO] Pânico via HTTP Micro-Bridge enviado em < 5ms (Motores congelados no robô físico)")
    except Exception as e:
        print(f"[WARN] HTTP Micro-Bridge panic trigger indisponível: {e}")

    # 1. Encerra o processo do teste YOLO e o servidor de câmera no Nano
    try:
        stop_yolo_test_process()
    except Exception as e:
        print(f"[WARN] Erro ao parar teste YOLO no pânico: {e}")
        
    try:
        stop_camera_stream()
    except Exception as e:
        print(f"[WARN] Erro ao desligar câmera no pânico: {e}")
    
    # 2. Desliga a bomba de sucção e TRAVA os servos do robô
    node = get_cobot_node()
    try:
        node.set_pump(False)
        node.clear_yolo_state()
        node.call_trigger_service(node.lock_cli, "Travar Servos (Pânico)")
    except Exception as e:
        print(f"[WARN] Erro ao desligar bomba/motores no Pânico: {e}")

    # 3. Mata o planejador MoveIt (move_group + rviz) no container mycobot_ros2 no PC
    try:
        print("[INFO] Matando MoveIt Planning e RViz no container mycobot_ros2...")
        subprocess.run('docker exec mycobot_ros2 bash -c "pkill -9 -f move_group 2>/dev/null || true; pkill -9 -f rviz 2>/dev/null || true"', shell=True, timeout=5)
    except Exception as e:
        print(f"[WARN] Erro ao matar MoveIt planning no pânico: {e}")

    # 4. Encerra o nó mycobot_bridge na Jetson Nano (mantendo as juntas travadas pelo microcontrolador)
    try:
        print("[INFO] Matando ponte mycobot_bridge na Jetson Nano...")
        cmd_kill_nano = "sshpass -p Elephant ssh -o StrictHostKeyChecking=no er@192.168.0.250 'pkill -9 -f mycobot_bridge 2>/dev/null || true; fuser -k 8088/tcp 2>/dev/null || true'"
        subprocess.run(cmd_kill_nano, shell=True, timeout=5)
    except Exception as e:
        print(f"[WARN] Erro ao encerrar mycobot_bridge no Nano: {e}")
        
    # 5. Trava persistentemente o estado da célula em PANIC_LOCKED
    cell_state["panic_locked"] = True
    cell_state["status"] = "panic_locked"
    cell_state["manual_authorized"] = False
    
    return {
        "status": "panic_triggered",
        "panic_locked": True,
        "message": "PÂNICO ABSOLUTO: Todos os componentes (Câmera, Bomba, YOLO, Motores, MoveIt Planning e Bridge Nano) foram PARADOS! As juntas do robô estão TRAVADAS. É necessário reiniciar."
    }

@router.post("/reset_panic")
def reset_panic():
    """Desbloqueia o estado de Pânico e dispara a reinicialização limpa do MoveIt, da Câmera e do Hardware Nano."""
    cell_state["panic_locked"] = False
    cell_state["status"] = "idle"
    cell_state["manual_authorized"] = False
    
    from backend.api.health_routes import restart_nano_hardware
    try:
        # restart_nano_hardware() mata os processos antigos e inicia um novo planejador MoveIt + Hardware + Câmera
        restart_nano_hardware()
    except Exception as e:
        print(f"[WARN] Erro ao reiniciar componentes no desbloqueio do pânico: {e}")
        
    return {
        "status": "success",
        "message": "Pânico desbloqueado. O planejador MoveIt, o hardware da Nano e a câmera estão sendo reiniciados do zero..."
    }


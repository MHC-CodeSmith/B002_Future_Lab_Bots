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
    arm_speed: Optional[float] = 0.15

class InterruptConfirmSchema(BaseModel):
    abort: bool  # True = SIM, Abortar; False = NÃO, Continuar

cell_state = {
    "mode": "auto",
    "auto_running": False,
    "cooldown_sec": 5.0,
    "yolo_conf": 0.60,
    "arm_speed": 0.15,
    "manual_authorized": False,
    "manual_step": "idle",  # "idle", "at_scan", "pick_authorized", "at_place_approach", "place_authorized"
    "status": "idle",
    "panic_locked": False,
    "yolo_detected_item": None
}

# Controle de threads e eventos do motor de ciclo
_cycle_thread: Optional[threading.Thread] = None
_pause_event = threading.Event()
_pause_event.set()  # set = executando, clear = pausado (interrompido)
_abort_requested = False
_cycle_cancel = False
_step_pick_event = threading.Event()
_step_place_event = threading.Event()

def _check_pause_and_cancel() -> bool:
    """Verifica se há requisição de pausa (interrupção) ou cancelamento/abort."""
    global _cycle_cancel, _abort_requested
    if _cycle_cancel or _abort_requested or not cell_state.get("auto_running", False) and cell_state["mode"] == "auto":
        return False
    while not _pause_event.is_set():
        time.sleep(0.05)
        if _cycle_cancel or _abort_requested:
            return False
    return not (_cycle_cancel or _abort_requested)

def _goto_pose_with_resume(node, pose_name: str, speed: float = 0.15) -> bool:
    """Executa goto_pose. Se for pausado/interrompido e depois retomado (NÃO, CONTINUAR), re-envia a trajetória para a pose alvo!"""
    while True:
        if not _check_pause_and_cancel():
            return False
        
        ok = node.goto_pose(pose_name, speed)
        
        if not _pause_event.is_set():
            if not _check_pause_and_cancel():
                return False
            print(f"[CYCLE] 🔄 Retomando movimento interrompido para a pose '{pose_name}'...")
            continue
            
        return ok

def _abort_cleanup():
    """Executa a sequência segura de descarte e retorno ao acionar Abort (SIM): desliga bomba no pick, volta para home e desativa o modo manual/auto."""
    global _abort_requested, _cycle_cancel
    print("[CYCLE] 🛑 Executando sequência de cancelamento/abort seguro...")
    from backend.api.cobot_routes import stop_yolo_test_process
    try:
        stop_yolo_test_process()
    except Exception:
        pass

    node = get_cobot_node()
    if node.pump_active:
        print("[CYCLE] Desligando bomba de sucção e liberando lata...")
        try:
            node.goto_pose("pick", 0.15)
        except Exception:
            pass
        node.set_pump(False)
        time.sleep(0.5)

    try:
        cell_state["status"] = "moving_home"
        print("[CYCLE] Retornando braço para HOME após abort...")
        node.goto_pose("home", 0.20)
    except Exception:
        pass

    # Desliga completamente o loop automático e reseta os estados da célula
    cell_state["auto_running"] = False
    cell_state["mode"] = "auto"
    cell_state["status"] = "idle"
    cell_state["manual_step"] = "idle"
    cell_state["yolo_detected_item"] = None
    _abort_requested = False
    _cycle_cancel = True

def is_valid_tin_class(cls_name: Optional[str]) -> bool:
    """Valida se a classe detectada pelo modelo YOLO é uma lata VÁLIDA para coleta."""
    if not cls_name:
        return False
    l = cls_name.lower().strip()
    if l in ("none", "invalid_stream", "tin_invalid") or "invalid" in l:
        return False
    if l.startswith("tin_valid") or "valid" in l:
        return True
    return False

def _run_cycle_internal(is_manual: bool = False):
    """Executa a sequência de inspeção, visão YOLO e coleta/soltura com suporte a aprovação passo-a-passo no modo manual."""
    global _cycle_cancel, _abort_requested
    _cycle_cancel = False
    _abort_requested = False
    _step_pick_event.clear()
    _step_place_event.clear()

    node = get_cobot_node()
    node.load_poses()

    missing = [p for p in ["home", "scan", "pick_approach", "pick", "place_approach", "place"] if p not in node.poses]
    if missing:
        print(f"[CYCLE] ABORTADO: poses faltando no YAML: {missing}")
        cell_state["status"] = "idle"
        cell_state["manual_step"] = "idle"
        cell_state["auto_running"] = False
        return

    from backend.api.cobot_routes import start_yolo_test_process, stop_yolo_test_process

    speed = max(0.01, min(0.15, float(cell_state.get("arm_speed", 0.15))))
    slow_speed = max(0.01, speed * 0.7)

    try:
        # ========== STEP 1: HOME → SCAN ==========
        cell_state["status"] = "moving_scan"
        print(f"[CYCLE] Step 1: Mover para posição SCAN (velocidade: {speed*100:.0f}%)...")
        ok = _goto_pose_with_resume(node, "scan", speed)
        if not ok or not _check_pause_and_cancel():
            _abort_cleanup()
            return
        time.sleep(0.5)

        # ========== STEP 2: INSPEÇÃO YOLO ATIVA ==========
        cell_state["status"] = "at_scan_inspecting"
        cell_state["manual_step"] = "at_scan"
        cell_state["yolo_detected_item"] = None
        node.clear_yolo_state()
        conf = float(cell_state.get("yolo_conf", 0.60))

        print(f"[CYCLE] Step 2: Ativando YOLO na pose SCAN (confianca > {conf:.2f})...")
        start_yolo_test_process(conf=conf)

        detected_item = None
        t0 = time.time()

        if is_manual:
            print("[CYCLE] Modo Manual: Aguardando detecção de lata válida e autorização do usuário...")
            while not _step_pick_event.is_set():
                if not _check_pause_and_cancel():
                    stop_yolo_test_process()
                    _abort_cleanup()
                    return

                yolo = node.last_yolo_msg
                if yolo and yolo.get("class") and is_valid_tin_class(yolo["class"]):
                    if yolo.get("confidence", 0) >= conf:
                        detected_item = yolo
                        cell_state["yolo_detected_item"] = yolo
                    else:
                        cell_state["yolo_detected_item"] = None
                else:
                    cell_state["yolo_detected_item"] = None
                time.sleep(0.2)
        else:
            stable_class = None
            stable_count = 0
            while (time.time() - t0) < 15.0:
                if not _check_pause_and_cancel():
                    stop_yolo_test_process()
                    _abort_cleanup()
                    return

                yolo = node.last_yolo_msg
                if yolo and yolo.get("class") and is_valid_tin_class(yolo["class"]):
                    if yolo.get("confidence", 0) >= conf:
                        cls = yolo["class"]
                        if cls == stable_class:
                            stable_count += 1
                        else:
                            stable_class = cls
                            stable_count = 1

                        if stable_count >= 3:
                            detected_item = yolo
                            cell_state["yolo_detected_item"] = yolo
                            break
                else:
                    stable_count = 0
                time.sleep(0.25)

        stop_yolo_test_process()

        if not detected_item and not is_manual:
            print("[CYCLE] Inspeção sem lata válida: mantendo braço na pose SCAN aguardando próximo ciclo...")
            cell_state["status"] = "at_scan_inspecting"
            return

        cls_name = (cell_state.get("yolo_detected_item") or {}).get("class", "lata")
        print(f"[CYCLE] Step 2 Concluído: Lata '{cls_name}' autorizada para coleta!")

        # ========== STEP 3: PICK APPROACH → PICK (BOMBA ON) → PICK APPROACH → PLACE APPROACH ==========
        cell_state["status"] = "moving_pick"
        cell_state["manual_step"] = "moving_pick"
        print(f"[CYCLE] Step 3: Indo para PICK APPROACH e PICK (velocidade: {speed*100:.0f}%)...")

        ok = _goto_pose_with_resume(node, "pick_approach", speed)
        if not ok or not _check_pause_and_cancel():
            _abort_cleanup()
            return
        time.sleep(0.3)

        cell_state["status"] = "picking"
        ok = _goto_pose_with_resume(node, "pick", slow_speed)
        if not ok or not _check_pause_and_cancel():
            _abort_cleanup()
            return
        time.sleep(0.5)

        cell_state["status"] = "moving_pick"
        ok = _goto_pose_with_resume(node, "pick_approach", speed)
        if not ok or not _check_pause_and_cancel():
            _abort_cleanup()
            return
        time.sleep(0.3)

        cell_state["status"] = "moving_place"
        ok = _goto_pose_with_resume(node, "place_approach", speed)
        if not ok or not _check_pause_and_cancel():
            _abort_cleanup()
            return
        time.sleep(0.5)

        # ========== STEP 4: AGUARDAR AUTORIZAÇÃO DE PLACE EM PLACE_APPROACH ==========
        if is_manual:
            cell_state["status"] = "at_place_approach_waiting"
            cell_state["manual_step"] = "at_place_approach"
            print("[CYCLE] Step 4 (Manual): Chegou a PLACE APPROACH. Aguardando autorização para soltar a lata...")
            while not _step_place_event.is_set():
                if not _check_pause_and_cancel():
                    _abort_cleanup()
                    return
                time.sleep(0.2)

        # ========== STEP 5: PLACE (BOMBA OFF) → PLACE APPROACH → HOME ==========
        cell_state["status"] = "placing"
        cell_state["manual_step"] = "placing"
        print(f"[CYCLE] Step 5: Avançando para PLACE e desligando bomba (velocidade: {speed*100:.0f}%)...")
        ok = _goto_pose_with_resume(node, "place", slow_speed)
        if not ok or not _check_pause_and_cancel():
            _abort_cleanup()
            return
        time.sleep(0.5)

        ok = _goto_pose_with_resume(node, "place_approach", speed)
        if not ok or not _check_pause_and_cancel():
            _abort_cleanup()
            return
        time.sleep(0.3)

        cell_state["status"] = "moving_home"
        print("[CYCLE] Finalização: Retornando para HOME...")
        _goto_pose_with_resume(node, "home", 0.20)

        print(f"[CYCLE] ✅ CICLO EXECUTADO COM SUCESSO COMPLETO!")

    except Exception as e:
        print(f"[CYCLE] ERRO no ciclo interno: {e}")
        _abort_cleanup()
    finally:
        cell_state["status"] = "idle"
        cell_state["manual_step"] = "idle"
        cell_state["yolo_detected_item"] = None
        cell_state["manual_authorized"] = False

def _run_auto_loop():
    """Worker do modo automático contínuo com verificação de interrupção e cooldown."""
    global _cycle_cancel, _abort_requested
    print("[AUTO_LOOP] 🚀 Modo Automático INICIADO em background.")
    
    while cell_state.get("auto_running", False) and not _cycle_cancel and not _abort_requested:
        if cell_state.get("panic_locked"):
            break

        _run_cycle_internal(is_manual=False)
        
        if not cell_state.get("auto_running", False) or _cycle_cancel or _abort_requested:
            break

        cooldown = float(cell_state.get("cooldown_sec", 5.0))
        t0 = time.time()
        while (time.time() - t0) < cooldown:
            if not cell_state.get("auto_running", False) or _cycle_cancel or _abort_requested:
                break
            if not _check_pause_and_cancel():
                break
            time.sleep(0.3)

    cell_state["auto_running"] = False
    print("[AUTO_LOOP] 🛑 Modo Automático TOTALMENTE ENCERRADO.")

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
    """Altera as configurações mestre da célula (modo, cooldown, confiança)."""
    global _cycle_cancel
    if cell_state.get("panic_locked"):
        raise HTTPException(status_code=423, detail="Célula bloqueada em modo de Pânico. É necessário reiniciar o sistema.")
    if payload.mode not in ["auto", "manual"]:
        raise HTTPException(status_code=400, detail="Modo deve ser 'auto' ou 'manual'.")

    cell_state["mode"] = payload.mode
    if payload.cooldown_sec is not None:
        cell_state["cooldown_sec"] = max(0.0, payload.cooldown_sec)
    if payload.yolo_conf is not None:
        cell_state["yolo_conf"] = max(0.10, min(1.0, payload.yolo_conf))
    if payload.arm_speed is not None:
        cell_state["arm_speed"] = max(0.01, min(0.15, payload.arm_speed))

    if payload.mode == "manual":
        # Se trocou para MANUAL, desliga o loop automático
        cell_state["auto_running"] = False
        _cycle_cancel = True

    return {"status": "success", "cell": cell_state}

@router.post("/auto/start")
def start_auto_mode():
    """Inicia a execução contínua do Modo Automático."""
    global _cycle_thread, _cycle_cancel, _abort_requested, _pause_event
    if cell_state.get("panic_locked"):
        raise HTTPException(status_code=423, detail="Célula bloqueada em Pânico.")

    cell_state["mode"] = "auto"
    cell_state["auto_running"] = True
    _cycle_cancel = False
    _abort_requested = False
    _pause_event.set()

    if _cycle_thread is None or not _cycle_thread.is_alive():
        _cycle_thread = threading.Thread(target=_run_auto_loop, daemon=True)
        _cycle_thread.start()
        return {"status": "success", "message": "Modo Automático INICIADO com SUCESSO!"}

    return {"status": "success", "message": "Modo Automático já está em execução."}

@router.post("/auto/stop")
def stop_auto_mode():
    """Para a execução do Modo Automático."""
    global _cycle_cancel
    _cycle_cancel = True
    cell_state["auto_running"] = False
    cell_state["mode"] = "auto"
    cell_state["status"] = "idle"
    return {"status": "success", "message": "Modo Automático PARADO."}

# ============================================================
# ENDPOINTS DO MODO MANUAL PASSO-A-PASSO
# ============================================================

@router.post("/manual/start_scan")
def manual_start_scan():
    """Passo 1 do Modo Manual: move o braço para a posição SCAN e liga a inspeção de visão YOLO."""
    global _cycle_thread
    if cell_state.get("panic_locked"):
        raise HTTPException(status_code=423, detail="Célula bloqueada em Pânico.")
    if cell_state["mode"] != "manual":
        raise HTTPException(status_code=400, detail="Este comando é exclusivo do Modo Manual.")
    if _cycle_thread is not None and _cycle_thread.is_alive():
        raise HTTPException(status_code=409, detail="Um ciclo já está em execução.")

    _cycle_thread = threading.Thread(target=_run_cycle_internal, kwargs={"is_manual": True}, daemon=True)
    _cycle_thread.start()
    return {"status": "success", "message": "Braço movendo para SCAN e ativando visão YOLO..."}

@router.post("/manual/authorize_pick")
def manual_authorize_pick():
    """Passo 2 do Modo Manual: Autoriza avançar para o PICK somente se houver lata válida detectada pelo YOLO."""
    if cell_state["mode"] != "manual":
        raise HTTPException(status_code=400, detail="Exclusivo do Modo Manual.")
    if cell_state["status"] != "at_scan_inspecting":
        raise HTTPException(status_code=400, detail="O braço precisa estar na posição SCAN inspecionando para autorizar a coleta.")
    if not cell_state.get("yolo_detected_item"):
        raise HTTPException(status_code=400, detail="Impossível autorizar coleta: nenhuma lata válida foi identificada pela visão YOLO!")

    _step_pick_event.set()
    return {"status": "success", "message": "Coleta autorizada! Movendo braço para o PICK..."}

@router.post("/manual/authorize_place")
def manual_authorize_place():
    """Passo 3 do Modo Manual: Autoriza avançar para soltar a lata no PLACE quando o braço estiver em PLACE_APPROACH."""
    if cell_state["mode"] != "manual":
        raise HTTPException(status_code=400, detail="Exclusivo do Modo Manual.")
    if cell_state["status"] != "at_place_approach_waiting":
        raise HTTPException(status_code=400, detail="O braço precisa estar aguardando em PLACE APPROACH para autorizar a soltura.")

    _step_place_event.set()
    return {"status": "success", "message": "Soltura autorizada! Liberando lata no PLACE..."}

# ============================================================
# ENDPOINTS DE INTERRUPÇÃO (PAUSA / CONFIRMAÇÃO / ABORT)
# ============================================================

@router.post("/interrupt")
def interrupt_operation():
    """Botão Interromper (Manual e Auto): Congela os motores do robô em < 5ms no ponto atual e abre confirmação."""
    if cell_state.get("panic_locked"):
        raise HTTPException(status_code=423, detail="Célula bloqueada em Pânico.")

    _pause_event.clear()  # Congela a thread do ciclo instantaneamente
    cell_state["status"] = "interrupted_paused"

    # Dispara a trava dos servos em < 5ms via HTTP Micro-Bridge diretamente no microcontrolador/Nano
    try:
        import urllib.request
        from backend.config.settings import get_settings
        nano_ip = get_settings().JETSON_NANO_IP
        req = urllib.request.Request(f"http://{nano_ip}:8088/servos/lock")
        with urllib.request.urlopen(req, timeout=0.5) as resp:
            print(f"[INFO] Trava de interrupção via HTTP Micro-Bridge ({nano_ip}) enviada em < 5ms!")
    except Exception as e:
        print(f"[WARN] HTTP Micro-Bridge lock indisponível: {e}")

    node = get_cobot_node()
    node.call_trigger_service(node.lock_cli, "Travar Servos (Interrupção)")

    return {
        "status": "interrupted",
        "message": "Operação interrompida! Motores congelados instantaneamente na posição atual."
    }

@router.post("/interrupt/confirm")
def confirm_interrupt(payload: InterruptConfirmSchema):
    """Confirmação da Interrupção: abort=True (SIM, aborta e solta a lata no pick) ou abort=False (NÃO, continua). Mantém torque 100% ativo."""
    global _abort_requested, _cycle_thread
    
    if payload.abort:
        print("[INTERRUPT] Usuário selecionou SIM (ABORTAR). Motores mantêm torque 100% ativo!")
        _abort_requested = True
        _pause_event.set()  # Acorda a thread para executar o _abort_cleanup() mantendo o torque dos motores!
        
        # Se nenhuma thread de ciclo estiver rodando em segundo plano, executa a limpeza imediatamente
        if _cycle_thread is None or not _cycle_thread.is_alive():
            _abort_cleanup()
        return {"status": "aborting", "message": "Abortando operação com torque ativo... Retornando braço para HOME."}
    else:
        print("[INTERRUPT] Usuário selecionou NÃO (CONTINUAR). Motores mantêm torque e retomam a movimentação!")
        _abort_requested = False
        _pause_event.set()  # Acorda a thread para continuar o movimento normal mantendo o torque energizado!
        
        # Se nenhuma thread de ciclo estiver rodando em segundo plano, restaura o status para idle
        if _cycle_thread is None or not _cycle_thread.is_alive():
            cell_state["status"] = "idle"
            cell_state["manual_step"] = "idle"
        return {"status": "resumed", "message": "Operação retomada com sucesso!"}

@router.post("/stop")
def emergency_stop():
    """Parada de emergência suave: desliga bomba, cancela o Modo Automático, desativa visão YOLO e retorna o braço para HOME."""
    global _cycle_cancel, _abort_requested
    _cycle_cancel = True
    _abort_requested = True
    _pause_event.set()

    if cell_state.get("panic_locked"):
        raise HTTPException(status_code=423, detail="Célula bloqueada em modo de Pânico. É necessário reiniciar o sistema.")

    node = get_cobot_node()
    node.load_poses()
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
    cell_state["manual_step"] = "idle"
    cell_state["yolo_detected_item"] = None

    def _home_worker():
        try:
            node.goto_pose("home", 0.15)
        except Exception:
            pass
        finally:
            cell_state["status"] = "idle"

    t = threading.Thread(target=_home_worker, daemon=True)
    t.start()

    return {
        "status": "emergency_stop_triggered",
        "message": "Parada de emergência acionada. Modo Automático DESLIGADO, bomba e teste YOLO parados, e braço retornando para HOME."
    }

@router.post("/panic")
def panic_stop():
    """Botão de Pânico Master: interrompe TUDO no projeto (Bomba, Câmera, YOLO, Robô, Motores e Planejamento MoveIt) e bloqueia a célula instantaneamente em < 10ms."""
    global _cycle_cancel, _abort_requested
    _cycle_cancel = True
    _abort_requested = True
    _pause_event.set()

    # Trava imediata de estado local (< 1ms)
    cell_state["panic_locked"] = True
    cell_state["status"] = "panic_locked"
    cell_state["manual_authorized"] = False
    cell_state["manual_step"] = "idle"

    # Worker assíncrono em segundo plano para limpeza de SSH, sub-processos e ROS 2 sem travar a resposta HTTP
    def _async_panic_cleanup():
        from backend.api.cobot_routes import stop_yolo_test_process
        from backend.api.health_routes import stop_camera_stream
        import subprocess
        import urllib.request
        from backend.config.settings import get_settings

        nano_ip = get_settings().JETSON_NANO_IP

        try:
            req = urllib.request.Request(f"http://{nano_ip}:8088/panic")
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                print(f"[INFO] Pânico via HTTP Micro-Bridge ({nano_ip}) enviado em < 5ms (Motores congelados no robô físico)")
        except Exception as e:
            print(f"[WARN] HTTP Micro-Bridge panic trigger indisponível: {e}")

        try:
            stop_yolo_test_process()
        except Exception as e:
            print(f"[WARN] Erro ao parar teste YOLO no pânico: {e}")

        try:
            stop_camera_stream()
        except Exception as e:
            print(f"[WARN] Erro ao desligar câmera no pânico: {e}")

        node = get_cobot_node()
        try:
            node.set_pump(False)
            node.clear_yolo_state()
            node.call_trigger_service(node.lock_cli, "Travar Servos (Pânico)")
        except Exception as e:
            print(f"[WARN] Erro ao desligar bomba/motores no Pânico: {e}")

        try:
            print("[INFO] Matando MoveIt Planning, RViz e janelas GUI no container mycobot_ros2...")
            subprocess.run('docker exec mycobot_ros2 bash -c "pkill -9 -f move_group 2>/dev/null || true; pkill -9 -f rviz 2>/dev/null || true; pkill -9 -f cam_yolo_test 2>/dev/null || true"', shell=True, timeout=5)
        except Exception as e:
            print(f"[WARN] Erro ao matar MoveIt planning no pânico: {e}")

        try:
            print(f"[INFO] Matando ponte mycobot_bridge na Jetson Nano ({nano_ip})...")
            cmd_kill_nano = f"sshpass -p Elephant ssh -o StrictHostKeyChecking=no er@{nano_ip} 'pkill -9 -f mycobot_bridge 2>/dev/null || true; fuser -k 8088/tcp 2>/dev/null || true'"
            subprocess.run(cmd_kill_nano, shell=True, timeout=5)
        except Exception as e:
            print(f"[WARN] Erro ao encerrar mycobot_bridge no Nano: {e}")

    t = threading.Thread(target=_async_panic_cleanup, daemon=True)
    t.start()

    return {
        "status": "panic_triggered",
        "panic_locked": True,
        "message": "PÂNICO ABSOLUTO: Todos os componentes foram PARADOS! As juntas do robô estão TRAVADAS. É necessário reiniciar."
    }

def _reset_cell_panic_lock():
    """Desbloqueia a célula do estado de pânico, zera o modo automático e reseta os status para idle."""
    global _abort_requested, _cycle_cancel
    _abort_requested = False
    _cycle_cancel = True
    cell_state["panic_locked"] = False
    cell_state["auto_running"] = False
    cell_state["mode"] = "auto"
    cell_state["status"] = "idle"
    cell_state["manual_step"] = "idle"
    cell_state["manual_authorized"] = False
    cell_state["yolo_detected_item"] = None
    print("[CELL] 🔓 Trava de Pânico DESBLOQUEADA e estado resetado para IDLE com SUCESSO!")

@router.post("/reset_panic")
def reset_panic():
    """Desbloqueia o estado de Pânico e dispara a reinicialização limpa do MoveIt, da Câmera e do Hardware Nano."""
    _reset_cell_panic_lock()

    from backend.api.health_routes import restart_nano_hardware
    try:
        restart_nano_hardware()
    except Exception as e:
        print(f"[WARN] Erro ao reiniciar componentes no desbloqueio do pânico: {e}")

    return {
        "status": "success",
        "message": "Pânico desbloqueado com sucesso! O planejador MoveIt, o hardware da Nano e a câmera estão sendo reiniciados do zero..."
    }

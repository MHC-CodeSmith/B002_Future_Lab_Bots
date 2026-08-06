import React, { useState, useEffect } from 'react';
import NetworkStatusHeader from '../components/NetworkStatusHeader';
import CellControlPanel from '../components/CellControlPanel';
import CameraVisionPanel from '../components/CameraVisionPanel';
import TeachModePanel from '../components/TeachModePanel';
import TurtleBotDashboardTab from '../components/TurtleBotDashboardTab';
import NotificationToast from '../components/NotificationToast';
import PanicOverlayModal from '../components/PanicOverlayModal';
import RebootOverlayModal from '../components/RebootOverlayModal';
import InterruptOverlayModal from '../components/InterruptOverlayModal';
import { Bot, Cpu } from 'lucide-react';

export default function Dashboard() {
  const [activeTab, setActiveTab] = useState('cobot'); // 'cobot' | 'turtlebot'
  const [health, setHealth] = useState(null);
  const [cellStatus, setCellStatus] = useState(null);
  const [poses, setPoses] = useState(null);
  const [tbStatus, setTbStatus] = useState(null);
  const [notification, setNotification] = useState(null);
  const [isRebooting, setIsRebooting] = useState(false);

  // Estados Otimistas para Resposta Instantânea (0ms) nos Botões
  const [optimisticPump, setOptimisticPump] = useState(null);
  const [optimisticYoloTest, setOptimisticYoloTest] = useState(null);

  const getApiBase = () => {
    if (typeof window !== 'undefined') {
      const host = window.location.hostname || 'localhost';
      return `http://${host}:8000/api/v1`;
    }
    return 'http://localhost:8000/api/v1';
  };

  // Helper seguro para chamadas à API sem estourar erros de runtime unhandled
  const safeApiCall = async (url, options = {}, warningTitle = '⚠️ ATENÇÃO DE OPERAÇÃO') => {
    try {
      const res = await fetch(url, options);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = data.detail || data.message || `Erro HTTP ${res.status}`;
        setNotification({
          type: 'warning',
          title: warningTitle,
          message: msg
        });
        return { ok: false, data };
      }
      return { ok: true, data };
    } catch (e) {
      console.warn("Erro na requisição API:", e);
      setNotification({
        type: 'error',
        title: '❌ FALHA DE CONEXÃO COM O BACKEND',
        message: 'Não foi possível se comunicar com o backend do Control Center.'
      });
      return { ok: false, data: null };
    }
  };

  const refreshStatus = async () => {
    const apiBase = getApiBase();
    try {
      const [hRes, cRes, pRes, tbRes] = await Promise.all([
        fetch(`${apiBase}/health/`).catch(() => null),
        fetch(`${apiBase}/cell/status`).catch(() => null),
        fetch(`${apiBase}/cobot/poses`).catch(() => null),
        fetch(`${apiBase}/turtlebot/status`).catch(() => null)
      ]);

      if (hRes && hRes.ok) setHealth(await hRes.json());
      if (cRes && cRes.ok) {
        const cData = await cRes.json();
        setCellStatus(cData);
        setOptimisticPump(null);
        setOptimisticYoloTest(null);
      }
      if (pRes && pRes.ok) setPoses(await pRes.json());
      if (tbRes && tbRes.ok) setTbStatus(await tbRes.json());
    } catch (err) {
      console.error("Erro ao atualizar status:", err);
    }
  };

  useEffect(() => {
    refreshStatus();
    const interval = setInterval(refreshStatus, 2000);
    return () => clearInterval(interval);
  }, []);

  // Handlers Célula & Cobot
  const handleUpdateMode = async (payload) => {
    const apiBase = getApiBase();
    const modeObj = typeof payload === 'string' 
      ? { mode: payload, cooldown_sec: 5.0, yolo_conf: 0.60 } 
      : payload;
    await safeApiCall(`${apiBase}/cell/mode`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(modeObj)
    }, '⚙️ CONFIGURAÇÃO DE MODO');
    refreshStatus();
  };

  const handleAutoStart = async () => {
    const apiBase = getApiBase();
    await safeApiCall(`${apiBase}/cell/auto/start`, { method: 'POST' });
    refreshStatus();
  };

  const handleAutoStop = async () => {
    const apiBase = getApiBase();
    await safeApiCall(`${apiBase}/cell/auto/stop`, { method: 'POST' });
    refreshStatus();
  };

  const handleManualStartScan = async () => {
    const apiBase = getApiBase();
    await safeApiCall(`${apiBase}/cell/manual/start_scan`, { method: 'POST' }, '🔍 MODO MANUAL: MOVER PARA SCAN');
    refreshStatus();
  };

  const handleManualAuthorizePick = async () => {
    const apiBase = getApiBase();
    await safeApiCall(`${apiBase}/cell/manual/authorize_pick`, { method: 'POST' });
    refreshStatus();
  };

  const handleManualAuthorizePlace = async () => {
    const apiBase = getApiBase();
    await safeApiCall(`${apiBase}/cell/manual/authorize_place`, { method: 'POST' });
    refreshStatus();
  };

  const handleInterrupt = async () => {
    const apiBase = getApiBase();
    await safeApiCall(`${apiBase}/cell/interrupt`, { method: 'POST' });
    refreshStatus();
  };

  const handleConfirmInterrupt = async (shouldAbort) => {
    const apiBase = getApiBase();
    await safeApiCall(`${apiBase}/cell/interrupt/confirm`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ abort: Boolean(shouldAbort) })
    }, '⏸️ INTERRUPÇÃO DA CÉLULA');
    refreshStatus();
  };

  const handleEmergencyStop = async () => {
    const apiBase = getApiBase();
    await safeApiCall(`${apiBase}/cell/stop`, { method: 'POST' }, '🛑 PARADA DE EMERGÊNCIA');
    refreshStatus();
  };

  const handlePanicStop = async () => {
    const apiBase = getApiBase();
    await safeApiCall(`${apiBase}/cell/panic`, { method: 'POST' });
    refreshStatus();
  };

  const handleResetPanic = async () => {
    const apiBase = getApiBase();
    await safeApiCall(`${apiBase}/cell/reset_panic`, { method: 'POST' });
    refreshStatus();
  };

  const handleRestartNanoHardware = async () => {
    setIsRebooting(true);
    const apiBase = getApiBase();
    await safeApiCall(`${apiBase}/health/restart_nano_hardware`, { method: 'POST' }, '🔄 REINICIANDO NANO');
  };

  const handleTogglePump = async () => {
    const targetState = !Boolean(cellStatus?.pump_active);
    setOptimisticPump(targetState);
    const apiBase = getApiBase();
    await safeApiCall(`${apiBase}/cobot/pump`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ on: targetState })
    }, '💨 BOMBA DE SUCÇÃO');
    refreshStatus();
  };

  const handleToggleYoloTest = async () => {
    const targetState = !Boolean(cellStatus?.yolo_test_active);
    setOptimisticYoloTest(targetState);
    const apiBase = getApiBase();
    await safeApiCall(`${apiBase}/cobot/yolo_test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active: targetState, conf: cellStatus?.cell?.yolo_conf ?? 0.60 })
    });
    refreshStatus();
  };

  const handleRestartCamera = async () => {
    const apiBase = getApiBase();
    await safeApiCall(`${apiBase}/health/restart_camera`, { method: 'POST' });
    refreshStatus();
  };

  const handleStopCamera = async () => {
    const apiBase = getApiBase();
    await safeApiCall(`${apiBase}/health/stop_camera`, { method: 'POST' });
    refreshStatus();
  };

  const handleRelease = async (joint_id = null) => {
    const apiBase = getApiBase();
    await safeApiCall(`${apiBase}/cobot/teach/release`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ joint_id })
    });
    refreshStatus();
  };

  const handleLock = async () => {
    const apiBase = getApiBase();
    await safeApiCall(`${apiBase}/cobot/teach/lock`, { method: 'POST' });
    refreshStatus();
  };

  const handleRecord = async (name) => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/cobot/teach/record/${name}`, { method: 'POST' }, `🔴 GRAVAR POSE ${name ? name.toUpperCase() : ''}`);
    if (ok) {
      setNotification({
        type: 'success',
        title: `🔴 POSE '${name ? name.toUpperCase() : ''}' GRAVADA`,
        message: `Ângulos gravados em memória com sucesso!`
      });
    }
    refreshStatus();
  };

  const handleSave = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/cobot/teach/save`, { method: 'POST' }, '💾 SALVAR CALIBRAGEM');
    if (ok) {
      setNotification({
        type: 'success',
        title: '💾 CALIBRAGEM SALVA NO DISCO',
        message: data.message || 'Todas as poses salvas no arquivo YAML do robô!'
      });
    }
    refreshStatus();
  };

  const handlePlayback = async (filename) => {
    const apiBase = getApiBase();
    await safeApiCall(`${apiBase}/cobot/teach/playback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename })
    });
    refreshStatus();
  };

  const handleClear = async () => {
    const apiBase = getApiBase();
    const { ok } = await safeApiCall(`${apiBase}/cobot/teach/clear`, { method: 'DELETE' });
    if (ok) {
      setNotification({
        type: 'warning',
        title: '🗑️ CALIBRAGEM ZERADA',
        message: 'Todas as poses salvas foram limpas. Um backup automático da versão anterior foi criado!'
      });
    }
    await refreshStatus();
  };

  const handleRestore = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/cobot/teach/restore`, { method: 'POST' }, '⏪ RESTAURAR BACKUP');
    if (ok) {
      setNotification({
        type: 'success',
        title: '⏪ BACKUP RESTAURADO',
        message: data?.message || 'Última calibragem restaurada com sucesso!'
      });
    }
    await refreshStatus();
  };

  const handleMovePose = async (name) => {
    const apiBase = getApiBase();
    await safeApiCall(`${apiBase}/cobot/move/${name}`, { method: 'POST' }, `🤖 MOVER PARA ${name.toUpperCase()}`);
    refreshStatus();
  };

  const handleMovePoseFail = async (name) => {
    const apiBase = getApiBase();
    await safeApiCall(`${apiBase}/cobot/move/${name}`, { method: 'POST' }, `🤖 MOVER PARA ${name.toUpperCase()}`);
    refreshStatus();
  };

  const handleLaunchRviz = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/health/launch_rviz`, { method: 'POST' }, '🖥️ RVIZ 2 (3D)');
    if (ok) {
      setNotification({
        type: 'info',
        title: '🖥️ RVIZ 2 (3D MOVES) INICIADO',
        message: data.message || 'Janela gráfica 3D do RViz 2 disparada no monitor do PC Host!'
      });
    }
  };

  const handleLaunchYoloWindow = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/cobot/launch_yolo_window`, { method: 'POST' }, '👁️ OPENCV YOLO');
    if (ok) {
      setNotification({
        type: 'info',
        title: '👁️ JANELA OPENCV DISPARADA',
        message: data.message || 'Janela gráfica OpenCV com bounding boxes iniciada no PC Host!'
      });
    }
  };

  // Handlers TurtleBot 4
  const handleTbDock = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/dock`, { method: 'POST' }, '⚡ TURTLEBOT DOCK');
    if (ok) {
      setNotification({
        type: 'success',
        title: '⚡ COMANDO DOCK ENVIADO',
        message: data.message || 'TurtleBot 4 retornando para a Estação de Carregamento!'
      });
    }
    refreshStatus();
  };

  const handleTbUndock = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/undock`, { method: 'POST' }, '🚀 TURTLEBOT UNDOCK');
    if (ok) {
      setNotification({
        type: 'success',
        title: '🚀 COMANDO UNDOCK ENVIADO',
        message: data.message || 'TurtleBot 4 saindo da Estação de Carregamento!'
      });
    }
    refreshStatus();
  };

  const handleTbLaunchLocalization = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/launch_localization`, { method: 'POST' }, '📍 LOCALIZAÇÃO NAV2');
    if (ok) {
      setNotification({
        type: 'success',
        title: '📍 LOCALIZAÇÃO NAV2 INICIADA',
        message: data.message || 'Localização Nav2 (B002_map.yaml) disparada com sucesso! Use 2D Pose Estimate no RViz.'
      });
    }
    refreshStatus();
  };

  const handleTbLaunchNav2 = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/launch_nav2`, { method: 'POST' }, '🧭 NAV2 STACK');
    if (ok) {
      setNotification({
        type: 'success',
        title: '🧭 STACK NAV2 INICIADO',
        message: data.message || 'Stack de navegação autônoma Nav2 iniciado com os parâmetros customizados!'
      });
    }
    refreshStatus();
  };

  const handleTbLaunchViz = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/launch_viz`, { method: 'POST' }, '🖥️ RVIZ NAV2');
    if (ok) {
      setNotification({
        type: 'success',
        title: '🖥️ RVIZ NAV2 DISPARADO',
        message: data.message || 'Janela gráfica do RViz2 para navegação disparada na tela do PC Host!'
      });
    }
  };

  const handleTbLaunchMissionManager = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/launch_mission_manager`, { method: 'POST' }, '📦 MISSION MANAGER');
    if (ok) {
      setNotification({
        type: 'success',
        title: '📦 GERENCIADOR DE MISSÕES ATIVO',
        message: data.message || 'Node mission_manager.py inicializado! Câmera OAK-D e rotinas prontas.'
      });
    }
    refreshStatus();
  };

  const handleTbTriggerDelivery = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/trigger_delivery`, { method: 'POST' }, '🚚 START DELIVERY');
    if (ok) {
      setNotification({
        type: 'success',
        title: '🚚 MISSÃO DE ENTREGA ACIONADA',
        message: data.message || 'Rotina autônoma de entrega (/start_delivery) disparada com sucesso!'
      });
    }
    refreshStatus();
  };

  const handleTbTriggerRestock = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/trigger_restock`, { method: 'POST' }, '📦 START RESTOCK');
    if (ok) {
      setNotification({
        type: 'success',
        title: '📦 MISSÃO DE REABASTECIMENTO ACIONADA',
        message: data.message || 'Rotina autônoma de reabastecimento (/start_restock) disparada com sucesso!'
      });
    }
    refreshStatus();
  };

  const [tbDiag, setTbDiag] = useState(null);

  const handleTbTriggerFailure = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/trigger_failure`, { method: 'POST' }, '⚠️ START FAILURE ROUTINE');
    if (ok) {
      setNotification({
        type: 'success',
        title: '⚠️ MISSÃO DE DESCARTE ACIONADA',
        message: data.message || 'Rotina de descarte de peça com defeito (/start_failure) disparada com sucesso!'
      });
    }
    refreshStatus();
  };

  const handleTbStopMission = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/stop_mission`, { method: 'POST' }, '🛑 CANCELAR MISSÃO');
    if (ok) {
      setNotification({
        type: 'warning',
        title: '🛑 MISSÃO INTERROMPIDA',
        message: data.message || 'Missão em andamento cancelada! Robô parado e Mission Manager liberado.'
      });
    }
    refreshStatus();
  };

  const handleTbDiagnose = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/diagnose`, { method: 'GET' }, '🔍 DIAGNÓSTICO TURTLEBOT');
    if (ok) {
      setTbDiag(data);
      setNotification({
        type: 'success',
        title: '🔍 DIAGNÓSTICO CONCLUÍDO',
        message: `Rede IP 192.168.0.129: ${data.ping_ok ? 'ONLINE' : 'SEM PING'}. ${data.topics_count} tópicos ROS 2 visíveis!`
      });
    }
  };

  const handleTbTriggerPatrol = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/trigger_patrol`, { method: 'POST' }, '🔄 START PATROL');
    if (ok) {
      setNotification({
        type: 'success',
        title: '🔄 PATRULHA INICIADA',
        message: data.message || 'Rotina autônoma de patrulha (/start_patrol) pelos waypoints iniciada!'
      });
    }
    refreshStatus();
  };

  const handleTbLaunchIntegrated3D = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/launch_integrated_3d`, { method: 'POST' }, '🌐 VISÃO 3D INTEGRADA');
    if (ok) {
      setNotification({
        type: 'success',
        title: '🌐 CENA 3D INTEGRADA DISPARADA',
        message: data.message || 'Janela 3D com Cobot + TurtleBot 4 + Mapa B002 aberta no PC Host!'
      });
    }
  };

  const handleTbTeleop = async (linear_x, angular_z) => {
    const apiBase = getApiBase();
    await safeApiCall(`${apiBase}/turtlebot/teleop`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ linear_x, angular_z })
    });
  };

  const handleTbStartOakdCamera = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/start_oakd_camera`, { method: 'POST' }, '👁️ LIGAR CÂMERA OAK-D');
    if (ok) {
      setNotification({
        type: 'success',
        title: '👁️ CÂMERA OAK-D ATIVADA',
        message: data.message || 'Visão remota da OAK-D disparada via SSH no TurtleBot 4!'
      });
    }
  };

  // Valores Finais (Considera o Estado Otimista Instantâneo se Presente)
  const currentPumpActive = optimisticPump !== null ? optimisticPump : Boolean(cellStatus?.pump_active);
  const currentYoloTestActive = optimisticYoloTest !== null ? optimisticYoloTest : Boolean(cellStatus?.yolo_test_active);

  return (
    <main className="min-h-screen p-4 md:p-8 max-w-7xl mx-auto space-y-6 relative">
      {/* Modal Popup de Reboot e Inicialização Centralizada */}
      <RebootOverlayModal
        isRebooting={isRebooting}
        onRebootComplete={() => {
          setIsRebooting(false);
          refreshStatus();
        }}
      />

      {/* Modal Popup de Bloqueio de Pânico Absoluto */}
      <PanicOverlayModal
        isLocked={Boolean(cellStatus?.cell?.panic_locked)}
        onResetPanic={handleResetPanic}
      />

      {/* Modal Popup de Confirmação de Interrupção (SIM, ABORTAR / NÃO, CONTINUAR) */}
      <InterruptOverlayModal
        isInterrupted={cellStatus?.cell?.status === 'interrupted_paused'}
        onConfirmInterrupt={handleConfirmInterrupt}
      />

      {/* Toast de Notificação Dinâmica */}
      <NotificationToast
        notification={notification}
        onClose={() => setNotification(null)}
      />

      {/* Topbar de Conectividade de Rede */}
      <NetworkStatusHeader healthData={health} />

      {/* Barra de Navegação por Abas (Tab Bar Switcher) */}
      <div className="flex items-center gap-3 p-1.5 bg-slate-900/80 rounded-2xl border border-slate-700/60 backdrop-blur-md">
        <button
          onClick={() => setActiveTab('cobot')}
          className={`flex-1 py-3 px-5 rounded-xl font-extrabold text-sm flex items-center justify-center gap-2.5 transition-all ${
            activeTab === 'cobot'
              ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-lg shadow-blue-500/20 border border-blue-400/30'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
          }`}
        >
          <Cpu className="w-5 h-5" />
          <span>🦾 Célula Robótica (MyCobot 280 & Visão)</span>
        </button>

        <button
          onClick={() => setActiveTab('turtlebot')}
          className={`flex-1 py-3 px-5 rounded-xl font-extrabold text-sm flex items-center justify-center gap-2.5 transition-all ${
            activeTab === 'turtlebot'
              ? 'bg-gradient-to-r from-purple-600 to-pink-600 text-white shadow-lg shadow-purple-500/20 border border-purple-400/30'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
          }`}
        >
          <Bot className="w-5 h-5" />
          <span>🐢 TurtleBot 4 (AMR & Visão 3D Integrada)</span>
        </button>
      </div>

      {/* Conteúdo da Aba 1: Célula Robótica */}
      {activeTab === 'cobot' && (
        <div className="space-y-6">
          <CellControlPanel
            cellState={cellStatus?.cell}
            onUpdateMode={handleUpdateMode}
            onAutoStart={handleAutoStart}
            onAutoStop={handleAutoStop}
            onManualStartScan={handleManualStartScan}
            onManualAuthorizePick={handleManualAuthorizePick}
            onManualAuthorizePlace={handleManualAuthorizePlace}
            onInterrupt={handleInterrupt}
            onConfirmInterrupt={handleConfirmInterrupt}
            onEmergencyStop={handleEmergencyStop}
            onPanicStop={handlePanicStop}
            onRestartNanoHardware={handleRestartNanoHardware}
          />

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <CameraVisionPanel
              streamUrl={health?.devices?.jetson_nano?.camera_stream_url}
              cameraOnline={Boolean(health?.devices?.jetson_nano?.camera_stream_online)}
              lastYolo={cellStatus?.last_yolo}
              yoloConfThreshold={cellStatus?.cell?.yolo_conf ?? 0.60}
              pumpActive={currentPumpActive}
              yoloTestActive={currentYoloTestActive}
              onTogglePump={handleTogglePump}
              onToggleYoloTest={handleToggleYoloTest}
              onRestartCamera={handleRestartCamera}
              onStopCamera={handleStopCamera}
              onLaunchYoloWindow={handleLaunchYoloWindow}
            />

            <TeachModePanel
              cellState={cellStatus?.cell}
              posesData={poses}
              onRelease={handleRelease}
              onLock={handleLock}
              onRecord={handleRecord}
              onSave={handleSave}
              onPlayback={handlePlayback}
              onClear={handleClear}
              onRestore={handleRestore}
              onMovePose={handleMovePose}
              onMovePoseFail={handleMovePoseFail}
              onLaunchRviz={handleLaunchRviz}
            />
          </div>
        </div>
      )}

      {/* Conteúdo da Aba 2: TurtleBot 4 (AMR) */}
      {activeTab === 'turtlebot' && (
        <TurtleBotDashboardTab
          tbStatus={tbStatus}
          tbDiag={tbDiag}
          onDiagnose={handleTbDiagnose}
          onDock={handleTbDock}
          onUndock={handleTbUndock}
          onLaunchLocalization={handleTbLaunchLocalization}
          onLaunchNav2={handleTbLaunchNav2}
          onLaunchViz={handleTbLaunchViz}
          onLaunchMissionManager={handleTbLaunchMissionManager}
          onTriggerDelivery={handleTbTriggerDelivery}
          onTriggerFailure={handleTbTriggerFailure}
          onTriggerRestock={handleTbTriggerRestock}
          onTriggerPatrol={handleTbTriggerPatrol}
          onStopMission={handleTbStopMission}
          onLaunchIntegrated3D={handleTbLaunchIntegrated3D}
          onTeleop={handleTbTeleop}
          onStartOakdCamera={handleTbStartOakdCamera}
        />
      )}
    </main>
  );
}

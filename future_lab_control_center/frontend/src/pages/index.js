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
import { useLanguage } from '../context/LanguageContext';

export default function Dashboard() {
  const { lang, t } = useLanguage();
  const [activeTab, setActiveTab] = useState('cobot'); // 'cobot' | 'turtlebot'
  const [health, setHealth] = useState(null);
  const [cellStatus, setCellStatus] = useState(null);
  const [poses, setPoses] = useState(null);
  const [tbStatus, setTbStatus] = useState(null);
  const [tbNavReadiness, setTbNavReadiness] = useState(null);
  const [tbProcesses, setTbProcesses] = useState(null);
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
  const safeApiCall = async (url, options = {}, warningTitle = '⚠️ OPERATION WARNING') => {
    try {
      const res = await fetch(url, options);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg = data.detail || data.message || `HTTP Error ${res.status}`;
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
        title: t('connFailedTitle'),
        message: t('connFailedMsg')
      });
      return { ok: false, data: null };
    }
  };

  const refreshStatus = async () => {
    const apiBase = getApiBase();
    try {
      const [hRes, cRes, pRes, tbRes, navRes, procRes] = await Promise.all([
        fetch(`${apiBase}/health/`).catch(() => null),
        fetch(`${apiBase}/cell/status`).catch(() => null),
        fetch(`${apiBase}/cobot/poses`).catch(() => null),
        fetch(`${apiBase}/turtlebot/status`).catch(() => null),
        fetch(`${apiBase}/turtlebot/nav_readiness`).catch(() => null),
        fetch(`${apiBase}/turtlebot/processes`).catch(() => null)
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
      if (navRes && navRes.ok) setTbNavReadiness(await navRes.json());
      if (procRes && procRes.ok) setTbProcesses(await procRes.json());
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
    }, t('modeConfigTitle'));
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
    await safeApiCall(`${apiBase}/cell/manual/start_scan`, { method: 'POST' }, t('manualMoveScanTitle'));
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
    }, t('cellInterruptTitle'));
    refreshStatus();
  };

  const handleEmergencyStop = async () => {
    const apiBase = getApiBase();
    await safeApiCall(`${apiBase}/cell/stop`, { method: 'POST' }, t('emergencyStopTitle'));
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
    await safeApiCall(`${apiBase}/health/restart_nano_hardware`, { method: 'POST' }, t('restartingNanoTitleAlert'));
  };

  const handleTogglePump = async () => {
    const targetState = !Boolean(cellStatus?.pump_active);
    setOptimisticPump(targetState);
    const apiBase = getApiBase();
    await safeApiCall(`${apiBase}/cobot/pump`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ on: targetState })
    }, t('suctionPumpTitle'));
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
    const { ok, data } = await safeApiCall(`${apiBase}/cobot/teach/record/${name}`, { method: 'POST' }, `${t('recordPoseTitle')} ${name ? name.toUpperCase() : ''}`);
    if (ok) {
      setNotification({
        type: 'success',
        title: `${t('poseRecordedTitle')} '${name ? name.toUpperCase() : ''}'`,
        message: t('poseRecordedMsg')
      });
    }
    refreshStatus();
  };

  const handleSave = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/cobot/teach/save`, { method: 'POST' }, t('saveCalibrationTitle'));
    if (ok) {
      setNotification({
        type: 'success',
        title: t('calibrationSavedTitle'),
        message: data.message || t('calibrationSavedMsg')
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
        title: t('calibrationClearedTitle'),
        message: t('calibrationClearedMsg')
      });
    }
    await refreshStatus();
  };

  const handleRestore = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/cobot/teach/restore`, { method: 'POST' }, t('restoreBackupTitle'));
    if (ok) {
      setNotification({
        type: 'success',
        title: t('backupRestoredTitle'),
        message: data?.message || t('backupRestoredMsg')
      });
    }
    await refreshStatus();
  };

  const handleMovePose = async (name) => {
    const apiBase = getApiBase();
    await safeApiCall(`${apiBase}/cobot/move/${name}`, { method: 'POST' }, `${t('moveToPoseTitle')} ${name.toUpperCase()}`);
    refreshStatus();
  };

  const handleMovePoseFail = async (name) => {
    const apiBase = getApiBase();
    await safeApiCall(`${apiBase}/cobot/move/${name}`, { method: 'POST' }, `${t('moveToPoseTitle')} ${name.toUpperCase()}`);
    refreshStatus();
  };

  const handleLaunchRviz = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/health/launch_rviz`, { method: 'POST' }, t('rviz3DTitle'));
    if (ok) {
      setNotification({
        type: 'info',
        title: t('rviz3DStartedTitle'),
        message: data.message || t('rviz3DStartedMsg')
      });
    }
  };

  const handleLaunchYoloWindow = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/cobot/launch_yolo_window`, { method: 'POST' }, t('opencvYoloTitle'));
    if (ok) {
      setNotification({
        type: 'info',
        title: t('opencvYoloStartedTitle'),
        message: data.message || t('opencvYoloStartedMsg')
      });
    }
  };

  // Handlers TurtleBot 4
  const handleTbDock = async () => {
    const apiBase = getApiBase();
    setNotification({
      type: 'info',
      title: '📡 Enviando Comando de Docking...',
      message: 'Comando de Dock enviado ao TurtleBot 4. Processando manobra física no robô...'
    });
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/dock`, { method: 'POST' }, t('tbDockTitle'));
    if (ok) {
      setNotification({
        type: 'success',
        title: '✅ Docking Concluído!',
        message: data.message || t('tbDockSentMsg')
      });
    }
    refreshStatus();
  };

  const handleTbUndock = async () => {
    const apiBase = getApiBase();
    setNotification({
      type: 'info',
      title: '📡 Enviando Comando de Undocking...',
      message: 'Comando de Undock enviado ao TurtleBot 4. Processando desengate físico no robô...'
    });
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/undock`, { method: 'POST' }, t('tbUndockTitle'));
    if (ok) {
      setNotification({
        type: 'success',
        title: '✅ Undocking Concluído!',
        message: data.message || t('tbUndockSentMsg')
      });
    }
    refreshStatus();
  };

  const handleTbLaunchLocalization = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/launch_localization`, { method: 'POST' }, t('tbLocTitle'));
    if (ok) {
      setNotification({
        type: 'success',
        title: t('tbLocStartedTitle'),
        message: data.message || t('tbLocStartedMsg')
      });
    }
    refreshStatus();
  };

  const handleTbLaunchNav2 = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/launch_nav2`, { method: 'POST' }, t('tbNav2Title'));
    if (ok) {
      setNotification({
        type: 'success',
        title: t('tbNav2StartedTitle'),
        message: data.message || t('tbNav2StartedMsg')
      });
    }
    refreshStatus();
  };

  const handleTbLaunchViz = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/launch_viz`, { method: 'POST' }, t('tbRvizNav2Title'));
    if (ok) {
      setNotification({
        type: 'success',
        title: t('tbRvizNav2StartedTitle'),
        message: data.message || t('tbRvizNav2StartedMsg')
      });
    }
  };

  const handleTbRestartDaemon = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/restart_daemon`, { method: 'POST' }, t('tbRestartDaemonTitle'));
    if (ok) {
      setNotification({
        type: 'success',
        title: t('tbRestartDaemonStartedTitle'),
        message: data.message || t('tbRestartDaemonStartedMsg')
      });
    }
    refreshStatus();
  };

  const handleTbStopLocalization = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/stop_localization`, { method: 'POST' }, t('tbStopLocTitle'));
    if (ok) {
      setNotification({
        type: 'info',
        title: t('tbStopLocStartedTitle'),
        message: data.message || t('tbStopLocStartedMsg')
      });
    }
    refreshStatus();
  };

  const handleTbStopNav2 = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/stop_nav2`, { method: 'POST' }, t('tbStopNav2Title'));
    if (ok) {
      setNotification({
        type: 'info',
        title: t('tbStopNav2StartedTitle'),
        message: data.message || t('tbStopNav2StartedMsg')
      });
    }
    refreshStatus();
  };

  const handleTbStopViz = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/stop_viz`, { method: 'POST' }, t('tbStopRvizTitle'));
    if (ok) {
      setNotification({
        type: 'info',
        title: t('tbStopRvizStartedTitle'),
        message: data.message || t('tbStopRvizStartedMsg')
      });
    }
    refreshStatus();
  };

  const handleTbStopMissionManagerProcess = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/stop_mission_manager_process`, { method: 'POST' }, t('tbStopMMTitle'));
    if (ok) {
      setNotification({
        type: 'info',
        title: t('tbStopMMStartedTitle'),
        message: data.message || t('tbStopMMStartedMsg')
      });
    }
    refreshStatus();
  };

  const handleTbLaunchMissionManager = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/launch_mission_manager`, { method: 'POST' }, t('tbMMTitle'));
    if (ok) {
      setNotification({
        type: 'success',
        title: t('tbMMStartedTitle'),
        message: data.message || t('tbMMStartedMsg')
      });
    }
    refreshStatus();
  };

  const handleTbTriggerDelivery = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/trigger_delivery`, { method: 'POST' }, t('tbDeliveryTitle'));
    if (ok) {
      setNotification({
        type: 'success',
        title: t('tbDeliveryStartedTitle'),
        message: data.message || t('tbDeliveryStartedMsg')
      });
    }
    refreshStatus();
  };

  const handleTbTriggerRestock = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/trigger_restock`, { method: 'POST' }, t('tbRestockTitle'));
    if (ok) {
      setNotification({
        type: 'success',
        title: t('tbRestockStartedTitle'),
        message: data.message || t('tbRestockStartedMsg')
      });
    }
    refreshStatus();
  };

  const [tbDiag, setTbDiag] = useState(null);

  const handleTbTriggerFailure = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/trigger_failure`, { method: 'POST' }, t('tbFailureTitle'));
    if (ok) {
      setNotification({
        type: 'success',
        title: t('tbFailureStartedTitle'),
        message: data.message || t('tbFailureStartedMsg')
      });
    }
    refreshStatus();
  };

  const handleTbStartSim = async (item = 'blue') => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/simulation/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ item })
    }, t('tbSimStartTitle'));
    if (ok) {
      setNotification({
        type: 'success',
        title: t('tbSimStartedTitle'),
        message: data.message || t('tbSimStartedMsg')
      });
    }
    refreshStatus();
  };

  const handleTbNextSimStep = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/simulation/next_step`, { method: 'POST' }, t('tbSimNextTitle'));
    if (ok) {
      setNotification({
        type: 'info',
        title: t('tbSimNextStartedTitle'),
        message: data.message || t('tbSimNextStartedMsg')
      });
    }
    refreshStatus();
  };

  const handleTbStopSim = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/simulation/stop`, { method: 'POST' }, t('tbSimStopTitle'));
    if (ok) {
      setNotification({
        type: 'warning',
        title: t('tbSimStopStartedTitle'),
        message: data.message || t('tbSimStopStartedMsg')
      });
    }
    refreshStatus();
  };

  const handleTbStopMission = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/stop_mission`, { method: 'POST' }, t('tbCancelMissionTitle'));
    if (ok) {
      setNotification({
        type: 'warning',
        title: t('tbCancelMissionStartedTitle'),
        message: data.message || t('tbCancelMissionStartedMsg')
      });
    }
    refreshStatus();
  };

  const handleTbDiagnose = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/diagnose`, { method: 'GET' }, t('tbDiagnoseTitle'));
    if (ok) {
      setTbDiag(data);
      const statusText = data.ping_ok ? (lang === 'pt' ? 'ONLINE' : 'ONLINE') : (lang === 'pt' ? 'SEM PING' : 'NO PING');
      const topicsText = lang === 'pt' ? 'tópicos ROS 2 visíveis' : 'ROS 2 topics visible';
      setNotification({
        type: 'success',
        title: t('tbDiagnoseStartedTitle'),
        message: `IP 192.168.0.129: ${statusText}. ${data.topics_count} ${topicsText}!`
      });
    }
  };

  const handleTbTriggerPatrol = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/trigger_patrol`, { method: 'POST' }, t('tbPatrolTitle'));
    if (ok) {
      setNotification({
        type: 'success',
        title: t('tbPatrolStartedTitle'),
        message: data.message || t('tbPatrolStartedMsg')
      });
    }
    refreshStatus();
  };

  const handleTbLaunchIntegrated3D = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/launch_integrated_3d`, { method: 'POST' }, t('tbViz3DTitle'));
    if (ok) {
      setNotification({
        type: 'success',
        title: t('tbViz3DStartedTitle'),
        message: data.message || t('tbViz3DStartedMsg')
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
    const { ok, data } = await safeApiCall(`${apiBase}/turtlebot/start_oakd_camera`, { method: 'POST' }, t('tbOakdCameraTitle'));
    if (ok) {
      setNotification({
        type: 'success',
        title: t('tbOakdCameraStartedTitle'),
        message: data.message || t('tbOakdCameraStartedMsg')
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
          <span>🦾 {t('tabCellControl')}</span>
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
          <span>{t('tabTurtleBotControl')}</span>
        </button>
      </div>

      {/* Conteúdo da Aba 1: Célula Robótica */}
      <div className={activeTab === 'cobot' ? 'space-y-6 block' : 'hidden'}>
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
          onTestHandshake={async (itemClass) => {
            const apiBase = getApiBase();
            const { ok, data } = await safeApiCall(`${apiBase}/cell/test_handshake`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ item_class: itemClass })
            }, t('tbHandshakeTestTitle'));
            if (ok) {
              setNotification({
                type: 'success',
                title: t('tbHandshakeTestStartedTitle'),
                message: data.message || t('tbHandshakeTestStartedMsg')
              });
            }
            refreshStatus();
          }}
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

      {/* Conteúdo da Aba 2: TurtleBot 4 (AMR) */}
      <div className={activeTab === 'turtlebot' ? 'space-y-6 block' : 'hidden'}>
        <TurtleBotDashboardTab
          tbStatus={tbStatus}
          tbDiag={tbDiag}
          tbNavReadiness={tbNavReadiness}
          tbProcesses={tbProcesses}
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
          onStartSim={handleTbStartSim}
          onNextSimStep={handleTbNextSimStep}
          onStopSim={handleTbStopSim}
          onRestartDaemon={handleTbRestartDaemon}
          onStopLocalization={handleTbStopLocalization}
          onStopNav2={handleTbStopNav2}
          onStopViz={handleTbStopViz}
          onStopMissionManagerProcess={handleTbStopMissionManagerProcess}
        />
      </div>
    </main>
  );
}

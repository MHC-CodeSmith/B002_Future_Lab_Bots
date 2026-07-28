import React, { useState, useEffect } from 'react';
import NetworkStatusHeader from '../components/NetworkStatusHeader';
import CellControlPanel from '../components/CellControlPanel';
import CameraVisionPanel from '../components/CameraVisionPanel';
import TeachModePanel from '../components/TeachModePanel';
import TurtleBotPanel from '../components/TurtleBotPanel';
import NotificationToast from '../components/NotificationToast';

export default function Dashboard() {
  const [health, setHealth] = useState(null);
  const [cellStatus, setCellStatus] = useState(null);
  const [poses, setPoses] = useState(null);
  const [notification, setNotification] = useState(null);

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

  const fetchCellStatus = async () => {
    const apiBase = getApiBase();
    try {
      const resCell = await fetch(`${apiBase}/cell/status`).then(r => r.json());
      setCellStatus(resCell);
      setOptimisticPump(prev => (prev !== null && Boolean(resCell?.pump_active) === prev ? null : prev));
      setOptimisticYoloTest(prev => (prev !== null && Boolean(resCell?.yolo_test_active) === prev ? null : prev));
    } catch (e) {
      console.warn("API de célula conectando...", e);
    }
  };

  const fetchSlowStatus = async () => {
    const apiBase = getApiBase();
    try {
      const [resHealth, resPoses] = await Promise.all([
        fetch(`${apiBase}/health`).then(r => r.json()),
        fetch(`${apiBase}/cobot/poses`).then(r => r.json())
      ]);
      setHealth(resHealth);
      setPoses(resPoses);
    } catch (e) {
      console.warn("API de saúde conectando...", e);
    }
  };

  useEffect(() => {
    // Por padrão: Sempre que a página for carregada/recarregada no navegador:
    // 1. O modo de teste do YOLO é desligado
    // 2. A câmera é reiniciada no Nano
    const initOnPageLoad = async () => {
      const apiBase = getApiBase();
      try {
        await Promise.all([
          fetch(`${apiBase}/cobot/yolo_test`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ active: false })
          }),
          fetch(`${apiBase}/health/restart_camera`, { method: 'POST' })
        ]);
      } catch (e) {
        console.warn("Falha ao reinicializar estado na carga da página:", e);
      }
      fetchCellStatus();
      fetchSlowStatus();
    };

    initOnPageLoad();

    // Polling ultrarrápido de 250ms APENAS para o status da célula (sem congestionar HTTP)
    const fastInterval = setInterval(fetchCellStatus, 250);
    // Polling lento de 3000ms para saúde de rede e arquivo de poses
    const slowInterval = setInterval(fetchSlowStatus, 3000);

    return () => {
      clearInterval(fastInterval);
      clearInterval(slowInterval);
    };
  }, []);

  const handleUpdateMode = async (payload) => {
    const apiBase = getApiBase();
    await safeApiCall(`${apiBase}/cell/mode`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    fetchCellStatus();
  };

  const handleAuthorizeScan = async () => {
    const apiBase = getApiBase();
    await safeApiCall(`${apiBase}/cell/authorize_scan`, { method: 'POST' });
    fetchCellStatus();
  };

  const handleEmergencyStop = async () => {
    // Validação preventiva no cliente: checa se a pose home foi gravada
    const homeRecorded = poses?.poses?.find(p => p.name === 'home')?.recorded;
    if (!homeRecorded) {
      setNotification({
        type: 'warning',
        title: '⚠️ EMERGÊNCIA (HOME) IMPOSSÍVEL',
        message: 'A pose "home" ainda não foi salva no disco! Grave e salve a pose "home" antes de acionar o retorno de emergência.'
      });
      return;
    }

    setOptimisticPump(false);
    setOptimisticYoloTest(false);
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/cell/stop`, { method: 'POST' }, '⚠️ EMERGÊNCIA (HOME) BLOQUEADA');
    if (ok) {
      setNotification({
        type: 'success',
        title: '🛑 EMERGÊNCIA ACIONADA',
        message: data.message || 'Parada de emergência acionada. Retornando o robô para HOME.'
      });
    }
    fetchCellStatus();
  };

  const handlePanicStop = async () => {
    setOptimisticPump(false);
    setOptimisticYoloTest(false);
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/cell/panic`, { method: 'POST' }, '🚨 PÂNICO ACIONADO');
    setNotification({
      type: 'panic',
      title: '🚨 PÂNICO GERAL ATIVADO',
      message: data?.message || 'Todos os processos parados, motores travados e planejamento cancelado imediatamente!'
    });
    fetchCellStatus();
  };

  const handleRestartNanoHardware = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/health/restart_nano_hardware`, { method: 'POST' }, '🔄 REINICIAR NANO');
    if (ok) {
      setNotification({
        type: 'success',
        title: '🔄 REINICIANDO PONTE NANO (HARDWARE)',
        message: data.message || 'Comando enviado para a Jetson Nano via SSH.'
      });
    }
    refreshStatus();
  };

  const handleTogglePump = async (on) => {
    setOptimisticPump(on);
    const apiBase = getApiBase();
    const { ok } = await safeApiCall(`${apiBase}/cobot/pump`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ on })
    });
    if (!ok) setOptimisticPump(null);
    fetchCellStatus();
  };

  const handleToggleYoloTest = async (active) => {
    setOptimisticYoloTest(active);
    const apiBase = getApiBase();
    const { ok } = await safeApiCall(`${apiBase}/cobot/yolo_test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active })
    });
    if (!ok) setOptimisticYoloTest(null);
    fetchCellStatus();
  };

  const refreshStatus = async () => {
    await Promise.all([fetchCellStatus(), fetchSlowStatus()]);
  };

  const handleRestartCamera = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/health/restart_camera`, { method: 'POST' });
    if (ok) {
      setNotification({
        type: 'success',
        title: '📷 REINICIANDO CÂMERA',
        message: data.message || 'Comando de reinicialização da câmera disparado.'
      });
    }
    refreshStatus();
  };

  const handleStopCamera = async () => {
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/health/stop_camera`, { method: 'POST' });
    if (ok) {
      setNotification({
        type: 'info',
        title: '📷 CÂMERA DESLIGADA',
        message: data.message || 'Servidor de câmera encerrado no Nano.'
      });
    }
    refreshStatus();
  };

  const handleMovePose = async (poseName) => {
    setOptimisticYoloTest(false);
    const apiBase = getApiBase();
    await safeApiCall(`${apiBase}/cobot/move/${poseName}`, { method: 'POST' });
    refreshStatus();
  };

  const handleRelease = async () => {
    const apiBase = getApiBase();
    const { ok } = await safeApiCall(`${apiBase}/cobot/teach/release`, { method: 'POST' });
    if (ok) {
      setNotification({
        type: 'warning',
        title: '🔓 MOTORES LIBERADOS',
        message: 'Torques soltos. SEGURE O BRAÇO DO ROBÔ manualmente!'
      });
    }
    refreshStatus();
  };

  const handleLock = async () => {
    const apiBase = getApiBase();
    const { ok } = await safeApiCall(`${apiBase}/cobot/teach/lock`, { method: 'POST' });
    if (ok) {
      setNotification({
        type: 'success',
        title: '🔒 MOTORES TRAVADOS',
        message: 'Motores fixados na posição angular atual.'
      });
    }
    refreshStatus();
  };

  const handleRecord = async (poseName) => {
    const apiBase = getApiBase();
    const { ok } = await safeApiCall(`${apiBase}/cobot/teach/record/${poseName}`, { method: 'POST' });
    if (ok) {
      setNotification({
        type: 'success',
        title: '📍 POSE GRAVADA EM MEMÓRIA',
        message: `Pose "${poseName}" capturada! Lembre-se de clicar em "SALVAR POSES NO DISCO (5)".`
      });
    }
    await refreshStatus();
  };

  const handleSave = async () => {
    const apiBase = getApiBase();
    const { ok } = await safeApiCall(`${apiBase}/cobot/teach/save`, { method: 'POST' });
    if (ok) {
      setNotification({
        type: 'success',
        title: '💾 POSES SALVAS NO DISCO',
        message: 'Arquivo de calibragem atualizado com sucesso!'
      });
    }
    await refreshStatus();
  };

  const handlePlayback = async () => {
    // Validação de pré-requisitos no cliente para playback
    const missing = (poses?.poses || [])
      .filter(p => !p.recorded)
      .map(p => p.name);

    if (missing.length > 0) {
      setNotification({
        type: 'warning',
        title: '⚠️ PLAYBACK IMPOSSÍVEL (CALIBRAGEM INCOMPLETA)',
        message: `Não há poses salvas no disco suficientes! Poses pendentes: [${missing.join(', ')}]. Grave e salve todas as 6 poses no disco antes de iniciar o playback.`
      });
      return;
    }

    setOptimisticYoloTest(false);
    const apiBase = getApiBase();
    const { ok, data } = await safeApiCall(`${apiBase}/cobot/teach/playback`, { method: 'POST' }, '⚠️ PLAYBACK IMPOSSÍVEL');
    if (ok) {
      setNotification({
        type: 'success',
        title: '▶️ PLAYBACK INICIADO',
        message: data.message || 'Trajetória em execução em segundo plano!'
      });
    }
    await refreshStatus();
  };

  const handleClear = async () => {
    const apiBase = getApiBase();
    const { ok } = await safeApiCall(`${apiBase}/cobot/teach/clear`, { method: 'DELETE' });
    if (ok) {
      setNotification({
        type: 'warning',
        title: '🗑️ CALIBRAGEM ZERADA',
        message: 'Todas as poses salvas foram apagadas.'
      });
    }
    await refreshStatus();
  };

  // Valores Finais (Considera o Estado Otimista Instantâneo se Presente)
  const currentPumpActive = optimisticPump !== null ? optimisticPump : Boolean(cellStatus?.pump_active);
  const currentYoloTestActive = optimisticYoloTest !== null ? optimisticYoloTest : Boolean(cellStatus?.yolo_test_active);

  return (
    <main className="min-h-screen p-4 md:p-8 max-w-7xl mx-auto space-y-6 relative">
      {/* Toast de Notificação Dinâmica */}
      <NotificationToast
        notification={notification}
        onClose={() => setNotification(null)}
      />

      {/* Topbar de Conectividade de Rede */}
      <NetworkStatusHeader healthData={health} />

      {/* Painel Mestre da Célula */}
      <CellControlPanel
        cellState={cellStatus?.cell}
        onUpdateMode={handleUpdateMode}
        onAuthorizeScan={handleAuthorizeScan}
        onEmergencyStop={handleEmergencyStop}
        onPanicStop={handlePanicStop}
        onRestartNanoHardware={handleRestartNanoHardware}
      />

      {/* Grid Principal: Visão YOLO + Modo Ensino */}
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
        />

        <TeachModePanel
          posesData={poses}
          onRelease={handleRelease}
          onLock={handleLock}
          onRecord={handleRecord}
          onSave={handleSave}
          onPlayback={handlePlayback}
          onClear={handleClear}
        />
      </div>

      {/* Status do TurtleBot 4 */}
      <TurtleBotPanel tbStatus={null} />
    </main>
  );
}


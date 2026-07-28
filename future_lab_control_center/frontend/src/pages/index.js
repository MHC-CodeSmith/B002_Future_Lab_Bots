import React, { useState, useEffect } from 'react';
import NetworkStatusHeader from '../components/NetworkStatusHeader';
import CellControlPanel from '../components/CellControlPanel';
import CameraVisionPanel from '../components/CameraVisionPanel';
import TeachModePanel from '../components/TeachModePanel';
import TurtleBotPanel from '../components/TurtleBotPanel';

export default function Dashboard() {
  const [health, setHealth] = useState(null);
  const [cellStatus, setCellStatus] = useState(null);
  const [poses, setPoses] = useState(null);

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

  const fetchAllStatus = async () => {
    const apiBase = getApiBase();
    try {
      const [resHealth, resCell, resPoses] = await Promise.all([
        fetch(`${apiBase}/health`).then(r => r.json()),
        fetch(`${apiBase}/cell/status`).then(r => r.json()),
        fetch(`${apiBase}/cobot/poses`).then(r => r.json())
      ]);
      setHealth(resHealth);
      setCellStatus(resCell);
      setPoses(resPoses);

      // Limpa os estados otimistas APENAS quando a API confirmar que o estado coincide
      setOptimisticPump(prev => (prev !== null && Boolean(resCell?.pump_active) === prev ? null : prev));
      setOptimisticYoloTest(prev => (prev !== null && Boolean(resCell?.yolo_test_active) === prev ? null : prev));
    } catch (e) {
      console.warn("API de controle conectando...", e);
    }
  };

  useEffect(() => {
    fetchAllStatus();
    // Polling ultra-responsivo a cada 150ms (0.15s) para atualizações instantâneas no dashboard
    const interval = setInterval(fetchAllStatus, 150);
    return () => clearInterval(interval);
  }, []);

  const handleUpdateMode = async (payload) => {
    const apiBase = getApiBase();
    await fetch(`${apiBase}/cell/mode`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    fetchAllStatus();
  };

  const handleAuthorizeScan = async () => {
    const apiBase = getApiBase();
    await fetch(`${apiBase}/cell/authorize_scan`, { method: 'POST' });
    fetchAllStatus();
  };

  const handleEmergencyStop = async () => {
    setOptimisticPump(false);
    setOptimisticYoloTest(false);
    const apiBase = getApiBase();
    await fetch(`${apiBase}/cell/stop`, { method: 'POST' });
    fetchAllStatus();
  };

  const handleTogglePump = async (on) => {
    setOptimisticPump(on);
    const apiBase = getApiBase();
    await fetch(`${apiBase}/cobot/pump`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ on })
    });
    fetchAllStatus();
  };

  const handleToggleYoloTest = async (active) => {
    setOptimisticYoloTest(active);
    const apiBase = getApiBase();
    await fetch(`${apiBase}/cobot/yolo_test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active })
    });
    fetchAllStatus();
  };

  const handleRestartCamera = async () => {
    const apiBase = getApiBase();
    await fetch(`${apiBase}/health/restart_camera`, { method: 'POST' });
    fetchAllStatus();
  };

  const handleStopCamera = async () => {
    const apiBase = getApiBase();
    await fetch(`${apiBase}/health/stop_camera`, { method: 'POST' });
    fetchAllStatus();
  };

  const handleMovePose = async (poseName) => {
    setOptimisticYoloTest(false);
    const apiBase = getApiBase();
    await fetch(`${apiBase}/cobot/move/${poseName}`, { method: 'POST' });
    fetchAllStatus();
  };

  const handleRelease = async () => {
    const apiBase = getApiBase();
    await fetch(`${apiBase}/cobot/teach/release`, { method: 'POST' });
    fetchAllStatus();
  };

  const handleLock = async () => {
    const apiBase = getApiBase();
    await fetch(`${apiBase}/cobot/teach/lock`, { method: 'POST' });
    fetchAllStatus();
  };

  const handleRecord = async (poseName) => {
    const apiBase = getApiBase();
    await fetch(`${apiBase}/cobot/teach/record/${poseName}`, { method: 'POST' });
    await fetchAllStatus();
  };

  const handleSave = async () => {
    const apiBase = getApiBase();
    await fetch(`${apiBase}/cobot/teach/save`, { method: 'POST' });
    await fetchAllStatus();
  };

  const handlePlayback = async () => {
    setOptimisticYoloTest(false);
    const apiBase = getApiBase();
    await fetch(`${apiBase}/cobot/teach/playback`, { method: 'POST' });
    await fetchAllStatus();
  };

  const handleClear = async () => {
    const apiBase = getApiBase();
    await fetch(`${apiBase}/cobot/teach/clear`, { method: 'DELETE' });
    await fetchAllStatus();
  };

  // Valores Finais (Considera o Estado Otimista Instantâneo se Presente)
  const currentPumpActive = optimisticPump !== null ? optimisticPump : Boolean(cellStatus?.pump_active);
  const currentYoloTestActive = optimisticYoloTest !== null ? optimisticYoloTest : Boolean(cellStatus?.yolo_test_active);

  return (
    <main className="min-h-screen p-4 md:p-8 max-w-7xl mx-auto space-y-6">
      {/* Topbar de Conectividade de Rede */}
      <NetworkStatusHeader healthData={health} />

      {/* Painel Mestre da Célula */}
      <CellControlPanel
        cellState={cellStatus?.cell}
        onUpdateMode={handleUpdateMode}
        onAuthorizeScan={handleAuthorizeScan}
        onEmergencyStop={handleEmergencyStop}
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

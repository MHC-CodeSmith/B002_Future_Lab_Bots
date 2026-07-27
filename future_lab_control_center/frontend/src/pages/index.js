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
    } catch (e) {
      console.warn("API de controle conectando...", e);
    }
  };

  useEffect(() => {
    fetchAllStatus();
    const interval = setInterval(fetchAllStatus, 2000);
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
    const apiBase = getApiBase();
    await fetch(`${apiBase}/cell/stop`, { method: 'POST' });
    fetchAllStatus();
  };

  const handleTogglePump = async (on) => {
    const apiBase = getApiBase();
    await fetch(`${apiBase}/cobot/pump`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ on })
    });
    fetchAllStatus();
  };

  const handleRestartCamera = async () => {
    const apiBase = getApiBase();
    await fetch(`${apiBase}/health/restart_camera`, { method: 'POST' });
    fetchAllStatus();
  };

  const handleMovePose = async (poseName) => {
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
    const apiBase = getApiBase();
    await fetch(`${apiBase}/cobot/teach/playback`, { method: 'POST' });
    await fetchAllStatus();
  };

  const handleClear = async () => {
    const apiBase = getApiBase();
    await fetch(`${apiBase}/cobot/teach/clear`, { method: 'DELETE' });
    await fetchAllStatus();
  };

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
          lastYolo={cellStatus?.last_yolo}
          pumpActive={cellStatus?.pump_active}
          onTogglePump={handleTogglePump}
          onRestartCamera={handleRestartCamera}
          onMovePose={handleMovePose}
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

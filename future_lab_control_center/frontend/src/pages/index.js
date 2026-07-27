import React, { useState, useEffect } from 'react';
import NetworkStatusHeader from '../components/NetworkStatusHeader';
import CellControlPanel from '../components/CellControlPanel';
import CameraVisionPanel from '../components/CameraVisionPanel';
import TeachModePanel from '../components/TeachModePanel';
import TurtleBotPanel from '../components/TurtleBotPanel';

const API_BASE = "http://localhost:8000/api/v1";

export default function Dashboard() {
  const [health, setHealth] = useState(null);
  const [cellStatus, setCellStatus] = useState(null);
  const [poses, setPoses] = useState(null);

  const fetchAllStatus = async () => {
    try {
      const [resHealth, resCell, resPoses] = await Promise.all([
        fetch(`${API_BASE}/health`).then(r => r.json()),
        fetch(`${API_BASE}/cell/status`).then(r => r.json()),
        fetch(`${API_BASE}/cobot/poses`).then(r => r.json())
      ]);
      setHealth(resHealth);
      setCellStatus(resCell);
      setPoses(resPoses);
    } catch (e) {
      console.warn("Backend API offline or connecting...", e);
    }
  };

  useEffect(() => {
    fetchAllStatus();
    const interval = setInterval(fetchAllStatus, 3000);
    return () => clearInterval(interval);
  }, []);

  const handleUpdateMode = async (payload) => {
    await fetch(`${API_BASE}/cell/mode`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    fetchAllStatus();
  };

  const handleAuthorizeScan = async () => {
    await fetch(`${API_BASE}/cell/authorize_scan`, { method: 'POST' });
    fetchAllStatus();
  };

  const handleEmergencyStop = async () => {
    await fetch(`${API_BASE}/cell/stop`, { method: 'POST' });
    fetchAllStatus();
  };

  const handleTogglePump = async (on) => {
    await fetch(`${API_BASE}/cobot/pump`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ on })
    });
    fetchAllStatus();
  };

  const handleRelease = () => fetch(`${API_BASE}/cobot/teach/release`, { method: 'POST' });
  const handleLock = () => fetch(`${API_BASE}/cobot/teach/lock`, { method: 'POST' });
  const handleRecord = async (poseName) => {
    await fetch(`${API_BASE}/cobot/teach/record/${poseName}`, { method: 'POST' });
    fetchAllStatus();
  };
  const handleSave = async () => {
    await fetch(`${API_BASE}/cobot/teach/save`, { method: 'POST' });
    fetchAllStatus();
  };
  const handlePlayback = () => fetch(`${API_BASE}/cobot/teach/playback`, { method: 'POST' });
  const handleClear = async () => {
    await fetch(`${API_BASE}/cobot/teach/clear`, { method: 'DELETE' });
    fetchAllStatus();
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

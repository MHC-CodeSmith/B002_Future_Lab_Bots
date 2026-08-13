import React, { useState } from 'react';
import { 
  Bot, Battery, Anchor, Navigation, MapPin, Play, Square, 
  ArrowUp, ArrowDown, ArrowLeft, ArrowRight, ShieldAlert,
  Box, Truck, RefreshCw, Eye, Layers, Compass, Search, Wifi,
  CheckCircle2, XCircle, Activity
} from 'lucide-react';
import { useLanguage } from '../context/LanguageContext';

export default function TurtleBotDashboardTab({ 
  tbStatus, 
  tbDiag,
  tbNavReadiness,
  tbProcesses,
  onDiagnose,
  onDock, 
  onUndock, 
  onLaunchLocalization, 
  onLaunchNav2, 
  onLaunchViz, 
  onLaunchMissionManager, 
  onTriggerDelivery, 
  onTriggerFailure,
  onTriggerRestock, 
  onTriggerPatrol, 
  onStopMission,
  onLaunchIntegrated3D,
  onTeleop,
  onStartOakdCamera,
  onStartSim,
  onNextSimStep,
  onStopSim,
  onRestartDaemon,
  onStopLocalization,
  onStopNav2,
  onStopViz,
  onStopMissionManagerProcess
}) {
  const { t } = useLanguage();
  const telemetryOk = tbStatus?.telemetry_ok === true;
  const isOnline = tbStatus?.ping_ok !== false && tbStatus?.status !== 'offline';
  const batteryPct = telemetryOk && tbStatus?.battery_percentage != null ? tbStatus.battery_percentage : null;
  const batteryCurrent = telemetryOk && tbStatus?.battery_current != null ? tbStatus.battery_current : null;
  const isCharging = telemetryOk && tbStatus?.charging === true;
  const isDocked = telemetryOk ? tbStatus?.is_docked : null;
  const simState = tbStatus?.sim_state;
  const pose = (telemetryOk && tbStatus?.current_pose) ? tbStatus.current_pose : null;
  const oakdStreaming = tbStatus?.oakd_streaming === true;
  const navReady = tbNavReadiness?.ready === true;
  const motionAllowed = telemetryOk && navReady;

  const [selectedSimItem, setSelectedSimItem] = useState('blue');
  const [loadingDiag, setLoadingDiag] = useState(false);
  const [logs, setLogs] = useState([]);
  const [loadingLogs, setLoadingLogs] = useState(false);
  const [logSource, setLogSource] = useState('localization');
  const [streamKey, setStreamKey] = useState(Date.now());
  const [restartingOakd, setRestartingOakd] = useState(false);

  const [initX, setInitX] = useState(0.0);
  const [initY, setInitY] = useState(0.0);
  const [initYaw, setInitYaw] = useState(0.0);
  const [settingPose, setSettingPose] = useState(false);
  const [poseMsg, setPoseMsg] = useState(null);

  const [amclStatus, setAmclStatus] = useState(null);
  const [navPoses, setNavPoses] = useState(null);
  const [savingDockPose, setSavingDockPose] = useState(false);

  const fetchAmclAndPoses = async () => {
    try {
      const host = typeof window !== 'undefined' ? window.location.hostname : 'localhost';
      const [amclRes, posesRes] = await Promise.all([
        fetch(`http://${host}:8000/api/v1/turtlebot/amcl_status`).catch(() => null),
        fetch(`http://${host}:8000/api/v1/turtlebot/nav_poses`).catch(() => null)
      ]);
      if (amclRes && amclRes.ok) setAmclStatus(await amclRes.json());
      if (posesRes && posesRes.ok) setNavPoses(await posesRes.json());
    } catch (e) {}
  };

  React.useEffect(() => {
    fetchAmclAndPoses();
    const interval = setInterval(fetchAmclAndPoses, 2000);
    return () => clearInterval(interval);
  }, []);

  const handleUseDockPose = () => {
    if (navPoses?.dock_pose) {
      setInitX(navPoses.dock_pose.x);
      setInitY(navPoses.dock_pose.y);
      setInitYaw(navPoses.dock_pose.yaw);
    }
  };

  const handleSaveDockPose = async () => {
    setSavingDockPose(true);
    setPoseMsg(null);
    try {
      const host = typeof window !== 'undefined' ? window.location.hostname : 'localhost';
      const res = await fetch(`http://${host}:8000/api/v1/turtlebot/save_dock_pose`, {
        method: 'POST'
      });
      const data = await res.json();
      if (res.ok) {
        setPoseMsg({ type: 'success', text: data.message || 'Pose da dock gravada com sucesso!' });
        fetchAmclAndPoses();
      } else {
        setPoseMsg({ type: 'error', text: data.detail || 'Falha ao gravar pose da dock.' });
      }
    } catch (e) {
      setPoseMsg({ type: 'error', text: e.message });
    } finally {
      setSavingDockPose(false);
    }
  };

  const handleSetInitialPose = async () => {
    setSettingPose(true);
    setPoseMsg(null);
    try {
      const res = await fetch(`http://${window.location.hostname}:8000/api/v1/turtlebot/set_initial_pose`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ x: parseFloat(initX), y: parseFloat(initY), yaw: parseFloat(initYaw) })
      });
      const data = await res.json();
      if (res.ok) {
        setPoseMsg({ type: 'success', text: data.message || 'Pose inicial enviada!' });
      } else {
        setPoseMsg({ type: 'error', text: data.detail || 'Falha ao enviar pose inicial.' });
      }
    } catch (e) {
      setPoseMsg({ type: 'error', text: e.message });
    } finally {
      setSettingPose(false);
    }
  };

  const fetchLogs = async (sourceParam = logSource) => {
    setLoadingLogs(true);
    try {
      const src = sourceParam || logSource;
      const host = typeof window !== 'undefined' ? window.location.hostname : 'localhost';
      const res = await fetch(`http://${host}:8000/api/v1/turtlebot/logs?source=${src}`);
      const data = await res.json();
      if (data?.logs) {
        setLogs(data.logs);
      }
    } catch (err) {
      console.error(err);
    }
    setLoadingLogs(false);
  };

  const handleSelectLogSource = (src) => {
    setLogSource(src);
    setLogs([`Carregando logs de '${src}'...`]);
    fetchLogs(src);
  };

  React.useEffect(() => {
    fetchLogs(logSource);
    const interval = setInterval(() => {
      fetchLogs(logSource);
    }, 2500);
    return () => clearInterval(interval);
  }, [logSource]);

  const handleRunDiagnose = async () => {
    setLoadingDiag(true);
    if (onDiagnose) {
      await onDiagnose();
    }
    setLoadingDiag(false);
  };

  const handleSendTeleop = (lx, az) => {
    if (onTeleop) {
      onTeleop(lx, az);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header Telemetria & Status de Conexão */}
      <div className="glass-card p-6 rounded-2xl border border-slate-700/60 shadow-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-700/80 pb-4">
          <div className="flex items-center gap-3">
            <div className="p-3 bg-blue-500/20 text-blue-400 rounded-xl border border-blue-500/30">
              <Bot className="w-7 h-7" />
            </div>
            <div>
              <h2 className="text-xl font-extrabold text-slate-100">{t('tbTitle')}</h2>
              <p className="text-xs text-slate-400">{t('tbSub')}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className={`text-xs px-3 py-1.5 rounded-full font-extrabold flex items-center gap-1.5 ${isOnline ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40' : 'bg-red-500/20 text-red-300 border border-red-500/40'}`}>
              <span className={`w-2 h-2 rounded-full ${isOnline ? 'bg-emerald-400 animate-pulse' : 'bg-red-500'}`}></span>
              {isOnline ? t('onlineDds') : t('disconnectedBattery')}
            </span>
          </div>
        </div>

        {/* 🚨 BANNER ALERTA DE TELEMETRIA INATIVA */}
        {!telemetryOk && (
          <div className="mt-4 p-4 rounded-xl bg-red-950/60 border border-red-500/60 flex items-center gap-3 text-red-200 font-bold shadow-lg animate-pulse">
            <ShieldAlert className="w-6 h-6 text-red-400 shrink-0" />
            <div>
              <p className="text-sm font-black text-red-100">🔴 SEM TELEMETRIA DA BASE (Create 3)</p>
              <p className="text-xs font-normal text-red-300">As leituras da Create 3 estão inativas há mais de 5s. Os comandos de movimento foram bloqueados automaticamente por segurança.</p>
            </div>
          </div>
        )}

        {/* 🚦 PAINEL DE PRONTIDÃO DA NAVEGAÇÃO & SEMÁFORO ROS 2 */}
        {tbNavReadiness && (
          <div className={`mt-4 p-4 rounded-xl border transition-all ${
            tbNavReadiness.ready 
              ? 'bg-emerald-950/30 border-emerald-500/40' 
              : 'bg-amber-950/30 border-amber-500/40'
          }`}>
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <div className={`p-2 rounded-lg ${tbNavReadiness.ready ? 'bg-emerald-500/20 text-emerald-400' : 'bg-amber-500/20 text-amber-400'}`}>
                  <Activity className="w-5 h-5 animate-pulse" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-slate-200">Prontidão da Navegação:</span>
                    <span className={`text-xs px-2.5 py-0.5 rounded-full font-black ${
                      tbNavReadiness.ready 
                        ? 'bg-emerald-500/30 text-emerald-300 border border-emerald-500/50' 
                        : 'bg-amber-500/30 text-amber-300 border border-amber-500/50'
                    }`}>
                      {tbNavReadiness.ready ? '✅ STACK PRONTA' : '⚠️ NÃO PRONTA'}
                    </span>
                  </div>
                  <p className="text-xs text-slate-300 mt-0.5 font-medium">{tbNavReadiness.hint}</p>
                </div>
              </div>
            </div>

            {/* Badges de Introspecção de Tópicos, Ações e Serviços */}
            {tbNavReadiness.checks && (
              <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 md:grid-cols-6 gap-2 text-xs">
                {Object.entries(tbNavReadiness.checks).map(([key, val]) => (
                  <div key={key} className={`px-2 py-1 rounded-md border flex items-center justify-between ${
                    val ? 'bg-slate-800/80 text-emerald-300 border-emerald-500/30' : 'bg-slate-900/80 text-slate-400 border-slate-700/50'
                  }`}>
                    <span className="truncate font-mono text-[10px]">{key}</span>
                    <span className={`w-2 h-2 rounded-full ${val ? 'bg-emerald-400' : 'bg-red-500/80'}`}></span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* 🎭 MODO SIMULADO INTERATIVO EXCLUSIVO TURTLEBOT 4 */}
        <div className="p-5 rounded-2xl border-2 border-indigo-500/50 bg-gradient-to-br from-slate-900/95 via-indigo-950/30 to-slate-900/95 shadow-2xl space-y-4 my-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-indigo-500/30 pb-3">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-indigo-500/20 text-indigo-400 rounded-xl border border-indigo-500/40">
                <Play className="w-5 h-5 animate-pulse" />
              </div>
              <div>
                <h3 className="text-base font-black text-slate-100 flex items-center gap-2">
                  {t('simTitle')}
                </h3>
                <p className="text-xs text-slate-400">
                  {t('simSub')}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {!simState?.active ? (
                <button
                  disabled={!motionAllowed}
                  title={!motionAllowed ? "Simulação bloqueada: requer telemetria fresca e stack pronta" : ""}
                  onClick={() => onStartSim && onStartSim(selectedSimItem)}
                  className={`py-2.5 px-5 font-extrabold rounded-xl shadow-lg flex items-center gap-2 transition-all active:scale-95 text-xs ${
                    motionAllowed 
                      ? 'bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white' 
                      : 'bg-slate-800 text-slate-500 cursor-not-allowed border border-slate-700'
                  }`}
                >
                  <Play className="w-4 h-4" />
                  <span>{t('btnStartSim')}</span>
                </button>
              ) : (
                <button
                  onClick={() => onStopSim && onStopSim()}
                  className="py-2.5 px-5 bg-gradient-to-r from-red-600 to-rose-600 hover:from-red-500 hover:to-rose-500 text-white font-extrabold rounded-xl shadow-lg flex items-center gap-2 transition-all active:scale-95 text-xs animate-pulse"
                >
                  <Square className="w-4 h-4" />
                  <span>{t('btnStopSim')}</span>
                </button>
              )}
            </div>
          </div>

          {/* Seleção de Peça / Lata */}
          <div className="flex flex-col sm:flex-row items-center justify-between gap-3 p-3 bg-slate-900/80 rounded-xl border border-slate-800">
            <span className="text-xs font-bold text-slate-300 uppercase tracking-wider">
              {t('selectPiece')}
            </span>
            <div className="flex items-center gap-3 w-full sm:w-auto">
              <button
                disabled={simState?.active}
                onClick={() => setSelectedSimItem('blue')}
                className={`flex-1 sm:flex-none py-2 px-4 rounded-xl font-extrabold text-xs flex items-center justify-center gap-2 transition-all border ${
                  selectedSimItem === 'blue'
                    ? 'bg-blue-600 text-white border-blue-400 shadow-lg shadow-blue-600/30'
                    : 'bg-slate-800 text-slate-400 border-slate-700 hover:bg-slate-700'
                }`}
              >
                <span className="w-2.5 h-2.5 rounded-full bg-blue-400"></span>
                <span>{t('blueTinLabel')}</span>
              </button>

              <button
                disabled={simState?.active}
                onClick={() => setSelectedSimItem('red')}
                className={`flex-1 sm:flex-none py-2 px-4 rounded-xl font-extrabold text-xs flex items-center justify-center gap-2 transition-all border ${
                  selectedSimItem === 'red'
                    ? 'bg-red-600 text-white border-red-400 shadow-lg shadow-red-600/30'
                    : 'bg-slate-800 text-slate-400 border-slate-700 hover:bg-slate-700'
                }`}
              >
                <span className="w-2.5 h-2.5 rounded-full bg-red-400"></span>
                <span>{t('redTinLabel')}</span>
              </button>
            </div>
          </div>

          {/* Status da Etapa + Botão Interativo OK / PRÓXIMO PASSO */}
          {simState?.active && (
            <div className="space-y-3 p-4 bg-indigo-950/40 rounded-xl border border-indigo-500/40">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-indigo-500/20 pb-2">
                <div>
                  <span className="text-xs font-extrabold text-indigo-400 uppercase tracking-widest">
                    {t('currentStep')} ({simState.step_index || 1}/4):
                  </span>
                  <h4 className="text-sm font-extrabold text-white mt-0.5">
                    {simState.step_title || 'Navegando...'}
                  </h4>
                </div>
                <span className={`px-3 py-1 rounded-full text-xs font-black self-start sm:self-auto ${
                  simState.waiting_confirmation
                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/50 animate-pulse'
                    : 'bg-amber-500/20 text-amber-300 border border-amber-500/50'
                }`}>
                  {simState.waiting_confirmation ? t('waitingConfirm') : t('movingRobot')}
                </span>
              </div>

              <p className="text-xs text-slate-300 font-medium">
                {simState.step_description}
              </p>

              {/* BOTÃO INTERATIVO OK / PRÓXIMO PASSO */}
              {simState.waiting_confirmation && (
                <button
                  disabled={!motionAllowed}
                  onClick={() => onNextSimStep && onNextSimStep()}
                  className={`w-full py-3.5 font-black rounded-xl shadow-xl flex items-center justify-center gap-3 transition-all text-sm border-2 uppercase tracking-wide mt-2 ${
                    motionAllowed 
                      ? 'bg-gradient-to-r from-emerald-500 via-teal-500 to-emerald-600 hover:from-emerald-400 hover:to-teal-400 text-slate-950 border-emerald-300 active:scale-98' 
                      : 'bg-slate-800 text-slate-500 border-slate-700 cursor-not-allowed'
                  }`}
                >
                  <CheckCircle2 className="w-5 h-5 text-slate-950" />
                  <span>{t('btnConfirmNext')}</span>
                </button>
              )}
            </div>
          )}
        </div>

        {/* Cards de Métricas */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-5">
          <div className="p-4 bg-slate-800/80 rounded-xl border border-slate-700/60 flex items-center gap-3">
            <div className={`p-3 rounded-lg ${telemetryOk ? (isCharging ? 'bg-emerald-500/20 text-emerald-400' : 'bg-amber-500/20 text-amber-400') : 'bg-red-500/20 text-red-400'}`}>
              <Battery className="w-6 h-6" />
            </div>
            <div>
              <p className="text-xs text-slate-400">{t('batteryCreate3')}</p>
              <p className={`text-base font-extrabold ${telemetryOk ? (isCharging ? 'text-emerald-400' : 'text-amber-400') : 'text-red-400'}`}>
                {telemetryOk && batteryPct !== null ? `${batteryPct}%` : '—'}
              </p>
              {telemetryOk && (
                <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold inline-block mt-0.5 ${isCharging ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40' : 'bg-amber-500/20 text-amber-300 border border-amber-500/40'}`} title={`Corrente elétrica: ${batteryCurrent != null ? batteryCurrent + ' A' : 'N/A'}`}>
                  {isCharging ? '⚡ Carregando' : '🔋 Descarregando'} ({batteryCurrent != null ? `${batteryCurrent} A` : ''})
                </span>
              )}
            </div>
          </div>

          <div className="p-4 bg-slate-800/80 rounded-xl border border-slate-700/60 flex items-center gap-3">
            <div className={`p-3 rounded-lg ${telemetryOk ? 'bg-blue-500/20 text-blue-400' : 'bg-slate-700 text-slate-400'}`}>
              <Anchor className="w-6 h-6" />
            </div>
            <div>
              <p className="text-xs text-slate-400">{t('dockStation')}</p>
              <p className={`text-sm font-bold ${telemetryOk ? 'text-slate-100' : 'text-slate-400'}`}>
                {telemetryOk ? (isDocked ? t('dockedRec') : t('undockedField')) : '—'}
              </p>
            </div>
          </div>

          <div className="p-4 bg-slate-800/80 rounded-xl border border-slate-700/60 flex items-center gap-3">
            <div className={`p-3 rounded-lg ${telemetryOk ? 'bg-purple-500/20 text-purple-400' : 'bg-slate-700 text-slate-400'}`}>
              <MapPin className="w-6 h-6" />
            </div>
            <div>
              <p className="text-xs text-slate-400">{t('coordinatesOdom')}</p>
              <p className={`text-sm font-bold ${telemetryOk ? 'text-purple-300' : 'text-slate-400'}`}>
                {telemetryOk && pose ? `X: ${pose.x}m | Y: ${pose.y}m` : '—'}
              </p>
            </div>
          </div>

          <div className="p-4 bg-slate-800/80 rounded-xl border border-slate-700/60 flex items-center gap-3">
            <div className={`p-3 rounded-lg ${isOnline ? 'bg-amber-500/20 text-amber-400' : 'bg-slate-700 text-slate-400'}`}>
              <Compass className="w-6 h-6" />
            </div>
            <div>
              <p className="text-xs text-slate-400">{t('nav2Status')}</p>
              <p className={`text-sm font-bold ${isOnline ? 'text-amber-300' : 'text-slate-400'}`}>
                {isOnline ? t('readyWaypoints') : '🔴 OFFLINE'}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Seção Lado a Lado: Câmera OAK-D Lite ao Vivo + Teleoperação Manual por D-Pad */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Painel de Vídeo ao Vivo da Câmera OAK-D do TurtleBot 4 */}
        <div className="glass-card p-5 rounded-2xl border border-slate-700/60 space-y-4 flex flex-col justify-between shadow-xl">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-700/60 pb-3">
            <div className="flex items-center gap-2.5">
              <Eye className="w-5 h-5 text-purple-400" />
              <div>
                <h3 className="text-base font-bold text-slate-100">{t('oakdTitle')}</h3>
                <p className="text-xs text-slate-400">{t('oakdSub')}</p>
              </div>
            </div>
            <div className="flex items-center gap-2 self-start sm:self-auto flex-wrap">
              <button
                onClick={async () => {
                  if (onStartOakdCamera) await onStartOakdCamera();
                  setStreamKey(Date.now());
                  setOakdOnline(true);
                }}
                className="py-2 px-3 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-bold rounded-xl shadow-lg flex items-center justify-center gap-2 transition-all active:scale-95 text-xs"
              >
                <Eye className="w-4 h-4" />
                <span>{t('btnStartOakd')}</span>
              </button>
              <button
                onClick={async () => {
                  setRestartingOakd(true);
                  setOakdOnline(false);
                  if (onStartOakdCamera) await onStartOakdCamera();
                  setTimeout(() => {
                    setStreamKey(Date.now());
                    setOakdOnline(true);
                    setRestartingOakd(false);
                  }, 300);
                }}
                disabled={restartingOakd}
                className="py-2 px-3 bg-slate-800 hover:bg-slate-700 text-amber-300 border border-amber-500/40 font-bold rounded-xl shadow-lg flex items-center justify-center gap-2 transition-all active:scale-95 text-xs disabled:opacity-50"
                title="Reiniciar Conexão / Reinstanciar Streaming MJPEG"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${restartingOakd ? 'animate-spin' : ''}`} />
                <span>{t('btnRestartOakd')}</span>
              </button>
            </div>
          </div>

          {/* Video Player Frame */}
          <div className="relative aspect-video bg-slate-950 rounded-xl overflow-hidden border border-slate-800 flex items-center justify-center">
            {oakdStreaming ? (
              <img
                src={typeof window !== 'undefined' ? `http://${window.location.hostname}:8000/api/v1/turtlebot/oakd_stream?t=${streamKey}` : `http://localhost:8000/api/v1/turtlebot/oakd_stream?t=${streamKey}`}
                alt="Stream da Câmera OAK-D"
                className="w-full h-full object-contain"
              />
            ) : (
              <div className="text-center p-6 space-y-3">
                <Eye className="w-12 h-12 text-slate-600 mx-auto animate-pulse" />
                <p className="text-sm font-bold text-slate-400">{t('oakdDisconnected')}</p>
                <p className="text-xs text-slate-500 max-w-md mx-auto">
                  {t('oakdInstruction')}
                </p>
              </div>
            )}
          </div>
        </div>

        {/* D-Pad Teleoperação Manual */}
        <div className="glass-card p-5 rounded-2xl border border-slate-700/60 space-y-4 flex flex-col justify-between shadow-xl">
          <div>
            <div className="flex items-center justify-between border-b border-slate-700/60 pb-3">
              <div className="flex items-center gap-2.5">
                <Bot className="w-5 h-5 text-blue-400" />
                <div>
                  <h3 className="text-base font-bold text-slate-200">{t('teleopDpadTitle')}</h3>
                  <p className="text-xs text-slate-400">{t('teleopDpadSub')}</p>
                </div>
              </div>
              <div className="flex gap-1.5">
                <button
                  onClick={onUndock}
                  title="Forçar Saída da Dock e Destravar Motores"
                  className={`py-1.5 px-3 border rounded-lg text-xs font-bold transition-all flex items-center gap-1 ${
                    !isDocked 
                      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 shadow-sm' 
                      : 'bg-amber-500/20 text-amber-300 border-amber-500/40 hover:bg-amber-500/30'
                  }`}
                >
                  <Play className="w-3.5 h-3.5" />
                  <span>UNDOCK</span>
                </button>
                <button
                  onClick={onDock}
                  title="Forçar Entrada na Dock"
                  className={`py-1.5 px-3 border rounded-lg text-xs font-bold transition-all flex items-center gap-1 ${
                    isDocked 
                      ? 'bg-blue-500/20 text-blue-300 border-blue-500/40 shadow-sm' 
                      : 'bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700'
                  }`}
                >
                  <Square className="w-3.5 h-3.5" />
                  <span>DOCK</span>
                </button>
              </div>
            </div>
            {isDocked && (
              <div className="mt-3 p-2.5 bg-amber-500/10 border border-amber-500/30 rounded-xl text-xs text-amber-300 flex items-center gap-2">
                <ShieldAlert className="w-4 h-4 text-amber-400 shrink-0" />
                <span>{t('dockAttention')}</span>
              </div>
            )}
          </div>

          <div className="flex flex-col items-center justify-center py-4">
            <div className="grid grid-cols-3 gap-3 w-56">
              <div></div>
              <button
                onClick={() => handleSendTeleop(0.25, 0.0)}
                className="p-5 bg-slate-800 hover:bg-blue-600 active:bg-blue-700 text-white font-bold rounded-2xl border border-slate-700 shadow-lg flex items-center justify-center transition-all active:scale-90"
              >
                <ArrowUp className="w-7 h-7" />
              </button>
              <div></div>

              <button
                onClick={() => handleSendTeleop(0.0, 0.6)}
                className="p-5 bg-slate-800 hover:bg-blue-600 active:bg-blue-700 text-white font-bold rounded-2xl border border-slate-700 shadow-lg flex items-center justify-center transition-all active:scale-90"
              >
                <ArrowLeft className="w-7 h-7" />
              </button>
              <button
                onClick={() => handleSendTeleop(0.0, 0.0)}
                className="p-5 bg-red-600/90 hover:bg-red-600 active:bg-red-700 text-white font-bold rounded-2xl border border-red-500 shadow-lg flex items-center justify-center transition-all active:scale-90"
              >
                <Square className="w-7 h-7 fill-current" />
              </button>
              <button
                onClick={() => handleSendTeleop(0.0, -0.6)}
                className="p-5 bg-slate-800 hover:bg-blue-600 active:bg-blue-700 text-white font-bold rounded-2xl border border-slate-700 shadow-lg flex items-center justify-center transition-all active:scale-90"
              >
                <ArrowRight className="w-7 h-7" />
              </button>

              <div></div>
              <button
                onClick={() => handleSendTeleop(-0.25, 0.0)}
                className="p-5 bg-slate-800 hover:bg-blue-600 active:bg-blue-700 text-white font-bold rounded-2xl border border-slate-700 shadow-lg flex items-center justify-center transition-all active:scale-90"
              >
                <ArrowDown className="w-7 h-7" />
              </button>
              <div></div>
            </div>
          </div>
        </div>
      </div>

      {/* Card de Diagnóstico de Rede e Tópicos ROS 2 */}
      <div className="glass-card p-5 rounded-xl border border-slate-700/60 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-700/60 pb-3">
          <div className="flex items-center gap-2.5">
            <Wifi className="w-5 h-5 text-blue-400" />
            <div>
              <h3 className="text-base font-bold text-slate-100">{t('diagTitle')}</h3>
              <p className="text-xs text-slate-400">{t('diagSub')}</p>
            </div>
          </div>
          <button
            onClick={handleRunDiagnose}
            disabled={loadingDiag}
            className="py-2.5 px-4 bg-blue-600 hover:bg-blue-500 text-white font-bold rounded-xl shadow-lg flex items-center justify-center gap-2 transition-all active:scale-95 text-xs self-start sm:self-auto"
          >
            <Search className={`w-4 h-4 ${loadingDiag ? 'animate-spin' : ''}`} />
            {loadingDiag ? t('testingConn') : t('btnAuditConn')}
          </button>
        </div>

        {tbDiag && (
          <div className="space-y-3 pt-1">
            <div className="flex flex-wrap items-center gap-3 text-xs">
              <span className={`px-3 py-1 rounded-full font-bold flex items-center gap-1.5 ${tbDiag.ping_ok ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' : 'bg-red-500/20 text-red-300 border border-red-500/30'}`}>
                {tbDiag.ping_ok ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> : <XCircle className="w-3.5 h-3.5 text-red-400" />}
                PING IP 192.168.0.129: {tbDiag.ping_ok ? 'ACTIVE' : 'NO RESPONSE'}
              </span>

              <span className="px-3 py-1 bg-slate-800 text-slate-300 border border-slate-700 rounded-full font-mono text-[11px]">
                Discovery Server: {tbDiag.discovery_server} (Domain {tbDiag.domain_id})
              </span>

              <span className="px-3 py-1 bg-purple-500/20 text-purple-300 border border-purple-500/30 rounded-full font-bold text-xs flex items-center gap-1">
                <Activity className="w-3.5 h-3.5 text-purple-400" />
                {tbDiag.topics_count} ROS 2 Topics Found
              </span>
            </div>

            {/* Grid de Tópicos Chave */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 pt-2">
              {Object.entries(tbDiag.key_topics || {}).map(([topicName, isPresent]) => (
                <div 
                  key={topicName} 
                  className={`p-2.5 rounded-lg border text-center font-mono text-xs flex items-center justify-between gap-1 ${
                    isPresent 
                      ? 'bg-emerald-950/40 text-emerald-300 border-emerald-500/40' 
                      : 'bg-red-950/30 text-red-400 border-red-500/30'
                  }`}
                >
                  <span className="truncate font-bold">{topicName}</span>
                  {isPresent ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" /> : <XCircle className="w-3.5 h-3.5 text-red-400 shrink-0" />}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Painel de Controle de Ações de Carga & Visão 3D Integrada */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Ações de Docking */}
        <div className="glass-card p-5 rounded-xl border border-slate-700/60 space-y-4">
          <h3 className="text-base font-bold text-slate-200 flex items-center gap-2">
            <Anchor className="w-5 h-5 text-blue-400" />
            {t('dockingControlTitle')}
          </h3>
          <p className="text-xs text-slate-400">{t('dockingControlSub')}</p>

          <div className="grid grid-cols-2 gap-3 pt-2">
            <button
              onClick={onDock}
              className="py-3 px-4 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold rounded-xl shadow-lg flex items-center justify-center gap-2 transition-all active:scale-95"
            >
              <Anchor className="w-4 h-4" />
              {t('btnDockShort')}
            </button>
            <button
              onClick={onUndock}
              className="py-3 px-4 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold rounded-xl shadow-lg flex items-center justify-center gap-2 transition-all active:scale-95"
            >
              <Play className="w-4 h-4" />
              {t('btnUndockShort')}
            </button>
          </div>
        </div>

        {/* Visão 3D Integrada (Cobot + TB4) */}
        <div className="glass-card p-5 rounded-xl border border-slate-700/60 space-y-4">
          <h3 className="text-base font-bold text-slate-200 flex items-center gap-2">
            <Layers className="w-5 h-5 text-purple-400" />
            {t('integrated3dTitle')}
          </h3>
          <p className="text-xs text-slate-400">{t('integrated3dSub')}</p>

          <div className="pt-2">
            <button
              onClick={onLaunchIntegrated3D}
              className="w-full py-3.5 px-4 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 text-white font-bold rounded-xl shadow-xl flex items-center justify-center gap-2 transition-all active:scale-95"
            >
              <Eye className="w-5 h-5" />
              {t('btnOpen3dIntegrated')}
            </button>
          </div>
        </div>
      </div>

      {/* Sequenciador Nav2 & Gerenciador de Missões */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Sequenciador Nav2 */}
        <div className="glass-card p-5 rounded-xl border border-slate-700/60 space-y-4">
          <h3 className="text-base font-bold text-slate-200 flex items-center gap-2">
            <Navigation className="w-5 h-5 text-amber-400" />
            {t('nav2SeqTitle')}
          </h3>
          <p className="text-xs text-slate-400">{t('nav2SeqSub')}</p>

          <div className="space-y-3 pt-1">
            <div className="flex gap-2">
              <button
                onClick={() => {
                  if (onLaunchLocalization) onLaunchLocalization();
                  handleSelectLogSource('localization');
                }}
                className="flex-1 py-3 px-4 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-bold rounded-xl flex items-center justify-between transition-all active:scale-95 text-xs sm:text-sm"
              >
                <span className="flex items-center gap-2">
                  <MapPin className="w-4 h-4 text-emerald-400" />
                  {t('step1Loc')}
                </span>
                <span className="text-[10px] sm:text-xs text-slate-400 font-normal hidden sm:inline">localization.launch.py</span>
              </button>
              <button
                onClick={() => {
                  if (onStopLocalization) onStopLocalization();
                }}
                className="px-3 py-3 bg-red-950/60 hover:bg-red-900/80 text-red-300 border border-red-500/40 font-bold rounded-xl flex items-center gap-1.5 transition-all active:scale-95 text-xs"
              >
                <Square className="w-3.5 h-3.5 fill-current text-red-400" />
                <span className="hidden sm:inline">Ctrl+C</span>
              </button>
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => {
                  if (onLaunchNav2) onLaunchNav2();
                  handleSelectLogSource('nav2');
                }}
                className="flex-1 py-3 px-4 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-bold rounded-xl flex items-center justify-between transition-all active:scale-95 text-xs sm:text-sm"
              >
                <span className="flex items-center gap-2">
                  <Navigation className="w-4 h-4 text-amber-400" />
                  {t('step2Nav')}
                </span>
                <span className="text-[10px] sm:text-xs text-slate-400 font-normal hidden sm:inline">nav2.launch.py</span>
              </button>
              <button
                onClick={() => {
                  if (onStopNav2) onStopNav2();
                }}
                className="px-3 py-3 bg-red-950/60 hover:bg-red-900/80 text-red-300 border border-red-500/40 font-bold rounded-xl flex items-center gap-1.5 transition-all active:scale-95 text-xs"
              >
                <Square className="w-3.5 h-3.5 fill-current text-red-400" />
                <span className="hidden sm:inline">Ctrl+C</span>
              </button>
            </div>

            <div className="flex gap-2">
              <button
                onClick={() => {
                  if (onLaunchViz) onLaunchViz();
                  handleSelectLogSource('viz');
                }}
                className="flex-1 py-3 px-4 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-bold rounded-xl flex items-center justify-between transition-all active:scale-95 text-xs sm:text-sm"
              >
                <span className="flex items-center gap-2">
                  <Eye className="w-4 h-4 text-blue-400" />
                  {t('step3Rviz')}
                </span>
                <span className="text-[10px] sm:text-xs text-slate-400 font-normal hidden sm:inline">view_navigation.launch.py</span>
              </button>
              <button
                onClick={() => {
                  if (onStopViz) onStopViz();
                }}
                className="px-3 py-3 bg-red-950/60 hover:bg-red-900/80 text-red-300 border border-red-500/40 font-bold rounded-xl flex items-center gap-1.5 transition-all active:scale-95 text-xs"
              >
                <Square className="w-3.5 h-3.5 fill-current text-red-400" />
                <span className="hidden sm:inline">Ctrl+C</span>
              </button>
            </div>

            <button
              onClick={() => {
                if (onRestartDaemon) onRestartDaemon();
              }}
              className="w-full py-3 px-4 bg-purple-950/50 hover:bg-purple-900/60 text-purple-200 border border-purple-500/40 font-bold rounded-xl flex items-center justify-between transition-all active:scale-95 shadow-md shadow-purple-900/20 mt-2 text-xs sm:text-sm"
            >
              <span className="flex items-center gap-2">
                <RefreshCw className="w-4 h-4 text-purple-400" />
                {t('btnRestartDaemon')}
              </span>
              <span className="text-xs text-purple-300/70 font-normal hidden sm:inline">ros2 daemon stop/start</span>
            </button>

            {/* Bloco de Definir Pose Inicial (/initialpose) */}
            <div className="p-3 bg-slate-900/80 rounded-xl border border-slate-700/80 space-y-2 mt-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
                  <MapPin className="w-3.5 h-3.5 text-purple-400" />
                  Pose Inicial (2D Pose Estimate)
                </span>
                <span className="text-[10px] text-slate-500 font-mono">/initialpose</span>
              </div>

              {/* Badge de Convergência do AMCL */}
              <div className="flex items-center justify-between p-2 rounded-lg border border-slate-800 bg-slate-950/60 text-xs">
                <span className="font-bold flex items-center gap-1.5 text-slate-300">
                  <Activity className="w-3.5 h-3.5 text-blue-400" />
                  AMCL:
                </span>
                {!amclStatus?.amcl_ok ? (
                  <span className="px-2 py-0.5 bg-slate-800 text-slate-400 border border-slate-700 rounded-full font-bold text-[10px]">
                    ⚪ AMCL fora do ar
                  </span>
                ) : !amclStatus?.converged ? (
                  <span className="px-2 py-0.5 bg-amber-500/20 text-amber-300 border border-amber-500/40 rounded-full font-bold font-mono text-[10px]" title={`Covariância: σ²x=${amclStatus.covariance?.x} σ²y=${amclStatus.covariance?.y} σ²yaw=${amclStatus.covariance?.yaw}`}>
                    🟡 Não Convergido (σ²x={amclStatus.covariance?.x}, σ²yaw={amclStatus.covariance?.yaw})
                  </span>
                ) : (
                  <span className="px-2 py-0.5 bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 rounded-full font-bold font-mono text-[10px]" title={`Pose Real AMCL: x=${amclStatus.pose?.x} y=${amclStatus.pose?.y} yaw=${amclStatus.pose?.yaw}`}>
                    🟢 Convergido (x={amclStatus.pose?.x}, y={amclStatus.pose?.y}, yaw={amclStatus.pose?.yaw})
                  </span>
                )}
              </div>

              {/* Botões "Usar pose da dock" e "Gravar pose da dock atual" */}
              <div className="grid grid-cols-2 gap-2 pt-0.5">
                <button
                  type="button"
                  onClick={handleUseDockPose}
                  disabled={!navPoses?.dock_pose}
                  className={`py-1.5 px-2 rounded-lg text-[11px] font-bold border transition-all flex items-center justify-center gap-1 ${
                    navPoses?.dock_pose?.measured
                      ? 'bg-slate-800 hover:bg-slate-700 text-blue-300 border-blue-500/40'
                      : 'bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border-amber-500/40'
                  }`}
                  title={navPoses?.dock_pose?.measured ? 'Preencher com pose medida da dock' : 'Preencher com semente estimada'}
                >
                  <Compass className="w-3.5 h-3.5" />
                  <span>
                    {navPoses?.dock_pose?.measured ? 'Usar Pose da Dock' : 'Usar Semente (não medida)'}
                  </span>
                </button>

                <button
                  type="button"
                  onClick={handleSaveDockPose}
                  disabled={!amclStatus?.converged || !isDocked || savingDockPose}
                  className={`py-1.5 px-2 rounded-lg text-[11px] font-bold border transition-all flex items-center justify-center gap-1 ${
                    amclStatus?.converged && isDocked
                      ? 'bg-emerald-600 hover:bg-emerald-500 text-white border-emerald-400 shadow'
                      : 'bg-slate-800 text-slate-500 border-slate-700 cursor-not-allowed'
                  }`}
                  title={amclStatus?.converged && isDocked ? 'Gravar pose real no nav_poses.yaml' : 'Requer AMCL convergido e robô acoplado na dock'}
                >
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  <span>{savingDockPose ? 'Gravando...' : 'Gravar Pose da Dock'}</span>
                </button>
              </div>

              <div className="grid grid-cols-3 gap-2 pt-1">
                <div>
                  <label className="text-[10px] text-slate-400 block font-mono">X (m)</label>
                  <input
                    type="number"
                    step="0.05"
                    value={initX}
                    onChange={(e) => setInitX(e.target.value)}
                    className="w-full bg-slate-800 text-slate-100 text-xs px-2 py-1 rounded border border-slate-700 font-mono"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-slate-400 block font-mono">Y (m)</label>
                  <input
                    type="number"
                    step="0.05"
                    value={initY}
                    onChange={(e) => setInitY(e.target.value)}
                    className="w-full bg-slate-800 text-slate-100 text-xs px-2 py-1 rounded border border-slate-700 font-mono"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-slate-400 block font-mono">Yaw (rad)</label>
                  <input
                    type="number"
                    step="0.1"
                    value={initYaw}
                    onChange={(e) => setInitYaw(e.target.value)}
                    className="w-full bg-slate-800 text-slate-100 text-xs px-2 py-1 rounded border border-slate-700 font-mono"
                  />
                </div>
              </div>
              <button
                disabled={!telemetryOk || !tbNavReadiness?.checks?.map || settingPose}
                onClick={handleSetInitialPose}
                className={`w-full py-2 font-bold rounded-lg text-xs flex items-center justify-center gap-2 transition-all ${
                  telemetryOk && tbNavReadiness?.checks?.map
                    ? 'bg-purple-600 hover:bg-purple-500 text-white shadow'
                    : 'bg-slate-800 text-slate-500 border border-slate-700 cursor-not-allowed'
                }`}
              >
                <MapPin className="w-3.5 h-3.5" />
                <span>{settingPose ? 'Enviando...' : 'Definir Pose Inicial'}</span>
              </button>
              {poseMsg && (
                <p className={`text-[10px] font-bold ${poseMsg.type === 'success' ? 'text-emerald-400' : 'text-red-400'}`}>
                  {poseMsg.text}
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Gerenciador de Missões (Mission Manager) */}
        <div className="glass-card p-5 rounded-xl border border-slate-700/60 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-base font-bold text-slate-200 flex items-center gap-2">
              <Truck className="w-5 h-5 text-emerald-400" />
              {t('missionManagerTitle')}
            </h3>
            <span className="text-[10px] px-2.5 py-1 bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 rounded-full font-mono font-bold">
              mission_manager.py
            </span>
          </div>
          <p className="text-xs text-slate-400">
            {t('missionManagerSub')}
          </p>

          <div className="flex gap-2">
            <button
              onClick={() => {
                if (onLaunchMissionManager) onLaunchMissionManager();
                handleSelectLogSource('mission');
              }}
              className="flex-1 py-3 px-4 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold rounded-xl shadow-lg flex items-center justify-center gap-2 transition-all active:scale-95 text-xs sm:text-sm"
            >
              <Play className="w-4.5 h-4.5 fill-current" />
              {t('btnStartNode')}
            </button>
            <button
              onClick={() => {
                if (onStopMissionManagerProcess) onStopMissionManagerProcess();
              }}
              className="px-4 py-3 bg-red-950/70 hover:bg-red-900/90 text-red-200 border border-red-500/50 font-bold rounded-xl flex items-center gap-2 transition-all active:scale-95 text-xs shadow-md shadow-red-950/30"
            >
              <Square className="w-4 h-4 fill-current text-red-400" />
              <span>{t('btnKillNode')}</span>
            </button>
          </div>

          <div className="border-t border-slate-700/60 pt-3">
            <p className="text-xs font-bold text-slate-300 mb-2">{t('triggerRoutineTitle')}</p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <button
                disabled={!motionAllowed}
                title={!motionAllowed ? "Rotina bloqueada: requer telemetria fresca e stack pronta" : ""}
                onClick={onTriggerDelivery}
                className={`py-3 px-2 font-bold rounded-xl border flex flex-col items-center justify-center gap-1 transition-all text-xs ${
                  motionAllowed 
                    ? 'bg-slate-800 hover:bg-blue-900/40 hover:border-blue-500/50 text-slate-100 border-slate-700' 
                    : 'bg-slate-900 text-slate-600 border-slate-800 cursor-not-allowed'
                }`}
              >
                <Truck className="w-5 h-5 text-blue-400" />
                <span>/start_delivery</span>
                <span className="text-[10px] text-slate-400 font-normal">{t('deliveryLabel')}</span>
              </button>

              <button
                disabled={!motionAllowed}
                title={!motionAllowed ? "Rotina bloqueada: requer telemetria fresca e stack pronta" : ""}
                onClick={onTriggerFailure}
                className={`py-3 px-2 font-bold rounded-xl border flex flex-col items-center justify-center gap-1 transition-all text-xs ${
                  motionAllowed 
                    ? 'bg-slate-800 hover:bg-red-900/40 hover:border-red-500/50 text-slate-100 border-slate-700' 
                    : 'bg-slate-900 text-slate-600 border-slate-800 cursor-not-allowed'
                }`}
              >
                <ShieldAlert className="w-5 h-5 text-red-400" />
                <span>/start_failure</span>
                <span className="text-[10px] text-slate-400 font-normal">{t('failureLabel')}</span>
              </button>

              <button
                disabled={!motionAllowed}
                title={!motionAllowed ? "Rotina bloqueada: requer telemetria fresca e stack pronta" : ""}
                onClick={onTriggerRestock}
                className={`py-3 px-2 font-bold rounded-xl border flex flex-col items-center justify-center gap-1 transition-all text-xs ${
                  motionAllowed 
                    ? 'bg-slate-800 hover:bg-amber-900/40 hover:border-amber-500/50 text-slate-100 border-slate-700' 
                    : 'bg-slate-900 text-slate-600 border-slate-800 cursor-not-allowed'
                }`}
              >
                <Box className="w-5 h-5 text-amber-400" />
                <span>/start_restock</span>
                <span className="text-[10px] text-slate-400 font-normal">{t('restockLabel')}</span>
              </button>

              <button
                disabled={!motionAllowed}
                title={!motionAllowed ? "Rotina bloqueada: requer telemetria fresca e stack pronta" : ""}
                onClick={onTriggerPatrol}
                className={`py-3 px-2 font-bold rounded-xl border flex flex-col items-center justify-center gap-1 transition-all text-xs ${
                  motionAllowed 
                    ? 'bg-slate-800 hover:bg-purple-900/40 hover:border-purple-500/50 text-slate-100 border-slate-700' 
                    : 'bg-slate-900 text-slate-600 border-slate-800 cursor-not-allowed'
                }`}
              >
                <RefreshCw className="w-5 h-5 text-purple-400" />
                <span>/start_patrol</span>
                <span className="text-[10px] text-slate-400 font-normal">{t('patrolLabel')}</span>
              </button>
            </div>

            {/* Botão de Emergência para Cancelamento de Missão */}
            <div className="pt-3">
              <button
                onClick={onStopMission}
                className="w-full py-3 px-4 bg-red-600/90 hover:bg-red-600 active:bg-red-700 text-white font-extrabold rounded-xl border border-red-500 shadow-lg flex items-center justify-center gap-2 transition-all active:scale-95 text-xs"
              >
                <Square className="w-4 h-4 fill-current" />
                <span>{t('btnCancelMission')}</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Console Terminal de Logs Nav2 / ROS 2 em Tempo Real */}
      <div className="glass-card p-5 rounded-2xl border border-slate-700/60 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-700/80 pb-3">
          <div className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-emerald-400" />
            <h3 className="text-base font-bold text-slate-200">{t('terminalLogsTitle')}</h3>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex bg-slate-900/90 p-1 rounded-xl border border-slate-800 text-xs">
              <button
                onClick={() => handleSelectLogSource('localization')}
                className={"px-3 py-1 rounded-lg font-bold transition-all " + (logSource === 'localization' ? 'bg-blue-600 text-white shadow' : 'text-slate-400 hover:text-slate-200')}
              >
                {t('logLoc')}
              </button>
              <button
                onClick={() => handleSelectLogSource('nav2')}
                className={"px-3 py-1 rounded-lg font-bold transition-all " + (logSource === 'nav2' ? 'bg-emerald-600 text-white shadow' : 'text-slate-400 hover:text-slate-200')}
              >
                {t('logNav')}
              </button>
              <button
                onClick={() => handleSelectLogSource('mission')}
                className={"px-3 py-1 rounded-lg font-bold transition-all " + (logSource === 'mission' ? 'bg-amber-600 text-white shadow' : 'text-slate-400 hover:text-slate-200')}
              >
                {t('logMission')}
              </button>
              <button
                onClick={() => handleSelectLogSource('viz')}
                className={"px-3 py-1 rounded-lg font-bold transition-all " + (logSource === 'viz' ? 'bg-purple-600 text-white shadow' : 'text-slate-400 hover:text-slate-200')}
              >
                {t('logRviz')}
              </button>
              <button
                onClick={() => handleSelectLogSource('all')}
                className={"px-3 py-1 rounded-lg font-bold transition-all " + (logSource === 'all' ? 'bg-slate-700 text-white shadow' : 'text-slate-400 hover:text-slate-200')}
              >
                {t('logAll')}
              </button>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => fetchLogs(logSource)}
                disabled={loadingLogs}
                className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-emerald-400 font-extrabold text-xs rounded-lg border border-slate-700 flex items-center gap-1.5 transition-all active:scale-95"
              >
                <RefreshCw className={"w-3.5 h-3.5 " + (loadingLogs ? "animate-spin" : "")} />
                <span>{t('btnRefresh')}</span>
              </button>
              <button
                onClick={() => setLogs([])}
                className="px-3 py-1.5 bg-red-950/50 hover:bg-red-900/80 text-red-300 font-extrabold text-xs rounded-lg border border-red-500/40 flex items-center gap-1.5 transition-all active:scale-95"
              >
                <span>{t('btnClearTerminal')}</span>
              </button>
            </div>
          </div>
        </div>

        <div className="p-4 bg-black/90 rounded-xl border border-slate-800 font-mono text-xs text-slate-300 max-h-80 overflow-y-auto space-y-1 shadow-inner">
          {logs && logs.length > 0 ? (
            logs.map((logLine, idx) => {
              let colorClass = "text-slate-300";
              if (logLine.includes("ERROR") || logLine.includes("Failed") || logLine.includes("Aborting")) {
                colorClass = "text-red-400 font-bold";
              } else if (logLine.includes("WARN")) {
                colorClass = "text-amber-300";
              } else if (logLine.includes("INFO") || logLine.includes("active") || logLine.includes("success") || logLine.includes("Read map")) {
                colorClass = "text-emerald-300";
              }
              return (
                <div key={idx} className={"leading-relaxed whitespace-pre-wrap " + colorClass}>
                  {logLine}
                </div>
              );
            })
          ) : (
            <div className="text-slate-500 italic text-center py-4">
              {t('noLogsRecorded')}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

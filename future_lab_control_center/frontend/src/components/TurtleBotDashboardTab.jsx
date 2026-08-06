import React, { useState } from 'react';
import { 
  Bot, Battery, Anchor, Navigation, MapPin, Play, Square, 
  ArrowUp, ArrowDown, ArrowLeft, ArrowRight, ShieldAlert,
  Box, Truck, RefreshCw, Eye, Layers, Compass, Search, Wifi,
  CheckCircle2, XCircle, Activity
} from 'lucide-react';

export default function TurtleBotDashboardTab({ 
  tbStatus, 
  tbDiag,
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
  onStartOakdCamera
}) {
  const isOnline = tbStatus?.status === 'ready' && tbStatus?.ping_ok !== false;
  const batteryPct = isOnline && tbStatus?.battery_percentage != null ? tbStatus.battery_percentage : null;
  const isDocked = tbStatus?.is_docked;
  const pose = tbStatus?.current_pose || { x: 0.0, y: 0.0, yaw: 0.0 };
  const [loadingDiag, setLoadingDiag] = useState(false);
  const [logs, setLogs] = useState([]);
  const [loadingLogs, setLoadingLogs] = useState(false);
  const [logSource, setLogSource] = useState('localization');
  const [oakdOnline, setOakdOnline] = useState(false);

  const fetchLogs = async (sourceParam = logSource) => {
    setLoadingLogs(true);
    try {
      const src = sourceParam || logSource;
      const res = await fetch(`http://${typeof window !== 'undefined' ? window.location.hostname : 'localhost'}:8000/api/v1/turtlebot/logs?source=${src}`);
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
    fetchLogs(src);
  };

  React.useEffect(() => {
    fetchLogs(logSource);
  }, []);

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
              <h2 className="text-xl font-extrabold text-slate-100">TurtleBot 4 (AMR Nav2 Stack)</h2>
              <p className="text-xs text-slate-400">Robô Movel Autônomo com ROS 2 Jazzy, iRobot Create 3 & Nav2</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className={`text-xs px-3 py-1.5 rounded-full font-extrabold flex items-center gap-1.5 ${isOnline ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40' : 'bg-red-500/20 text-red-300 border border-red-500/40'}`}>
              <span className={`w-2 h-2 rounded-full ${isOnline ? 'bg-emerald-400 animate-pulse' : 'bg-red-500'}`}></span>
              {isOnline ? 'ONLINE (DDS Domain 0)' : '🔴 DESCONECTADO / SEM BATERIA (192.168.0.129)'}
            </span>
          </div>
        </div>

        {/* Cards de Métricas */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-5">
          <div className="p-4 bg-slate-800/80 rounded-xl border border-slate-700/60 flex items-center gap-3">
            <div className={`p-3 rounded-lg ${isOnline ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'}`}>
              <Battery className="w-6 h-6" />
            </div>
            <div>
              <p className="text-xs text-slate-400">Bateria (Create 3)</p>
              <p className={`text-base font-extrabold ${isOnline ? 'text-emerald-400' : 'text-red-400'}`}>
                {isOnline && batteryPct !== null ? `${batteryPct}%` : '🔴 DESCONECTADO (0%)'}
              </p>
            </div>
          </div>

          <div className="p-4 bg-slate-800/80 rounded-xl border border-slate-700/60 flex items-center gap-3">
            <div className={`p-3 rounded-lg ${isOnline ? 'bg-blue-500/20 text-blue-400' : 'bg-slate-700 text-slate-400'}`}>
              <Anchor className="w-6 h-6" />
            </div>
            <div>
              <p className="text-xs text-slate-400">Estação de Carga</p>
              <p className={`text-sm font-bold ${isOnline ? 'text-slate-100' : 'text-slate-400'}`}>
                {isOnline ? (isDocked ? 'Docked (Recarregando)' : 'Em Campo (Undocked)') : '🔴 SEM TELEMETRIA'}
              </p>
            </div>
          </div>

          <div className="p-4 bg-slate-800/80 rounded-xl border border-slate-700/60 flex items-center gap-3">
            <div className={`p-3 rounded-lg ${isOnline ? 'bg-purple-500/20 text-purple-400' : 'bg-slate-700 text-slate-400'}`}>
              <MapPin className="w-6 h-6" />
            </div>
            <div>
              <p className="text-xs text-slate-400">Coordenadas (Odom)</p>
              <p className={`text-sm font-bold ${isOnline ? 'text-purple-300' : 'text-slate-400'}`}>
                {isOnline ? `X: ${pose.x}m | Y: ${pose.y}m` : '-- (Sem Sinal)'}
              </p>
            </div>
          </div>

          <div className="p-4 bg-slate-800/80 rounded-xl border border-slate-700/60 flex items-center gap-3">
            <div className={`p-3 rounded-lg ${isOnline ? 'bg-amber-500/20 text-amber-400' : 'bg-slate-700 text-slate-400'}`}>
              <Compass className="w-6 h-6" />
            </div>
            <div>
              <p className="text-xs text-slate-400">Status Nav2</p>
              <p className={`text-sm font-bold ${isOnline ? 'text-amber-300' : 'text-slate-400'}`}>
                {isOnline ? 'Pronto para Waypoints' : '🔴 OFFLINE'}
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
                <h3 className="text-base font-bold text-slate-100">Visão OAK-D Lite ao Vivo (TurtleBot 4 AMR)</h3>
                <p className="text-xs text-slate-400">Transmissão em tempo real durante a teleoperação.</p>
              </div>
            </div>
            <button
              onClick={async () => {
                if (onStartOakdCamera) await onStartOakdCamera();
                setOakdOnline(true);
              }}
              className="py-2 px-3 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-bold rounded-xl shadow-lg flex items-center justify-center gap-2 transition-all active:scale-95 text-xs self-start sm:self-auto"
            >
              <Eye className="w-4 h-4" />
              <span>👁️ LIGAR CÂMERA OAK-D</span>
            </button>
          </div>

          {/* Video Player Frame */}
          <div className="relative aspect-video bg-slate-950 rounded-xl overflow-hidden border border-slate-800 flex items-center justify-center">
            {oakdOnline ? (
              <img
                src={typeof window !== 'undefined' ? "http://" + window.location.hostname + ":8000/api/v1/turtlebot/oakd_stream" : "http://localhost:8000/api/v1/turtlebot/oakd_stream"}
                alt="Stream da Câmera OAK-D"
                className="w-full h-full object-contain"
                onError={() => setOakdOnline(false)}
              />
            ) : (
              <div className="text-center p-6 space-y-3">
                <Eye className="w-12 h-12 text-slate-600 mx-auto animate-pulse" />
                <p className="text-sm font-bold text-slate-400">Câmera OAK-D Desconectada</p>
                <p className="text-xs text-slate-500 max-w-md mx-auto">
                  Clique no botão <span className="text-purple-300 font-semibold font-mono">"👁️ LIGAR CÂMERA OAK-D"</span> para ativar a visão remota.
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
                  <h3 className="text-base font-bold text-slate-200">Teleoperação Manual por D-Pad</h3>
                  <p className="text-xs text-slate-400">Controle de movimento direto (/cmd_vel_unstamped).</p>
                </div>
              </div>
              {isDocked && (
                <button
                  onClick={onUndock}
                  className="py-1.5 px-3 bg-amber-500/20 text-amber-300 border border-amber-500/40 rounded-lg text-xs font-bold hover:bg-amber-500/30 transition-all flex items-center gap-1"
                  title="O robô está encaixado na dock station. Clique para desencaixar as rodas."
                >
                  <Play className="w-3.5 h-3.5" />
                  <span>🚀 DESENCAIXAR DOCK (UNDOCK)</span>
                </button>
              )}
            </div>
            {isDocked && (
              <div className="mt-3 p-2.5 bg-amber-500/10 border border-amber-500/30 rounded-xl text-xs text-amber-300 flex items-center gap-2">
                <ShieldAlert className="w-4 h-4 text-amber-400 shrink-0" />
                <span><strong>Atenção:</strong> O robô está encaixado na Dock. Clique em <strong>UNDOCK</strong> acima para destravar os motores e mover livremente.</span>
              </div>
            )}
          </div>

          <div className="flex flex-col items-center justify-center py-4">
            <div className="grid grid-cols-3 gap-3 w-56">
              <div></div>
              <button
                onClick={() => handleSendTeleop(0.25, 0.0)}
                className="p-5 bg-slate-800 hover:bg-blue-600 active:bg-blue-700 text-white font-bold rounded-2xl border border-slate-700 shadow-lg flex items-center justify-center transition-all active:scale-90"
                title="Frente (linear_x = +0.25 m/s)"
              >
                <ArrowUp className="w-7 h-7" />
              </button>
              <div></div>

              <button
                onClick={() => handleSendTeleop(0.0, 0.6)}
                className="p-5 bg-slate-800 hover:bg-blue-600 active:bg-blue-700 text-white font-bold rounded-2xl border border-slate-700 shadow-lg flex items-center justify-center transition-all active:scale-90"
                title="Esquerda (angular_z = +0.6 rad/s)"
              >
                <ArrowLeft className="w-7 h-7" />
              </button>
              <button
                onClick={() => handleSendTeleop(0.0, 0.0)}
                className="p-5 bg-red-600/90 hover:bg-red-600 active:bg-red-700 text-white font-bold rounded-2xl border border-red-500 shadow-lg flex items-center justify-center transition-all active:scale-90"
                title="Parar Robô (Emergency Stop /cmd_vel)"
              >
                <Square className="w-7 h-7 fill-current" />
              </button>
              <button
                onClick={() => handleSendTeleop(0.0, -0.6)}
                className="p-5 bg-slate-800 hover:bg-blue-600 active:bg-blue-700 text-white font-bold rounded-2xl border border-slate-700 shadow-lg flex items-center justify-center transition-all active:scale-90"
                title="Direita (angular_z = -0.6 rad/s)"
              >
                <ArrowRight className="w-7 h-7" />
              </button>

              <div></div>
              <button
                onClick={() => handleSendTeleop(-0.25, 0.0)}
                className="p-5 bg-slate-800 hover:bg-blue-600 active:bg-blue-700 text-white font-bold rounded-2xl border border-slate-700 shadow-lg flex items-center justify-center transition-all active:scale-90"
                title="Ré (linear_x = -0.25 m/s)"
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
              <h3 className="text-base font-bold text-slate-100">Diagnóstico de Rede & Tópicos ROS 2</h3>
              <p className="text-xs text-slate-400">Verifica se a Raspberry Pi responde ao Ping e audita os tópicos visíveis no Discovery Server.</p>
            </div>
          </div>
          <button
            onClick={handleRunDiagnose}
            disabled={loadingDiag}
            className="py-2.5 px-4 bg-blue-600 hover:bg-blue-500 text-white font-bold rounded-xl shadow-lg flex items-center justify-center gap-2 transition-all active:scale-95 text-xs self-start sm:self-auto"
          >
            <Search className={`w-4 h-4 ${loadingDiag ? 'animate-spin' : ''}`} />
            {loadingDiag ? 'TESTANDO CONEXÃO...' : '🔍 AUDITAR CONEXÃO & TÓPICOS'}
          </button>
        </div>

        {tbDiag && (
          <div className="space-y-3 pt-1">
            <div className="flex flex-wrap items-center gap-3 text-xs">
              <span className={`px-3 py-1 rounded-full font-bold flex items-center gap-1.5 ${tbDiag.ping_ok ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' : 'bg-red-500/20 text-red-300 border border-red-500/30'}`}>
                {tbDiag.ping_ok ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> : <XCircle className="w-3.5 h-3.5 text-red-400" />}
                PING IP 192.168.0.129: {tbDiag.ping_ok ? 'ATIVO' : 'SEM RESPOSTA'}
              </span>

              <span className="px-3 py-1 bg-slate-800 text-slate-300 border border-slate-700 rounded-full font-mono text-[11px]">
                Discovery Server: {tbDiag.discovery_server} (Domain {tbDiag.domain_id})
              </span>

              <span className="px-3 py-1 bg-purple-500/20 text-purple-300 border border-purple-500/30 rounded-full font-bold text-xs flex items-center gap-1">
                <Activity className="w-3.5 h-3.5 text-purple-400" />
                {tbDiag.topics_count} Tópicos ROS 2 Encontrados
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
            Controle de Base de Carregamento (Docking)
          </h3>
          <p className="text-xs text-slate-400">Acione ações automáticas de alinhamento infravermelho com a estação de carga.</p>

          <div className="grid grid-cols-2 gap-3 pt-2">
            <button
              onClick={onDock}
              className="py-3 px-4 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold rounded-xl shadow-lg flex items-center justify-center gap-2 transition-all active:scale-95"
            >
              <Anchor className="w-4 h-4" />
              ⚡ DOCK (Ir Carga)
            </button>
            <button
              onClick={onUndock}
              className="py-3 px-4 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold rounded-xl shadow-lg flex items-center justify-center gap-2 transition-all active:scale-95"
            >
              <Play className="w-4 h-4" />
              🚀 UNDOCK (Sair Carga)
            </button>
          </div>
        </div>

        {/* Visão 3D Integrada (Cobot + TB4) */}
        <div className="glass-card p-5 rounded-xl border border-slate-700/60 space-y-4">
          <h3 className="text-base font-bold text-slate-200 flex items-center gap-2">
            <Layers className="w-5 h-5 text-purple-400" />
            Visualização 3D Integrada (Cobot + TB4)
          </h3>
          <p className="text-xs text-slate-400">Lança a cena 3D com o MyCobot 280 e o TurtleBot 4 juntos no mapa B002.</p>

          <div className="pt-2">
            <button
              onClick={onLaunchIntegrated3D}
              className="w-full py-3.5 px-4 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 text-white font-bold rounded-xl shadow-xl flex items-center justify-center gap-2 transition-all active:scale-95"
            >
              <Eye className="w-5 h-5" />
              🌐 ABRIR VISÃO 3D INTEGRADA (Cobot + TB4)
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
            Sequenciador de Inicialização Nav2
          </h3>
          <p className="text-xs text-slate-400">Execute os passos de lançamento do stack de navegação autônoma.</p>

          <div className="space-y-3 pt-1">
            <button
              onClick={() => {
                if (onLaunchLocalization) onLaunchLocalization();
                handleSelectLogSource('localization');
              }}
              className="w-full py-3 px-4 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-bold rounded-xl flex items-center justify-between transition-all active:scale-95"
            >
              <span className="flex items-center gap-2 text-sm">
                <MapPin className="w-4 h-4 text-emerald-400" />
                1. Iniciar Localização (Mapa B002)
              </span>
              <span className="text-xs text-slate-400 font-normal">localization.launch.py</span>
            </button>

            <button
              onClick={() => {
                if (onLaunchNav2) onLaunchNav2();
                handleSelectLogSource('nav2');
              }}
              className="w-full py-3 px-4 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-bold rounded-xl flex items-center justify-between transition-all active:scale-95"
            >
              <span className="flex items-center gap-2 text-sm">
                <Navigation className="w-4 h-4 text-amber-400" />
                2. Lançar Nav2 Stack (params_custom)
              </span>
              <span className="text-xs text-slate-400 font-normal">nav2.launch.py</span>
            </button>

            <button
              onClick={() => {
                if (onLaunchViz) onLaunchViz();
                handleSelectLogSource('viz');
              }}
              className="w-full py-3 px-4 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-bold rounded-xl flex items-center justify-between transition-all active:scale-95"
            >
              <span className="flex items-center gap-2 text-sm">
                <Eye className="w-4 h-4 text-blue-400" />
                3. Abrir RViz Nav2 (Tela Host)
              </span>
              <span className="text-xs text-slate-400 font-normal">view_navigation.launch.py</span>
            </button>
          </div>
        </div>

        {/* Gerenciador de Missões (Mission Manager) */}
        <div className="glass-card p-5 rounded-xl border border-slate-700/60 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-base font-bold text-slate-200 flex items-center gap-2">
              <Truck className="w-5 h-5 text-emerald-400" />
              Gerenciador Mestre de Missões
            </h3>
            <span className="text-[10px] px-2.5 py-1 bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 rounded-full font-mono font-bold">
              mission_manager.py
            </span>
          </div>
          <p className="text-xs text-slate-400">
            Inicia o nó principal em background (conecta câmera OAK-D + IA de visão) e aguarda o disparo das rotinas autônomas.
          </p>

          <button
            onClick={onLaunchMissionManager}
            className="w-full py-3 px-4 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold rounded-xl shadow-lg flex items-center justify-center gap-2 transition-all active:scale-95 text-sm"
          >
            <Play className="w-4.5 h-4.5 fill-current" />
            1. INICIAR NODE GERENCIADOR (waypoints.yaml + OAK-D)
          </button>

          <div className="border-t border-slate-700/60 pt-3">
            <p className="text-xs font-bold text-slate-300 mb-2">2. Disparar Rotina Autônoma:</p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <button
                onClick={onTriggerDelivery}
                className="py-3 px-2 bg-slate-800 hover:bg-blue-900/40 hover:border-blue-500/50 text-slate-100 font-bold rounded-xl border border-slate-700 flex flex-col items-center justify-center gap-1 transition-all text-xs"
                title="Undock -> Coleta em pickup_point -> Entrega -> Retorna ao Dock"
              >
                <Truck className="w-5 h-5 text-blue-400" />
                <span>/start_delivery</span>
                <span className="text-[10px] text-slate-400 font-normal">Entrega</span>
              </button>

              <button
                onClick={onTriggerFailure}
                className="py-3 px-2 bg-slate-800 hover:bg-red-900/40 hover:border-red-500/50 text-slate-100 font-bold rounded-xl border border-slate-700 flex flex-col items-center justify-center gap-1 transition-all text-xs"
                title="Undock -> Coleta em failure_pickup -> Zonas de Descarte -> Retorna ao Dock"
              >
                <ShieldAlert className="w-5 h-5 text-red-400" />
                <span>/start_failure</span>
                <span className="text-[10px] text-slate-400 font-normal">Descarte (Falha)</span>
              </button>

              <button
                onClick={onTriggerRestock}
                className="py-3 px-2 bg-slate-800 hover:bg-amber-900/40 hover:border-amber-500/50 text-slate-100 font-bold rounded-xl border border-slate-700 flex flex-col items-center justify-center gap-1 transition-all text-xs"
                title="Undock -> Coleta em restock_pickup -> Zonas de Reabastecimento -> Retorna ao Dock"
              >
                <Box className="w-5 h-5 text-amber-400" />
                <span>/start_restock</span>
                <span className="text-[10px] text-slate-400 font-normal">Reabastecimento</span>
              </button>

              <button
                onClick={onTriggerPatrol}
                className="py-3 px-2 bg-slate-800 hover:bg-purple-900/40 hover:border-purple-500/50 text-slate-100 font-bold rounded-xl border border-slate-700 flex flex-col items-center justify-center gap-1 transition-all text-xs"
                title="Ronda contínua pelos waypoints do laboratório B002"
              >
                <RefreshCw className="w-5 h-5 text-purple-400" />
                <span>/start_patrol</span>
                <span className="text-[10px] text-slate-400 font-normal">Patrulha / Ronda</span>
              </button>
            </div>

            {/* Botão de Emergência para Cancelamento de Missão */}
            <div className="pt-3">
              <button
                onClick={onStopMission}
                className="w-full py-3 px-4 bg-red-600/90 hover:bg-red-600 active:bg-red-700 text-white font-extrabold rounded-xl border border-red-500 shadow-lg flex items-center justify-center gap-2 transition-all active:scale-95 text-xs"
                title="Aborta a missão atual, cancela Nav2 e libera o Mission Manager"
              >
                <Square className="w-4 h-4 fill-current" />
                <span>🛑 CANCELAR / PARAR MISSÃO ATUAL (/stop_mission)</span>
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
            <h3 className="text-base font-bold text-slate-200">Terminal de Logs do Nav2 & Localização em Tempo Real</h3>
          </div>
          <div className="flex items-center gap-2">
            <div className="flex bg-slate-900/90 p-1 rounded-xl border border-slate-800 text-xs">
              <button
                onClick={() => handleSelectLogSource('localization')}
                className={"px-3 py-1 rounded-lg font-bold transition-all " + (logSource === 'localization' ? 'bg-blue-600 text-white shadow' : 'text-slate-400 hover:text-slate-200')}
              >
                🗺️ Localização (Mapa)
              </button>
              <button
                onClick={() => handleSelectLogSource('nav2')}
                className={"px-3 py-1 rounded-lg font-bold transition-all " + (logSource === 'nav2' ? 'bg-emerald-600 text-white shadow' : 'text-slate-400 hover:text-slate-200')}
              >
                🚀 Nav2 Stack
              </button>
              <button
                onClick={() => handleSelectLogSource('viz')}
                className={"px-3 py-1 rounded-lg font-bold transition-all " + (logSource === 'viz' ? 'bg-purple-600 text-white shadow' : 'text-slate-400 hover:text-slate-200')}
              >
                👁️ RViz2
              </button>
              <button
                onClick={() => handleSelectLogSource('all')}
                className={"px-3 py-1 rounded-lg font-bold transition-all " + (logSource === 'all' ? 'bg-slate-700 text-white shadow' : 'text-slate-400 hover:text-slate-200')}
              >
                📋 Todos
              </button>
            </div>
            <button
              onClick={() => fetchLogs(logSource)}
              disabled={loadingLogs}
              className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-emerald-400 font-extrabold text-xs rounded-lg border border-slate-700 flex items-center gap-1.5 transition-all active:scale-95"
            >
              <RefreshCw className={"w-3.5 h-3.5 " + (loadingLogs ? "animate-spin" : "")} />
              <span>Atualizar</span>
            </button>
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
              Nenhum log gravado ainda para a opção de console. Clique no botão de inicialização correspondente acima para iniciar o processo!
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

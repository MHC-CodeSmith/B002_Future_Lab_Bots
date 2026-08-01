import React, { useState } from 'react';
import { 
  Bot, Battery, Anchor, Navigation, MapPin, Play, Square, 
  ArrowUp, ArrowDown, ArrowLeft, ArrowRight, ShieldAlert,
  Box, Truck, RefreshCw, Eye, Layers, Compass
} from 'lucide-react';

export default function TurtleBotDashboardTab({ 
  tbStatus, 
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
  onLaunchIntegrated3D,
  onTeleop
}) {
  const isOnline = tbStatus?.status === 'ready';
  const batteryPct = tbStatus?.battery_percentage || 100;
  const isDocked = tbStatus?.is_docked !== false;
  const pose = tbStatus?.current_pose || { x: 0.0, y: 0.0, yaw: 0.0 };

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
            <span className={`text-xs px-3 py-1.5 rounded-full font-extrabold flex items-center gap-1.5 ${isOnline ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40' : 'bg-slate-700 text-slate-400'}`}>
              <span className={`w-2 h-2 rounded-full ${isOnline ? 'bg-emerald-400 animate-pulse' : 'bg-slate-500'}`}></span>
              {isOnline ? 'ONLINE (DDS Domain 0)' : 'AGUARDANDO CONEXÃO'}
            </span>
          </div>
        </div>

        {/* Cards de Métricas */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-5">
          <div className="p-4 bg-slate-800/80 rounded-xl border border-slate-700/60 flex items-center gap-3">
            <div className="p-3 bg-emerald-500/20 text-emerald-400 rounded-lg">
              <Battery className="w-6 h-6" />
            </div>
            <div>
              <p className="text-xs text-slate-400">Bateria</p>
              <p className="text-lg font-black text-slate-100">{batteryPct}%</p>
            </div>
          </div>

          <div className="p-4 bg-slate-800/80 rounded-xl border border-slate-700/60 flex items-center gap-3">
            <div className="p-3 bg-blue-500/20 text-blue-400 rounded-lg">
              <Anchor className="w-6 h-6" />
            </div>
            <div>
              <p className="text-xs text-slate-400">Estação de Carga</p>
              <p className="text-lg font-black text-slate-100">{isDocked ? 'Docked (Recarregando)' : 'Em Campo (Undocked)'}</p>
            </div>
          </div>

          <div className="p-4 bg-slate-800/80 rounded-xl border border-slate-700/60 flex items-center gap-3">
            <div className="p-3 bg-purple-500/20 text-purple-400 rounded-lg">
              <MapPin className="w-6 h-6" />
            </div>
            <div>
              <p className="text-xs text-slate-400">Coordenadas (Odom)</p>
              <p className="text-sm font-bold text-purple-300">X: {pose.x}m | Y: {pose.y}m</p>
            </div>
          </div>

          <div className="p-4 bg-slate-800/80 rounded-xl border border-slate-700/60 flex items-center gap-3">
            <div className="p-3 bg-amber-500/20 text-amber-400 rounded-lg">
              <Compass className="w-6 h-6" />
            </div>
            <div>
              <p className="text-xs text-slate-400">Status Nav2</p>
              <p className="text-sm font-bold text-amber-300">Pronto para Waypoints</p>
            </div>
          </div>
        </div>
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
              onClick={onLaunchLocalization}
              className="w-full py-3 px-4 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-bold rounded-xl flex items-center justify-between transition-all"
            >
              <span className="flex items-center gap-2 text-sm">
                <MapPin className="w-4 h-4 text-emerald-400" />
                1. Iniciar Localização (Mapa B002)
              </span>
              <span className="text-xs text-slate-400 font-normal">localization.launch.py</span>
            </button>

            <button
              onClick={onLaunchNav2}
              className="w-full py-3 px-4 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-bold rounded-xl flex items-center justify-between transition-all"
            >
              <span className="flex items-center gap-2 text-sm">
                <Navigation className="w-4 h-4 text-amber-400" />
                2. Lançar Nav2 Stack (params_custom)
              </span>
              <span className="text-xs text-slate-400 font-normal">nav2.launch.py</span>
            </button>

            <button
              onClick={onLaunchViz}
              className="w-full py-3 px-4 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-bold rounded-xl flex items-center justify-between transition-all"
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
          </div>
        </div>
      </div>

      {/* D-Pad Teleoperação Manual */}
      <div className="glass-card p-5 rounded-xl border border-slate-700/60 space-y-4">
        <h3 className="text-base font-bold text-slate-200 flex items-center gap-2">
          <Bot className="w-5 h-5 text-blue-400" />
          Teleoperação Manual por D-Pad (/cmd_vel)
        </h3>

        <div className="flex flex-col items-center justify-center py-2">
          <div className="grid grid-cols-3 gap-2 w-48">
            <div></div>
            <button
              onClick={() => handleSendTeleop(0.2, 0.0)}
              className="p-4 bg-slate-800 hover:bg-blue-600 text-white font-bold rounded-xl border border-slate-700 flex items-center justify-center transition-all active:scale-95"
            >
              <ArrowUp className="w-6 h-6" />
            </button>
            <div></div>

            <button
              onClick={() => handleSendTeleop(0.0, 0.5)}
              className="p-4 bg-slate-800 hover:bg-blue-600 text-white font-bold rounded-xl border border-slate-700 flex items-center justify-center transition-all active:scale-95"
            >
              <ArrowLeft className="w-6 h-6" />
            </button>
            <button
              onClick={() => handleSendTeleop(0.0, 0.0)}
              className="p-4 bg-red-600/80 hover:bg-red-600 text-white font-bold rounded-xl border border-red-500 flex items-center justify-center transition-all active:scale-95"
            >
              <Square className="w-6 h-6" />
            </button>
            <button
              onClick={() => handleSendTeleop(0.0, -0.5)}
              className="p-4 bg-slate-800 hover:bg-blue-600 text-white font-bold rounded-xl border border-slate-700 flex items-center justify-center transition-all active:scale-95"
            >
              <ArrowRight className="w-6 h-6" />
            </button>

            <div></div>
            <button
              onClick={() => handleSendTeleop(-0.2, 0.0)}
              className="p-4 bg-slate-800 hover:bg-blue-600 text-white font-bold rounded-xl border border-slate-700 flex items-center justify-center transition-all active:scale-95"
            >
              <ArrowDown className="w-6 h-6" />
            </button>
            <div></div>
          </div>
        </div>
      </div>
    </div>
  );
}

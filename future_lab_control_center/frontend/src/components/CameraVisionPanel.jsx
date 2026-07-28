import React, { useState, useEffect, useRef } from 'react';
import { Camera, Power, PowerOff, CheckCircle, AlertTriangle, RefreshCw, FlaskConical, Search, XCircle, Loader2 } from 'lucide-react';

export default function CameraVisionPanel({
  streamUrl,
  cameraOnline,
  lastYolo,
  pumpActive,
  yoloTestActive,
  onTogglePump,
  onToggleYoloTest,
  onRestartCamera,
  onStopCamera
}) {
  const [streamError, setStreamError] = useState(false);
  const [streamKey, setStreamKey] = useState(Date.now());
  const [restarting, setRestarting] = useState(false);
  const [stopping, setStopping] = useState(false);
  const retryTimers = useRef([]);

  const rawUrl = streamUrl || "http://192.168.0.250:8080/stream.mjpg";
  const liveUrl = `${rawUrl}${rawUrl.includes('?') ? '&' : '?'}t=${streamKey}`;

  // Tick do relógio a cada 500ms para forçar re-avaliação do isFresh
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setTick(k => k + 1), 500);
    return () => clearInterval(t);
  }, []);

  // Considera recente se a mensagem chegou nos últimos 10 segundos
  const isFresh = lastYolo && lastYolo.timestamp && Math.abs(Date.now() / 1000 - lastYolo.timestamp) < 10.0;

  const getDetectionBadge = () => {
    if (!isFresh || !lastYolo || !lastYolo.class) return null;
    const cls = (lastYolo.class || '').toLowerCase();
    const conf = (lastYolo.confidence * 100).toFixed(0);

    if (cls.includes('red') || cls.includes('vermelha') || cls.includes('triangle')) {
      return {
        bg: 'bg-red-950/90 border-red-500/70 text-red-200 shadow-red-900/50',
        dot: 'bg-red-500',
        label: `Lata Válida Vermelha (Triângulo) — ${conf}%`
      };
    }
    if (cls.includes('blue') || cls.includes('azul') || cls.includes('square')) {
      return {
        bg: 'bg-blue-950/90 border-blue-500/70 text-blue-200 shadow-blue-900/50',
        dot: 'bg-blue-500',
        label: `Lata Válida Azul (Quadrado) — ${conf}%`
      };
    }
    if (cls.includes('invalid') || cls.includes('rejeitada')) {
      return {
        bg: 'bg-amber-950/90 border-amber-500/70 text-amber-200 shadow-amber-900/50',
        dot: 'bg-amber-500',
        label: `Lata Inválida (Rejeitada) — ${conf}%`
      };
    }
    return {
      bg: 'bg-emerald-950/90 border-emerald-500/70 text-emerald-200 shadow-emerald-900/50',
      dot: 'bg-emerald-500',
      label: `Objeto Detectado (${lastYolo.class}) — ${conf}%`
    };
  };

  const badge = getDetectionBadge();
  const isBusy = restarting || stopping;

  return (
    <div className="glass-card p-5 rounded-xl space-y-4">
      <div className="flex flex-wrap items-center justify-between border-b border-slate-700 pb-3 gap-2">
        <h2 className="text-lg font-bold flex items-center gap-2">
          <Camera className="w-5 h-5 text-emerald-400" />
          Visão da Câmera & Classificação YOLO
        </h2>
        
        <div className="flex flex-wrap items-center gap-2">
          {/* Botão LIGAR / REINICIAR CÂMERA — contextual com base no estado */}
          <button
            onClick={handleStartOrRestart}
            disabled={isBusy}
            className={`px-3 py-1.5 text-xs font-bold rounded-lg flex items-center gap-1.5 btn-hover transition-all duration-150 ${
              isBusy
                ? 'bg-slate-700 text-slate-400 cursor-not-allowed border border-slate-600'
                : cameraOnline
                  ? 'bg-blue-600/30 hover:bg-blue-600 text-blue-300 border border-blue-500/40'
                  : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-900/30'
            }`}
            title={cameraOnline ? "Reiniciar servidor MJPEG na Jetson Nano" : "Ligar servidor MJPEG na Jetson Nano"}
          >
            {restarting ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                INICIALIZANDO...
              </>
            ) : cameraOnline ? (
              <>
                <RefreshCw className="w-3.5 h-3.5" />
                REINICIAR CÂMERA
              </>
            ) : (
              <>
                <Power className="w-3.5 h-3.5" />
                LIGAR CÂMERA
              </>
            )}
          </button>

          {/* Botão DESLIGAR CÂMERA — disponível apenas quando online */}
          <button
            onClick={handleStop}
            disabled={!cameraOnline || isBusy}
            className={`px-3 py-1.5 text-xs font-bold rounded-lg flex items-center gap-1.5 transition-all duration-150 ${
              !cameraOnline || isBusy
                ? 'bg-slate-800/50 text-slate-600 cursor-not-allowed border border-slate-700/50'
                : 'bg-red-600/30 hover:bg-red-600 text-red-300 border border-red-500/40 btn-hover'
            }`}
            title={!cameraOnline ? "Câmera já está desligada" : "Desligar servidor MJPEG na Jetson Nano"}
          >
            {stopping ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                DESLIGANDO...
              </>
            ) : (
              <>
                <PowerOff className="w-3.5 h-3.5" />
                DESLIGAR CÂMERA
              </>
            )}
          </button>

          {/* Botão de Toggle do Teste YOLO — Apenas ativável quando a câmera está LIGADA */}
          <button
            onClick={() => onToggleYoloTest(!yoloTestActive)}
            disabled={!cameraOnline || isBusy}
            className={`px-3 py-1.5 text-xs font-bold rounded-lg flex items-center gap-1.5 transition-all duration-150 ${
              !cameraOnline || isBusy
                ? 'bg-slate-800/50 text-slate-600 cursor-not-allowed border border-slate-700/50'
                : yoloTestActive
                  ? 'bg-red-600 hover:bg-red-500 text-white shadow-lg shadow-red-900/40 btn-hover'
                  : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-900/30 btn-hover'
            }`}
            title={!cameraOnline ? "Ligue a câmera antes de iniciar o teste do YOLO" : yoloTestActive ? "Desligar teste isolado do YOLO" : "Iniciar teste isolado de classificação do YOLO"}
          >
            <FlaskConical className={`w-3.5 h-3.5 ${yoloTestActive ? 'animate-pulse' : ''}`} />
            {yoloTestActive ? 'DESLIGAR TESTE YOLO' : 'TESTAR YOLO'}
          </button>

          {/* Botão de Toggle da Bomba */}
          <button
            onClick={() => onTogglePump(!pumpActive)}
            className={`px-3 py-1.5 text-xs font-bold rounded-lg btn-hover flex items-center gap-1.5 transition-all duration-150 ${
              pumpActive
                ? 'bg-red-600 hover:bg-red-500 text-white shadow-lg shadow-red-900/40'
                : 'bg-emerald-600 hover:bg-emerald-500 text-white'
            }`}
          >
            <Power className="w-3.5 h-3.5" />
            {pumpActive ? 'DESLIGAR BOMBA' : 'LIGAR BOMBA'}
          </button>
        </div>
      </div>

      {/* Video Feed MJPEG */}
      <div className="relative aspect-video bg-slate-900 rounded-xl overflow-hidden border border-slate-800 flex items-center justify-center">
        {restarting ? (
          <div className="text-center p-6 space-y-3">
            <Loader2 className="w-10 h-10 text-blue-400 mx-auto animate-spin" />
            <p className="text-sm font-semibold text-slate-200">Inicializando Servidor de Câmera na Jetson Nano...</p>
            <p className="text-xs text-slate-400">Liberando hardware USB /dev/video0 e iniciando stream MJPEG (~6s).</p>
          </div>
        ) : stopping ? (
          <div className="text-center p-6 space-y-3">
            <Loader2 className="w-10 h-10 text-red-400 mx-auto animate-spin" />
            <p className="text-sm font-semibold text-slate-200">Desligando Servidor de Câmera...</p>
            <p className="text-xs text-slate-400">Encerrando o processo na Jetson Nano.</p>
          </div>
        ) : !streamError ? (
          <img
            key={streamKey}
            src={liveUrl}
            alt="Feed ao vivo da Câmera Jetson Nano"
            onError={() => {
              if (!restarting && !stopping) setStreamError(true);
            }}
            className="w-full h-full object-contain"
          />
        ) : (
          <div className="text-center p-6 space-y-2">
            <AlertTriangle className="w-10 h-10 text-amber-400 mx-auto animate-bounce" />
            <p className="text-sm font-semibold text-slate-300">
              {cameraOnline ? 'Reconectando ao Stream...' : 'Câmera Desligada'}
            </p>
            <p className="text-xs text-slate-500">
              {cameraOnline
                ? 'Tentando reconectar automaticamente a cada 3 segundos...'
                : 'Clique em "LIGAR CÂMERA" para iniciar o servidor MJPEG na Jetson Nano.'
              }
            </p>
            {!cameraOnline && (
              <button
                onClick={handleStartOrRestart}
                disabled={isBusy}
                className="mt-2 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-xs font-bold rounded-lg flex items-center gap-1 mx-auto text-white"
              >
                <Power className="w-3.5 h-3.5" />
                Ligar Câmera no Nano (SSH)
              </button>
            )}
          </div>
        )}

        {/* Overlay de Status do Teste YOLO */}
        {yoloTestActive && !isBusy && (
          <div className="absolute top-3 right-3 bg-emerald-950/90 backdrop-blur border border-emerald-500/60 px-3 py-1.5 rounded-lg flex items-center gap-2 shadow-lg">
            <FlaskConical className="w-4 h-4 text-emerald-400 animate-spin" />
            <span className="text-xs font-bold text-emerald-300">MODO TESTE YOLO ATIVO</span>
          </div>
        )}

        {/* Overlay de Rótulo YOLO ao vivo */}
        {isFresh && badge && !isBusy && (
          <div className={`absolute top-3 left-3 backdrop-blur border px-3 py-2 rounded-lg flex items-center gap-2 shadow-lg ${badge.bg}`}>
            <span className={`w-2.5 h-2.5 rounded-full ${badge.dot} animate-ping`} />
            <div>
              <p className="text-[10px] text-slate-300 uppercase tracking-wider font-semibold">Detecção ao Vivo:</p>
              <p className="text-xs font-bold">{badge.label}</p>
            </div>
          </div>
        )}
      </div>

      {/* Card de Status da Classificação Atual */}
      <div className="p-3.5 bg-slate-800/60 rounded-xl border border-slate-700/50 flex flex-wrap items-center justify-between text-sm gap-2">
        <span className="text-slate-400 font-medium">Classificação Atual:</span>
        
        {restarting ? (
          <span className="font-bold text-blue-400 flex items-center gap-1.5 bg-blue-950/40 px-3 py-1 rounded-lg border border-blue-500/30">
            <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />
            Inicializando câmera...
          </span>
        ) : stopping ? (
          <span className="font-bold text-red-400 flex items-center gap-1.5 bg-red-950/40 px-3 py-1 rounded-lg border border-red-500/30">
            <Loader2 className="w-4 h-4 text-red-400 animate-spin" />
            Desligando câmera...
          </span>
        ) : isFresh && badge ? (
          <span className="font-bold text-emerald-400 flex items-center gap-1.5 bg-emerald-950/40 px-3 py-1 rounded-lg border border-emerald-500/30">
            <CheckCircle className="w-4 h-4 text-emerald-400" />
            {badge.label}
          </span>
        ) : yoloTestActive ? (
          <span className="font-bold text-amber-400 flex items-center gap-1.5 bg-amber-950/40 px-3 py-1 rounded-lg border border-amber-500/30 animate-pulse">
            <Search className="w-4 h-4 text-amber-400 animate-spin" />
            Nenhuma lata identificada no campo de visão
          </span>
        ) : (
          <span className="text-slate-500 italic flex items-center gap-1">
            <XCircle className="w-4 h-4 text-slate-600" />
            Aguardando ativação do Teste YOLO ou scan da célula...
          </span>
        )}
      </div>
    </div>
  );
}

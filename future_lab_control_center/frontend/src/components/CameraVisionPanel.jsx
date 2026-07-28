import React, { useState, useEffect, useRef } from 'react';
import { Camera, Eye, Power, CheckCircle, AlertTriangle, RefreshCw, FlaskConical, Search, XCircle, Loader2 } from 'lucide-react';

export default function CameraVisionPanel({
  streamUrl,
  lastYolo,
  pumpActive,
  yoloTestActive,
  onTogglePump,
  onToggleYoloTest,
  onRestartCamera
}) {
  const [streamError, setStreamError] = useState(false);
  const [streamKey, setStreamKey] = useState(Date.now());
  const [restarting, setRestarting] = useState(false);
  const retryTimers = useRef([]);

  const rawUrl = streamUrl || "http://192.168.0.250:8080/stream.mjpg";
  const liveUrl = `${rawUrl}${rawUrl.includes('?') ? '&' : '?'}t=${streamKey}`;

  // Verifica se a última mensagem do YOLO é recente (últimos 2.5 segundos)
  const isFresh = lastYolo && (Date.now() / 1000 - (lastYolo.timestamp || 0)) < 2.5;

  // Auto-recovery: quando o stream está em erro e NÃO estamos reiniciando,
  // tenta reconectar a cada 3 segundos automaticamente
  useEffect(() => {
    if (streamError && !restarting) {
      const interval = setInterval(() => {
        setStreamError(false);
        setStreamKey(Date.now());
      }, 3000);
      return () => clearInterval(interval);
    }
  }, [streamError, restarting]);

  const handleRefreshStream = async () => {
    // Limpa timers anteriores
    retryTimers.current.forEach(t => clearTimeout(t));
    retryTimers.current = [];

    setRestarting(true);
    setStreamError(false);
    
    if (onRestartCamera) {
      try {
        await onRestartCamera();
      } catch (e) {
        console.warn("Erro ao reiniciar câmera:", e);
      }
    }
    
    // Múltiplas tentativas de reconexão: 7s, 10s, 13s, 16s após disparo
    // O servidor Nano demora ~6-8s para inicializar (scp + pkill + sleep 2 + python + HTTP checks)
    const retryDelays = [7000, 10000, 13000, 16000];
    retryDelays.forEach((delay, i) => {
      const timer = setTimeout(() => {
        setStreamError(false);
        setStreamKey(Date.now());
        // Na última tentativa, desliga o estado de "reiniciando"
        if (i === retryDelays.length - 1) {
          setRestarting(false);
        }
      }, delay);
      retryTimers.current.push(timer);
    });
  };

  const getDetectionBadge = () => {
    if (!isFresh || !lastYolo) return null;
    const cls = (lastYolo.class || '').toLowerCase();
    const conf = (lastYolo.confidence * 100).toFixed(0);

    if (cls.includes('red')) {
      return {
        bg: 'bg-red-950/90 border-red-500/70 text-red-200',
        dot: 'bg-red-500',
        label: `Lata Válida Vermelha (Triângulo) — ${conf}%`
      };
    }
    if (cls.includes('blue')) {
      return {
        bg: 'bg-blue-950/90 border-blue-500/70 text-blue-200',
        dot: 'bg-blue-500',
        label: `Lata Válida Azul (Quadrado) — ${conf}%`
      };
    }
    return {
      bg: 'bg-amber-950/90 border-amber-500/70 text-amber-200',
      dot: 'bg-amber-500',
      label: `Lata Inválida (Rejeitada) — ${conf}%`
    };
  };

  const badge = getDetectionBadge();

  return (
    <div className="glass-card p-5 rounded-xl space-y-4">
      <div className="flex flex-wrap items-center justify-between border-b border-slate-700 pb-3 gap-2">
        <h2 className="text-lg font-bold flex items-center gap-2">
          <Camera className="w-5 h-5 text-emerald-400" />
          Visão da Câmera & Classificação YOLO
        </h2>
        
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={handleRefreshStream}
            disabled={restarting}
            className="px-3 py-1.5 text-xs font-bold rounded-lg bg-blue-600/30 hover:bg-blue-600 text-blue-300 border border-blue-500/40 flex items-center gap-1.5 btn-hover"
            title="Executar RUN_NANO_CAMERA.sh start via SSH na Jetson Nano"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${restarting ? 'animate-spin' : ''}`} />
            {restarting ? 'INICIALIZANDO NANO...' : 'REINICIAR CÂMERA'}
          </button>

          {/* Botão de Toggle do Teste YOLO */}
          <button
            onClick={() => onToggleYoloTest(!yoloTestActive)}
            className={`px-3 py-1.5 text-xs font-bold rounded-lg btn-hover flex items-center gap-1.5 transition-all duration-150 ${
              yoloTestActive
                ? 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-900/40 animate-pulse'
                : 'bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700'
            }`}
          >
            <FlaskConical className="w-3.5 h-3.5" />
            {yoloTestActive ? 'TESTE YOLO: LIGADO' : 'TESTAR YOLO'}
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

      {/* Video Feed MJPEG com chave dinâmica anticache */}
      <div className="relative aspect-video bg-slate-900 rounded-xl overflow-hidden border border-slate-800 flex items-center justify-center">
        {restarting ? (
          <div className="text-center p-6 space-y-3">
            <Loader2 className="w-10 h-10 text-blue-400 mx-auto animate-spin" />
            <p className="text-sm font-semibold text-slate-200">Inicializando Servidor de Câmera na Jetson Nano...</p>
            <p className="text-xs text-slate-400">Liberando hardware USB /dev/video0 e iniciando stream MJPEG (~6s).</p>
          </div>
        ) : !streamError ? (
          <img
            key={streamKey}
            src={liveUrl}
            alt="Feed ao vivo da Câmera Jetson Nano"
            onError={() => {
              if (!restarting) setStreamError(true);
            }}
            className="w-full h-full object-contain"
          />
        ) : (
          <div className="text-center p-6 space-y-2">
            <AlertTriangle className="w-10 h-10 text-amber-400 mx-auto animate-bounce" />
            <p className="text-sm font-semibold text-slate-300">Stream da Câmera Indisponível</p>
            <p className="text-xs text-slate-500">Clique no botão abaixo para disparar a inicialização remota na Jetson Nano ({rawUrl}).</p>
            <button
              onClick={handleRefreshStream}
              disabled={restarting}
              className="mt-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-xs font-bold rounded-lg flex items-center gap-1 mx-auto"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${restarting ? 'animate-spin' : ''}`} />
              {restarting ? 'INICIALIZANDO NANO...' : 'Disparar Câmera no Nano (SSH)'}
            </button>
          </div>
        )}

        {/* Overlay de Status do Teste YOLO */}
        {yoloTestActive && !restarting && (
          <div className="absolute top-3 right-3 bg-emerald-950/90 backdrop-blur border border-emerald-500/60 px-3 py-1.5 rounded-lg flex items-center gap-2 shadow-lg">
            <FlaskConical className="w-4 h-4 text-emerald-400 animate-spin" />
            <span className="text-xs font-bold text-emerald-300">MODO TESTE YOLO ATIVO</span>
          </div>
        )}

        {/* Overlay de Rótulo YOLO ao vivo */}
        {isFresh && badge && !restarting && (
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
            Reiniciando stream da câmera...
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

import React, { useState } from 'react';
import { Camera, Eye, Power, CheckCircle, AlertTriangle, RefreshCw } from 'lucide-react';

export default function CameraVisionPanel({ streamUrl, lastYolo, pumpActive, onTogglePump, onRestartCamera }) {
  const [streamError, setStreamError] = useState(false);
  const [streamKey, setStreamKey] = useState(Date.now());
  const [restarting, setRestarting] = useState(false);

  const rawUrl = streamUrl || "http://192.168.0.250:8080/stream.mjpg";
  const liveUrl = `${rawUrl}${rawUrl.includes('?') ? '&' : '?'}t=${streamKey}`;

  const handleRefreshStream = async () => {
    setRestarting(true);
    setStreamError(false);
    setStreamKey(Date.now());
    if (onRestartCamera) {
      try {
        await onRestartCamera();
      } catch (e) {
        console.warn("Erro ao reiniciar câmera:", e);
      }
    }
    setTimeout(() => setRestarting(false), 1500);
  };

  return (
    <div className="glass-card p-5 rounded-xl space-y-4">
      <div className="flex flex-wrap items-center justify-between border-b border-slate-700 pb-3 gap-2">
        <h2 className="text-lg font-bold flex items-center gap-2">
          <Camera className="w-5 h-5 text-emerald-400" />
          Visão da Câmera & Classificação YOLO
        </h2>
        
        <div className="flex items-center gap-2">
          <button
            onClick={handleRefreshStream}
            disabled={restarting}
            className="px-3 py-1 text-xs font-bold rounded-lg bg-blue-600/30 hover:bg-blue-600 text-blue-300 border border-blue-500/40 flex items-center gap-1.5 btn-hover"
            title="Reiniciar Câmera & Recarregar Stream MJPEG"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${restarting ? 'animate-spin' : ''}`} />
            REINICIAR CÂMERA
          </button>

          <button
            onClick={() => onTogglePump(!pumpActive)}
            className={`px-3 py-1 text-xs font-bold rounded-lg btn-hover ${pumpActive ? 'bg-red-600 hover:bg-red-500 text-white' : 'bg-emerald-600 hover:bg-emerald-500 text-white'}`}
          >
            {pumpActive ? 'DESLIGAR BOMBA' : 'LIGAR BOMBA'}
          </button>
        </div>
      </div>

      {/* Video Feed MJPEG com chave dinâmica anticache */}
      <div className="relative aspect-video bg-slate-900 rounded-xl overflow-hidden border border-slate-800 flex items-center justify-center">
        {!streamError ? (
          <img
            key={streamKey}
            src={liveUrl}
            alt="Feed ao vivo da Câmera Jetson Nano"
            onError={() => setStreamError(true)}
            className="w-full h-full object-contain"
          />
        ) : (
          <div className="text-center p-6 space-y-2">
            <AlertTriangle className="w-10 h-10 text-amber-400 mx-auto animate-bounce" />
            <p className="text-sm font-semibold text-slate-300">Stream da Câmera Indisponível</p>
            <p className="text-xs text-slate-500">Verifique se o script da câmera está rodando na Jetson Nano ({rawUrl}).</p>
            <button
              onClick={handleRefreshStream}
              className="mt-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-xs font-bold rounded-lg flex items-center gap-1 mx-auto"
            >
              <RefreshCw className="w-3.5 h-3.5" /> Reconectar Stream MJPEG
            </button>
          </div>
        )}

        {/* Overlay de Rótulo YOLO */}
        {lastYolo && (
          <div className="absolute top-3 left-3 bg-slate-950/80 backdrop-blur border border-emerald-500/50 px-3 py-2 rounded-lg flex items-center gap-2">
            <Eye className="w-4 h-4 text-emerald-400 animate-pulse" />
            <div>
              <p className="text-xs text-slate-400">Última Detecção:</p>
              <p className="text-sm font-bold text-emerald-300 uppercase">
                {lastYolo.class} ({(lastYolo.confidence * 100).toFixed(0)}%)
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Card de Leitura da Classe */}
      <div className="p-3 bg-slate-800/60 rounded-xl border border-slate-700/50 flex items-center justify-between text-sm">
        <span className="text-slate-400">Classificação Atual:</span>
        {lastYolo ? (
          <span className="font-bold text-emerald-400 flex items-center gap-1">
            <CheckCircle className="w-4 h-4" />
            {lastYolo.class} (Confiança: {(lastYolo.confidence * 100).toFixed(0)}%)
          </span>
        ) : (
          <span className="text-slate-500 italic">Aguardando scan na posição...</span>
        )}
      </div>
    </div>
  );
}

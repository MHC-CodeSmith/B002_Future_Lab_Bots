import React, { useState } from 'react';
import { Camera, Eye, Power, CheckCircle, AlertTriangle, RefreshCw, FlaskConical } from 'lucide-react';

export default function CameraVisionPanel({ streamUrl, lastYolo, pumpActive, yoloTestActive, onTogglePump, onToggleYoloTest, onRestartCamera }) {
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
    setTimeout(() => setRestarting(false), 2000);
  };

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
            title="Reiniciar Servidor MJPEG na Jetson Nano"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${restarting ? 'animate-spin' : ''}`} />
            {restarting ? 'REINICIANDO...' : 'REINICIAR CÂMERA'}
          </button>

          {/* Botão de Toggle do Teste YOLO (Estilo do Botão da Bomba) */}
          <button
            onClick={() => onToggleYoloTest(!yoloTestActive)}
            className={`px-3 py-1.5 text-xs font-bold rounded-lg btn-hover flex items-center gap-1.5 ${
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
            className={`px-3 py-1.5 text-xs font-bold rounded-lg btn-hover flex items-center gap-1.5 ${
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
            <p className="text-xs text-slate-500">Clique no botão abaixo para disparar a inicialização remota na Jetson Nano ({rawUrl}).</p>
            <button
              onClick={handleRefreshStream}
              className="mt-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-xs font-bold rounded-lg flex items-center gap-1 mx-auto"
            >
              <RefreshCw className="w-3.5 h-3.5" /> Disparar Câmera no Nano (SSH)
            </button>
          </div>
        )}

        {/* Overlay de Status do Teste YOLO */}
        {yoloTestActive && (
          <div className="absolute top-3 right-3 bg-emerald-950/80 backdrop-blur border border-emerald-500/60 px-3 py-1.5 rounded-lg flex items-center gap-2">
            <FlaskConical className="w-4 h-4 text-emerald-400 animate-spin" />
            <span className="text-xs font-bold text-emerald-300">MODO TESTE YOLO ATIVO</span>
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
          <span className="text-slate-500 italic">
            {yoloTestActive ? 'Analisando imagem em qualquer posição...' : 'Aguardando teste do YOLO ou scan...'}
          </span>
        )}
      </div>
    </div>
  );
}

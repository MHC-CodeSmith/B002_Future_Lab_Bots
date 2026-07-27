import React, { useState } from 'react';
import { Camera, Eye, Power, CheckCircle, AlertTriangle } from 'lucide-react';

export default function CameraVisionPanel({ streamUrl, lastYolo, pumpActive, onTogglePump }) {
  const [streamError, setStreamError] = useState(false);

  return (
    <div className="glass-card p-5 rounded-xl space-y-4">
      <div className="flex items-center justify-between border-b border-slate-700 pb-3">
        <h2 className="text-lg font-bold flex items-center gap-2">
          <Camera className="w-5 h-5 text-emerald-400" />
          Visão da Câmera & Classificação YOLO
        </h2>
        <div className="flex items-center gap-2">
          <span className={`text-xs px-2.5 py-1 rounded-full font-bold flex items-center gap-1 ${pumpActive ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40' : 'bg-slate-700 text-slate-400'}`}>
            <Power className="w-3 h-3" />
            BOMBA: {pumpActive ? 'LIGADA' : 'DESLIGADA'}
          </span>
          <button
            onClick={() => onTogglePump(!pumpActive)}
            className={`px-3 py-1 text-xs font-bold rounded-lg btn-hover ${pumpActive ? 'bg-red-600 hover:bg-red-500 text-white' : 'bg-emerald-600 hover:bg-emerald-500 text-white'}`}
          >
            {pumpActive ? 'DESLIGAR BOMBA' : 'LIGAR BOMBA'}
          </button>
        </div>
      </div>

      {/* Video Feed MJPEG */}
      <div className="relative aspect-video bg-slate-900 rounded-xl overflow-hidden border border-slate-800 flex items-center justify-center">
        {!streamError ? (
          <img
            src={streamUrl || "http://192.168.0.250:8080/stream.mjpg"}
            alt="Feed ao vivo da Câmera Jetson Nano"
            onError={() => setStreamError(true)}
            className="w-full h-full object-contain"
          />
        ) : (
          <div className="text-center p-6 space-y-2">
            <AlertTriangle className="w-10 h-10 text-amber-400 mx-auto animate-bounce" />
            <p className="text-sm font-semibold text-slate-300">Stream da Câmera Indisponível</p>
            <p className="text-xs text-slate-500">Verifique se o script da câmera está rodando na Jetson Nano ({streamUrl}).</p>
            <button
              onClick={() => setStreamError(false)}
              className="mt-2 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-xs font-bold rounded-lg"
            >
              Reconectar Stream
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

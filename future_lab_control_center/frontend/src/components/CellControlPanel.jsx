import React, { useState } from 'react';
import { Play, Pause, AlertOctagon, RefreshCw, Sliders, CheckCircle } from 'lucide-react';

export default function CellControlPanel({ cellState, onUpdateMode, onAuthorizeScan, onEmergencyStop }) {
  const [mode, setMode] = useState(cellState?.mode || 'auto');
  const [cooldown, setCooldown] = useState(cellState?.cooldown_sec || 5.0);
  const [conf, setConf] = useState((cellState?.yolo_conf || 0.60) * 100);
  const [authorized, setAuthorized] = useState(false);

  const handleModeChange = (newMode) => {
    setMode(newMode);
    onUpdateMode({ mode: newMode, cooldown_sec: cooldown, yolo_conf: conf / 100 });
  };

  const handleSliderChange = (newCooldown, newConf) => {
    setCooldown(newCooldown);
    setConf(newConf);
    onUpdateMode({ mode, cooldown_sec: newCooldown, yolo_conf: newConf / 100 });
  };

  const handleAuthorize = () => {
    setAuthorized(true);
    onAuthorizeScan();
    setTimeout(() => setAuthorized(false), 3000);
  };

  return (
    <div className="glass-card p-5 rounded-xl space-y-6">
      <div className="flex items-center justify-between border-b border-slate-700 pb-3">
        <h2 className="text-lg font-bold flex items-center gap-2">
          <Sliders className="w-5 h-5 text-blue-400" />
          Controle Mestre da Célula
        </h2>
        <span className={`px-3 py-1 text-xs font-bold rounded-full ${mode === 'auto' ? 'bg-blue-500/20 text-blue-400' : 'bg-amber-500/20 text-amber-400'}`}>
          MODO: {mode.toUpperCase()}
        </span>
      </div>

      {/* Botões Mestre de Operação */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <button
          onClick={() => handleModeChange('auto')}
          className="flex items-center justify-center gap-2 py-3 px-4 bg-emerald-600 hover:bg-emerald-500 font-bold rounded-xl btn-hover shadow-lg shadow-emerald-900/30"
        >
          <Play className="w-5 h-5 fill-current" />
          MODO AUTOMÁTICO
        </button>

        <button
          onClick={() => handleModeChange('manual')}
          className="flex items-center justify-center gap-2 py-3 px-4 bg-amber-600 hover:bg-amber-500 font-bold rounded-xl btn-hover shadow-lg shadow-amber-900/30"
        >
          <Pause className="w-5 h-5 fill-current" />
          MODO MANUAL
        </button>

        <button
          onClick={onEmergencyStop}
          className="flex items-center justify-center gap-2 py-3 px-4 bg-red-600 hover:bg-red-500 font-bold rounded-xl btn-hover shadow-lg shadow-red-900/40"
        >
          <AlertOctagon className="w-5 h-5" />
          EMERGÊNCIA (HOME)
        </button>
      </div>

      {/* Botão de Liberação do Scan no Modo Manual */}
      {mode === 'manual' && (
        <div className="p-4 bg-amber-500/10 border border-amber-500/30 rounded-xl space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-amber-300">
              👉 Modo Manual Ativo: O robô aguarda autorização para o próximo scan.
            </span>
            <button
              onClick={handleAuthorize}
              disabled={authorized}
              className={`px-4 py-2 text-xs font-bold rounded-lg flex items-center gap-2 ${authorized ? 'bg-emerald-600 text-white' : 'bg-amber-500 hover:bg-amber-400 text-slate-950 btn-hover'}`}
            >
              {authorized ? <CheckCircle className="w-4 h-4" /> : <RefreshCw className="w-4 h-4" />}
              {authorized ? 'SCAN AUTORIZADO!' : 'AUTORIZAR PRÓXIMO SCAN'}
            </button>
          </div>
        </div>
      )}

      {/* Sliders Dinâmicos de Parâmetros */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-2">
        {/* Slider de Cooldown */}
        <div className="space-y-2 bg-slate-800/50 p-4 rounded-xl border border-slate-700/50">
          <div className="flex justify-between text-sm">
            <span className="text-slate-300 font-medium">Cooldown Pós-Coleta (Auto)</span>
            <span className="font-bold text-blue-400">{cooldown}s</span>
          </div>
          <input
            type="range"
            min="1.0"
            max="10.0"
            step="0.5"
            value={cooldown}
            onChange={(e) => handleSliderChange(parseFloat(e.target.value), conf)}
            className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
          />
          <p className="text-xs text-slate-400">Tempo de pausa entre entregas no modo automático para evitar acúmulo.</p>
        </div>

        {/* Slider de Confiança YOLO */}
        <div className="space-y-2 bg-slate-800/50 p-4 rounded-xl border border-slate-700/50">
          <div className="flex justify-between text-sm">
            <span className="text-slate-300 font-medium">Confiança Mínima YOLO</span>
            <span className="font-bold text-emerald-400">{conf}%</span>
          </div>
          <input
            type="range"
            min="30"
            max="90"
            step="5"
            value={conf}
            onChange={(e) => handleSliderChange(cooldown, parseFloat(e.target.value))}
            className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-emerald-500"
          />
          <p className="text-xs text-slate-400">Limiar mínimo para validar detecção de latas (Recomendado: 60%).</p>
        </div>
      </div>
    </div>
  );
}

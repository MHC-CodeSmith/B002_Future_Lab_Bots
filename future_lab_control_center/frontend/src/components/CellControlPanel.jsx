import React, { useState } from 'react';
import { Play, Pause, AlertOctagon, RefreshCw, Sliders, CheckCircle, Flame, Cpu, Loader2, PauseCircle, Check, X } from 'lucide-react';
import { useLanguage } from '../context/LanguageContext';

export default function CellControlPanel({
  cellState,
  onUpdateMode,
  onAutoStart,
  onAutoStop,
  onManualStartScan,
  onManualAuthorizePick,
  onManualAuthorizePlace,
  onInterrupt,
  onEmergencyStop,
  onPanicStop,
  onRestartNanoHardware,
  onTestHandshake
}) {
  const { t } = useLanguage();
  const [mode, setMode] = useState(cellState?.mode || 'auto');
  const [cooldown, setCooldown] = useState(cellState?.cooldown_sec || 5.0);
  const [conf, setConf] = useState((cellState?.yolo_conf || 0.60) * 100);
  const [speedPct, setSpeedPct] = useState(Math.round((cellState?.arm_speed || 0.15) * 100));
  const [restartingHw, setRestartingHw] = useState(false);

  React.useEffect(() => {
    if (cellState?.mode) {
      setMode(cellState.mode);
    }
    if (cellState?.arm_speed !== undefined) {
      setSpeedPct(Math.round(cellState.arm_speed * 100));
    }
  }, [cellState?.mode, cellState?.arm_speed]);

  const handleModeChange = (newMode) => {
    setMode(newMode);
    onUpdateMode({ mode: newMode, cooldown_sec: cooldown, yolo_conf: conf / 100, arm_speed: speedPct / 100 });
  };

  const handleAutoClick = () => {
    handleModeChange('auto');
    if (onAutoStart) onAutoStart();
  };

  const handleSliderChange = (newCooldown, newConf, newSpeedPct) => {
    setCooldown(newCooldown);
    setConf(newConf);
    setSpeedPct(newSpeedPct);
    onUpdateMode({ mode, cooldown_sec: newCooldown, yolo_conf: newConf / 100, arm_speed: newSpeedPct / 100 });
  };

  const handleRestartHw = async () => {
    setRestartingHw(true);
    try {
      if (onRestartNanoHardware) await onRestartNanoHardware();
    } finally {
      setTimeout(() => setRestartingHw(false), 4000);
    }
  };

  const status = cellState?.status || 'idle';
  const detectedItem = cellState?.yolo_detected_item;

  // Lógica dinâmica: Se o modo manual estiver ATIVO (ou se um ciclo estiver rodando), o botão vira "INTERROMPER"
  const isManualActive = mode === 'manual';
  const isCycleRunning = status !== 'idle' && status !== 'stopped' && status !== 'panic_locked';
  const isAutoRunning = mode === 'auto' && isCycleRunning;

  return (
    <div className="glass-card p-5 rounded-xl space-y-6 relative">
      <div className="flex items-center justify-between border-b border-slate-700 pb-3">
        <h2 className="text-lg font-bold flex items-center gap-2">
          <Sliders className="w-5 h-5 text-blue-400" />
          {t('cellMasterControl')}
        </h2>
        <div className="flex items-center gap-2">
          <button
            onClick={handleRestartHw}
            disabled={restartingHw}
            className="px-3 py-1 bg-red-600 hover:bg-red-500 text-white border border-red-500 text-xs font-bold rounded-lg flex items-center gap-1.5 transition-colors shadow-md shadow-red-950/60"
            title={t('restartNanoTitle')}
          >
            {restartingHw ? <Loader2 className="w-3.5 h-3.5 animate-spin text-white" /> : <Flame className="w-3.5 h-3.5 text-white fill-current" />}
            {restartingHw ? t('restartingNano') : t('btnRestartNanoHw')}
          </button>

          <span className={`px-3 py-1 text-xs font-bold rounded-full ${mode === 'auto' ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30' : 'bg-amber-500/20 text-amber-400 border border-amber-500/30'}`}>
            {t('modeBadge')} {mode.toUpperCase()}
          </span>
        </div>
      </div>

      {/* Botões Mestre de Operação (3 Botões) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {/* Botão Modo Auto */}
        <button
          onClick={handleAutoClick}
          className={`flex items-center justify-center gap-2 py-3.5 px-3 font-bold rounded-xl btn-hover text-xs md:text-sm ${mode === 'auto' ? 'bg-blue-600 hover:bg-blue-500 text-white shadow-lg shadow-blue-900/40 ring-2 ring-blue-400' : 'bg-slate-800 hover:bg-slate-700 text-slate-300'}`}
          title={t('modeDescriptionAuto')}
        >
          {isAutoRunning ? <Loader2 className="w-4 h-4 animate-spin text-white" /> : <Play className="w-4 h-4 fill-current" />}
          {isAutoRunning ? t('autoRunningBtn') : t('startAutoBtn')}
        </button>

        {/* Botão Dinâmico Modo Manual / Interromper */}
        {isManualActive || isCycleRunning ? (
          <button
            onClick={onInterrupt}
            className="flex items-center justify-center gap-2 py-3.5 px-3 bg-orange-600 hover:bg-orange-500 text-white font-bold rounded-xl btn-hover shadow-lg shadow-orange-900/50 animate-pulse text-xs md:text-sm ring-2 ring-orange-400"
            title={t('modeDescriptionManual')}
          >
            <PauseCircle className="w-4.5 h-4.5" />
            {t('interruptBtn')}
          </button>
        ) : (
          <button
            onClick={() => handleModeChange('manual')}
            className="flex items-center justify-center gap-2 py-3.5 px-3 bg-lime-500 hover:bg-lime-400 text-slate-950 font-black rounded-xl btn-hover shadow-lg shadow-lime-950/50 text-xs md:text-sm border border-lime-400/40"
            title={t('modeDescriptionManual')}
          >
            <Pause className="w-4 h-4 fill-current" />
            {t('manualModeBtn')}
          </button>
        )}

        {/* Botão Emergência Home */}
        <button
          onClick={onEmergencyStop}
          className="flex items-center justify-center gap-2 py-3.5 px-3 bg-amber-700 hover:bg-amber-600 text-white font-bold rounded-xl btn-hover shadow-lg shadow-amber-900/40 text-xs md:text-sm"
          title={t('btnEmergencyStop')}
        >
          <AlertOctagon className="w-4 h-4" />
          {t('emergencyHomeBtn')}
        </button>
      </div>

      {/* Painel do Modo Manual Passo-a-Passo */}
      {isManualActive && (
        <div className="p-4 bg-slate-900/80 border border-amber-500/30 rounded-xl space-y-4 shadow-inner">
          <div className="flex items-center justify-between border-b border-amber-500/20 pb-2">
            <span className="text-xs font-bold text-amber-400 flex items-center gap-2">
              <CheckCircle className="w-4 h-4 text-amber-400" />
              {t('manualControlsTitle')}
            </span>
            <span className="text-xs text-slate-400">
              STATUS: <strong className="text-white uppercase">{status}</strong>
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {/* Passo 1: Ir para SCAN */}
            <div className="p-3 bg-slate-800/80 border border-slate-700 rounded-lg space-y-2">
              <span className="text-xs font-bold text-slate-300 block">{t('step1Scan')}</span>
              <button
                onClick={onManualStartScan}
                disabled={status !== 'idle'}
                className={`w-full py-2.5 px-3 text-xs font-bold rounded-lg flex items-center justify-center gap-2 transition-all ${status === 'idle' ? 'bg-amber-500 hover:bg-amber-400 text-slate-950 btn-hover shadow-md' : 'bg-slate-700/50 text-slate-500 cursor-not-allowed'}`}
              >
                <RefreshCw className={`w-3.5 h-3.5 ${status === 'moving_scan' ? 'animate-spin' : ''}`} />
                {status === 'moving_scan' ? 'INDO PARA SCAN...' : t('step1Scan')}
              </button>
            </div>

            {/* Passo 2: Autorizar PICK */}
            <div className="p-3 bg-slate-800/80 border border-slate-700 rounded-lg space-y-2">
              <span className="text-xs font-bold text-slate-300 block">{t('step2Pick')}</span>
              {status === 'at_scan_inspecting' && detectedItem ? (
                <button
                  onClick={onManualAuthorizePick}
                  className="w-full py-2.5 px-3 text-xs font-bold rounded-lg flex items-center justify-center gap-2 bg-emerald-500 hover:bg-emerald-400 text-slate-950 btn-hover shadow-lg shadow-emerald-900/40 animate-pulse"
                >
                  <Check className="w-4 h-4" />
                  {t('step2Pick')}: {detectedItem.class} ({(detectedItem.confidence * 100).toFixed(0)}%)
                </button>
              ) : (
                <button
                  disabled
                  className="w-full py-2.5 px-3 text-xs font-bold rounded-lg flex items-center justify-center gap-2 bg-slate-800 text-slate-500 border border-slate-700 cursor-not-allowed"
                >
                  {status === 'at_scan_inspecting' ? <Loader2 className="w-3.5 h-3.5 animate-spin text-amber-400" /> : <X className="w-3.5 h-3.5" />}
                  {status === 'at_scan_inspecting' ? 'Aguardando detecção YOLO...' : t('step2Pick')}
                </button>
              )}
            </div>

            {/* Passo 3: Autorizar PLACE */}
            <div className="p-3 bg-slate-800/80 border border-slate-700 rounded-lg space-y-2">
              <span className="text-xs font-bold text-slate-300 block">{t('step3Place')}</span>
              {status === 'at_place_approach_waiting' ? (
                <button
                  onClick={onManualAuthorizePlace}
                  className="w-full py-2.5 px-3 text-xs font-bold rounded-lg flex items-center justify-center gap-2 bg-blue-500 hover:bg-blue-400 text-white btn-hover shadow-lg shadow-blue-900/40 animate-pulse"
                >
                  <Check className="w-4 h-4" />
                  {t('step3Place')}
                </button>
              ) : (
                <button
                  disabled
                  className="w-full py-2.5 px-3 text-xs font-bold rounded-lg flex items-center justify-center gap-2 bg-slate-800 text-slate-500 border border-slate-700 cursor-not-allowed"
                >
                  <X className="w-3.5 h-3.5" />
                  {t('step3Place')}
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 🧪 PAINEL DE TESTE DE HANDSHAKE COBOT ➔ TURTLEBOT 4 */}
      <div className="p-4 bg-gradient-to-r from-indigo-950/60 via-purple-950/30 to-indigo-950/60 border border-purple-500/40 rounded-xl space-y-3 shadow-lg">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-purple-500/30 pb-2">
          <div className="flex items-center gap-2">
            <Cpu className="w-5 h-5 text-purple-400" />
            <h3 className="text-sm font-bold text-slate-100">
              {t('testHandshakeTitle')}
            </h3>
          </div>
          <span className="text-xs text-slate-400 font-medium">
            {t('testHandshakeSubtitle')}
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <button
            onClick={() => onTestHandshake && onTestHandshake('tin_valid_blue_square')}
            disabled={isCycleRunning}
            className={`py-3 px-4 rounded-xl font-extrabold text-xs flex items-center justify-center gap-2 transition-all border ${
              !isCycleRunning
                ? 'bg-blue-600 hover:bg-blue-500 text-white border-blue-400 shadow-lg shadow-blue-900/40 btn-hover'
                : 'bg-slate-800 text-slate-500 border-slate-700 cursor-not-allowed'
            }`}
          >
            <span className="w-2.5 h-2.5 rounded-full bg-blue-400 animate-pulse"></span>
            <span>{t('testBlueTin')}</span>
          </button>

          <button
            onClick={() => onTestHandshake && onTestHandshake('tin_valid_red_square')}
            disabled={isCycleRunning}
            className={`py-3 px-4 rounded-xl font-extrabold text-xs flex items-center justify-center gap-2 transition-all border ${
              !isCycleRunning
                ? 'bg-red-600 hover:bg-red-500 text-white border-red-400 shadow-lg shadow-red-900/40 btn-hover'
                : 'bg-slate-800 text-slate-500 border-slate-700 cursor-not-allowed'
            }`}
          >
            <span className="w-2.5 h-2.5 rounded-full bg-red-400 animate-pulse"></span>
            <span>{t('testRedTin')}</span>
          </button>
        </div>
      </div>

      {/* Sliders Dinâmicos de Parâmetros (3 Sliders) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
        {/* Slider de Cooldown */}
        <div className="space-y-2 bg-slate-800/50 p-4 rounded-xl border border-slate-700/50">
          <div className="flex justify-between text-sm">
            <span className="text-slate-300 font-medium">{t('cooldownTitle')}</span>
            <span className="font-bold text-blue-400">{cooldown}s</span>
          </div>
          <input
            type="range"
            min="1.0"
            max="10.0"
            step="0.5"
            value={cooldown}
            onChange={(e) => handleSliderChange(parseFloat(e.target.value), conf, speedPct)}
            className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
          />
          <p className="text-xs text-slate-400">{t('cooldownSub')}</p>
        </div>

        {/* Slider de Confiança YOLO */}
        <div className="space-y-2 bg-slate-800/50 p-4 rounded-xl border border-slate-700/50">
          <div className="flex justify-between text-sm">
            <span className="text-slate-300 font-medium">{t('confTitle')}</span>
            <span className="font-bold text-emerald-400">{conf}%</span>
          </div>
          <input
            type="range"
            min="30"
            max="90"
            step="5"
            value={conf}
            onChange={(e) => handleSliderChange(cooldown, parseFloat(e.target.value), speedPct)}
            className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-emerald-500"
          />
          <p className="text-xs text-slate-400">{t('confSub')}</p>
        </div>

        {/* Slider de Velocidade do Braço (Nano) */}
        <div className="space-y-2 bg-slate-800/50 p-4 rounded-xl border border-slate-700/50">
          <div className="flex justify-between items-center text-sm">
            <div className="flex items-center gap-2">
              <span className="text-slate-300 font-medium">{t('armSpeedTitle')}</span>
              <span className="text-[10px] font-bold text-amber-400 bg-amber-950/80 px-1.5 py-0.5 rounded border border-amber-700/60 uppercase tracking-wider">
                {t('underConstBadge')}
              </span>
            </div>
            <span className="font-bold text-amber-400">{speedPct}%</span>
          </div>
          <input
            type="range"
            min="1"
            max="15"
            step="1"
            value={speedPct}
            onChange={(e) => handleSliderChange(cooldown, conf, parseInt(e.target.value, 10))}
            className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-amber-400"
          />
          <p className="text-xs text-amber-400/80 font-medium">{t('underConstNote')}</p>
        </div>
      </div>
    </div>
  );
}

import React, { useState } from 'react';
import { AlertOctagon, Flame, RefreshCw, Cpu, Camera, Power, Loader2 } from 'lucide-react';
import { useLanguage } from '../context/LanguageContext';

export default function PanicOverlayModal({ isLocked, onResetPanic }) {
  const { t } = useLanguage();
  const [resetting, setResetting] = useState(false);

  if (!isLocked) return null;

  const handleReset = async () => {
    setResetting(true);
    try {
      await onResetPanic();
    } finally {
      setTimeout(() => setResetting(false), 4000);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/90 backdrop-blur-xl flex items-center justify-center p-4 animate-in fade-in duration-300">
      <div className="max-w-2xl w-full bg-red-950/90 border-2 border-red-500 rounded-2xl p-6 md:p-8 space-y-6 shadow-2xl shadow-red-950/80 text-center relative overflow-hidden">
        {/* Animação sutil de luz vermelha de pânico */}
        <div className="absolute -top-24 -left-24 w-48 h-48 bg-red-600/30 rounded-full blur-3xl animate-pulse" />
        <div className="absolute -bottom-24 -right-24 w-48 h-48 bg-red-600/30 rounded-full blur-3xl animate-pulse" />

        {/* Ícone de Pânico Absoluto */}
        <div className="flex justify-center">
          <div className="w-20 h-20 bg-red-600/20 border border-red-500/50 rounded-full flex items-center justify-center text-red-500 animate-bounce">
            <Flame className="w-12 h-12" />
          </div>
        </div>

        {/* Mensagem e Título */}
        <div className="space-y-3">
          <h2 className="text-2xl md:text-3xl font-black text-red-100 tracking-wider flex items-center justify-center gap-2">
            <AlertOctagon className="w-8 h-8 text-red-500" />
            {t('panicOverlayTitle')}
          </h2>
          <p className="text-sm md:text-base text-red-200/90 leading-relaxed max-w-xl mx-auto font-medium">
            {t('panicOverlaySubtitle')}
          </p>
        </div>

        {/* Lista de Componentes Desligados */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs font-bold text-red-200">
          <div className="p-3 bg-red-900/40 border border-red-500/30 rounded-xl flex flex-col items-center gap-1.5">
            <Power className="w-5 h-5 text-red-400" />
            <span>{t('panicPumpLabel')}</span>
          </div>
          <div className="p-3 bg-red-900/40 border border-red-500/30 rounded-xl flex flex-col items-center gap-1.5">
            <Camera className="w-5 h-5 text-red-400" />
            <span>{t('panicCameraLabel')}</span>
          </div>
          <div className="p-3 bg-red-900/40 border border-red-500/30 rounded-xl flex flex-col items-center gap-1.5">
            <Cpu className="w-5 h-5 text-red-400" />
            <span>{t('panicMotorsLabel')}</span>
          </div>
          <div className="p-3 bg-red-900/40 border border-red-500/30 rounded-xl flex flex-col items-center gap-1.5">
            <AlertOctagon className="w-5 h-5 text-red-400" />
            <span>{t('panicYoloLabel')}</span>
          </div>
        </div>

        {/* Aviso Explícito de Necessidade de Reinicialização */}
        <div className="p-4 bg-red-900/60 border border-red-400/40 rounded-xl text-xs text-red-100 space-y-1">
          <p className="font-bold text-amber-300 flex items-center justify-center gap-1.5 text-sm">
            {t('panicAlertTitle')}
          </p>
          <p className="text-slate-200">
            {t('panicAlertDesc')}
          </p>
        </div>

        {/* Botão de Desbloqueio e Reinicialização */}
        <div className="pt-2">
          <button
            onClick={handleReset}
            disabled={resetting}
            className="w-full py-4 px-6 bg-gradient-to-r from-red-600 to-amber-600 hover:from-red-500 hover:to-amber-500 text-white font-black text-sm md:text-base rounded-xl shadow-xl shadow-red-950/60 flex items-center justify-center gap-2 btn-hover tracking-wide"
          >
            {resetting ? <Loader2 className="w-5 h-5 animate-spin" /> : <RefreshCw className="w-5 h-5" />}
            {resetting ? t('resettingPanicLoading') : t('btnRestartPanic')}
          </button>
        </div>
      </div>
    </div>
  );
}

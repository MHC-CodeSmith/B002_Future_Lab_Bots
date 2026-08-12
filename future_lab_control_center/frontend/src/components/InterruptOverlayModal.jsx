import React from 'react';
import { ShieldAlert, AlertTriangle, CheckCircle, XCircle } from 'lucide-react';
import { useLanguage } from '../context/LanguageContext';

export default function InterruptOverlayModal({ isInterrupted, onConfirmInterrupt }) {
  const { t } = useLanguage();
  if (!isInterrupted) return null;

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/85 backdrop-blur-md flex items-center justify-center p-4 overflow-y-auto animate-in fade-in duration-200">
      <div className="glass-card max-w-lg w-full p-6 md:p-8 rounded-2xl border-2 border-amber-500/60 shadow-2xl shadow-amber-950/80 space-y-6 text-center relative max-h-[90vh] overflow-y-auto">
        
        {/* Ícone Alerta de Interrupção */}
        <div className="flex justify-center">
          <div className="w-16 h-16 bg-amber-500/20 text-amber-400 border border-amber-500/50 rounded-full flex items-center justify-center shadow-inner animate-pulse">
            <ShieldAlert className="w-10 h-10" />
          </div>
        </div>

        {/* Mensagem e Título */}
        <div className="space-y-2">
          <h3 className="text-xl md:text-2xl font-black text-white tracking-wide flex items-center justify-center gap-2">
            <AlertTriangle className="w-6 h-6 text-amber-400" />
            {t('interruptOverlayTitle')}
          </h3>
          <p className="text-xs md:text-sm text-slate-300 leading-relaxed font-medium">
            {t('interruptOverlayMsg')}
          </p>
        </div>

        {/* Explicação Clara dos Dois Modos */}
        <div className="p-4 bg-slate-900/90 border border-slate-700/80 rounded-xl text-left space-y-3 text-xs md:text-sm">
          <div className="space-y-1 border-b border-slate-800 pb-2">
            <p className="text-red-400 font-bold flex items-center gap-1.5">
              <XCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
              {t('interruptOverlayAbortLabel')}
            </p>
            <p className="text-slate-300 pl-5 text-xs leading-normal">
              {t('interruptOverlayAbortDesc')}
            </p>
          </div>

          <div className="space-y-1">
            <p className="text-emerald-400 font-bold flex items-center gap-1.5">
              <CheckCircle className="w-4 h-4 text-emerald-400 flex-shrink-0" />
              {t('interruptOverlayResumeLabel')}
            </p>
            <p className="text-slate-300 pl-5 text-xs leading-normal">
              {t('interruptOverlayResumeDesc')}
            </p>
          </div>
        </div>

        {/* Botões Grandes e Destacados */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
          <button
            onClick={() => onConfirmInterrupt(true)}
            className="w-full py-3.5 px-4 bg-red-600 hover:bg-red-500 text-white font-black rounded-xl btn-hover text-xs md:text-sm shadow-lg shadow-red-950/60 flex items-center justify-center gap-2"
          >
            <XCircle className="w-4 h-4" />
            {t('btnAbortOperation')}
          </button>

          <button
            onClick={() => onConfirmInterrupt(false)}
            className="w-full py-3.5 px-4 bg-emerald-600 hover:bg-emerald-500 text-white font-black rounded-xl btn-hover text-xs md:text-sm shadow-lg shadow-emerald-950/60 flex items-center justify-center gap-2"
          >
            <CheckCircle className="w-4 h-4" />
            {t('btnResumeOperation')}
          </button>
        </div>
      </div>
    </div>
  );
}

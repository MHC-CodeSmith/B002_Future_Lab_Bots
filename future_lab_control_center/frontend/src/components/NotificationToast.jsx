import React, { useEffect } from 'react';
import { AlertTriangle, CheckCircle, Info, X, AlertOctagon, RefreshCw } from 'lucide-react';

export default function NotificationToast({ notification, onClose }) {
  useEffect(() => {
    if (notification && notification.type !== 'panic') {
      const timer = setTimeout(() => {
        onClose();
      }, 7000); // Autoclose após 7s se não for pânico
      return () => clearTimeout(timer);
    }
  }, [notification, onClose]);

  if (!notification) return null;

  const isPanic = notification.type === 'panic';
  const isError = notification.type === 'error';
  const isWarning = notification.type === 'warning';
  const isSuccess = notification.type === 'success';

  let bgColor = 'bg-slate-800 border-slate-700 text-slate-200';
  let Icon = Info;

  if (isPanic) {
    bgColor = 'bg-red-950/95 border-red-500 text-red-100 shadow-2xl shadow-red-950 animate-pulse';
    Icon = AlertOctagon;
  } else if (isError) {
    bgColor = 'bg-red-900/90 border-red-500 text-red-100 shadow-lg';
    Icon = AlertTriangle;
  } else if (isWarning) {
    bgColor = 'bg-amber-950/95 border-amber-500/80 text-amber-200 shadow-lg';
    Icon = AlertTriangle;
  } else if (isSuccess) {
    bgColor = 'bg-emerald-950/95 border-emerald-500/80 text-emerald-200 shadow-lg';
    Icon = CheckCircle;
  }

  return (
    <div className={`fixed top-4 right-4 left-4 md:left-auto md:max-w-xl z-50 p-4 rounded-xl border backdrop-blur-md flex items-start gap-3 transition-all duration-300 ${bgColor}`}>
      <Icon className={`w-6 h-6 flex-shrink-0 mt-0.5 ${isPanic || isError ? 'text-red-400' : isWarning ? 'text-amber-400' : 'text-emerald-400'}`} />
      
      <div className="flex-1 text-sm space-y-1">
        <h4 className="font-bold text-sm tracking-wide">
          {notification.title || (isPanic ? '🚨 PÂNICO ATIVADO' : isError ? '❌ ERRO DE OPERAÇÃO' : isWarning ? '⚠️ ATENÇÃO / POSES PENDENTES' : '✅ OPERAÇÃO CONCLUÍDA')}
        </h4>
        <p className="text-xs leading-relaxed opacity-95">
          {notification.message}
        </p>
      </div>

      <button
        onClick={onClose}
        className="p-1 hover:bg-white/10 rounded-lg text-slate-300 transition-colors"
        title="Fechar Notificação"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}

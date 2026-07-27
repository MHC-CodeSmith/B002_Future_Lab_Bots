import React from 'react';
import { Bot, Battery, Navigation, Anchor } from 'lucide-react';

export default function TurtleBotPanel({ tbStatus }) {
  const isOnline = tbStatus?.status === 'ready';

  return (
    <div className="glass-card p-5 rounded-xl space-y-4">
      <div className="flex items-center justify-between border-b border-slate-700 pb-3">
        <h2 className="text-lg font-bold flex items-center gap-2">
          <Bot className="w-5 h-5 text-blue-400" />
          Status do TurtleBot 4 (AMR)
        </h2>
        <span className={`text-xs px-2.5 py-1 rounded-full font-bold ${isOnline ? 'bg-emerald-500/20 text-emerald-300' : 'bg-slate-700 text-slate-400'}`}>
          {isOnline ? 'CONECTADO' : 'AGUARDANDO CONEXÃO'}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Bateria */}
        <div className="p-3 bg-slate-800/60 rounded-xl border border-slate-700/50 flex items-center gap-3">
          <div className="p-2 bg-emerald-500/20 text-emerald-400 rounded-lg">
            <Battery className="w-5 h-5" />
          </div>
          <div>
            <p className="text-xs text-slate-400">Bateria</p>
            <p className="text-sm font-bold text-slate-200">{tbStatus?.battery_percentage || 100}%</p>
          </div>
        </div>

        {/* Docking */}
        <div className="p-3 bg-slate-800/60 rounded-xl border border-slate-700/50 flex items-center gap-3">
          <div className="p-2 bg-blue-500/20 text-blue-400 rounded-lg">
            <Anchor className="w-5 h-5" />
          </div>
          <div>
            <p className="text-xs text-slate-400">Estação de Carga</p>
            <p className="text-sm font-bold text-slate-200">{tbStatus?.is_docked ? 'No Dock' : 'Em Campo'}</p>
          </div>
        </div>

        {/* Navegação */}
        <div className="p-3 bg-slate-800/60 rounded-xl border border-slate-700/50 flex items-center gap-3">
          <div className="p-2 bg-purple-500/20 text-purple-400 rounded-lg">
            <Navigation className="w-5 h-5" />
          </div>
          <div>
            <p className="text-xs text-slate-400">Status Nav2</p>
            <p className="text-sm font-bold text-slate-200">Pronto para Waypoints</p>
          </div>
        </div>
      </div>
    </div>
  );
}

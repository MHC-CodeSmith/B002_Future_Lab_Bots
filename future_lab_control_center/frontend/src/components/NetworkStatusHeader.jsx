import React from 'react';
import { Activity, Wifi, Camera, Bot, Globe } from 'lucide-react';
import { useLanguage } from '../context/LanguageContext';

export default function NetworkStatusHeader({ healthData }) {
  const devices = healthData?.devices || {};
  const { lang, toggleLanguage, t } = useLanguage();

  return (
    <header className="glass-card p-4 rounded-xl mb-6 flex flex-wrap items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        <div className="p-2 bg-blue-600/20 rounded-lg text-blue-400">
          <Activity className="w-6 h-6 animate-pulse" />
        </div>
        <div>
          <h1 className="text-xl font-bold tracking-wide">{t('systemTitle')}</h1>
          <p className="text-xs text-slate-400">{t('systemSubtitle')}</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 text-sm">
        {/* Seletor de Idioma */}
        <button
          onClick={() => toggleLanguage()}
          title="Alternar Idioma / Switch Language"
          className="flex items-center gap-2 px-3 py-1.5 bg-blue-950/60 hover:bg-blue-900/80 transition-colors rounded-lg border border-blue-600/50 text-blue-300 font-bold cursor-pointer"
        >
          <Globe className="w-4 h-4 text-blue-400" />
          <span>{lang === 'pt' ? '🇧🇷 PT' : '🇺🇸 EN'}</span>
        </button>

        {/* PC Host */}
        <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-800/80 rounded-lg border border-slate-700">
          <Wifi className={`w-4 h-4 ${devices.host_pc?.online ? 'text-emerald-400' : 'text-red-400'}`} />
          <span className="text-slate-300 font-medium">PC Host:</span>
          <span className={`text-xs px-2 py-0.5 rounded-full font-bold ${devices.host_pc?.online ? 'bg-emerald-500/20 text-emerald-300' : 'bg-red-500/20 text-red-300'}`}>
            {devices.host_pc?.online ? 'ONLINE' : 'OFFLINE'}
          </span>
        </div>

        {/* Jetson Nano */}
        <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-800/80 rounded-lg border border-slate-700">
          <Bot className={`w-4 h-4 ${devices.jetson_nano?.online ? 'text-emerald-400' : 'text-red-400'}`} />
          <span className="text-slate-300 font-medium">Nano (Cobot):</span>
          <span className={`text-xs px-2 py-0.5 rounded-full font-bold ${devices.jetson_nano?.online ? 'bg-emerald-500/20 text-emerald-300' : 'bg-red-500/20 text-red-300'}`}>
            {devices.jetson_nano?.online ? 'ONLINE' : 'OFFLINE'}
          </span>
        </div>

        {/* Stream Câmera */}
        <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-800/80 rounded-lg border border-slate-700">
          <Camera className={`w-4 h-4 ${devices.jetson_nano?.camera_stream_online ? 'text-emerald-400' : 'text-amber-400'}`} />
          <span className="text-slate-300 font-medium">Câmera MJPEG:</span>
          <span className={`text-xs px-2 py-0.5 rounded-full font-bold ${devices.jetson_nano?.camera_stream_online ? 'bg-emerald-500/20 text-emerald-300' : 'bg-amber-500/20 text-amber-300'}`}>
            {devices.jetson_nano?.camera_stream_online ? 'STREAM' : 'OFFLINE'}
          </span>
        </div>

        {/* TurtleBot 4 */}
        <div className="flex items-center gap-2 px-3 py-1.5 bg-slate-800/80 rounded-lg border border-slate-700">
          <Bot className={`w-4 h-4 ${devices.turtlebot4?.online ? 'text-emerald-400' : 'text-slate-500'}`} />
          <span className="text-slate-300 font-medium">TurtleBot 4:</span>
          <span className={`text-xs px-2 py-0.5 rounded-full font-bold ${devices.turtlebot4?.online ? 'bg-emerald-500/20 text-emerald-300' : 'bg-slate-700 text-slate-400'}`}>
            {devices.turtlebot4?.online ? 'ONLINE' : 'DESCONECTADO'}
          </span>
        </div>
      </div>
    </header>
  );
}

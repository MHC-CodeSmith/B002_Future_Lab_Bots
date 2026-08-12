import React, { useState } from 'react';
import { BookOpen, Unlock, Lock, Save, Play, Pause, Trash2, CheckCircle2, XCircle, Clock, RotateCcw } from 'lucide-react';
import { useLanguage } from '../context/LanguageContext';

export default function TeachModePanel({ cellState, posesData, onRelease, onLock, onRecord, onSave, onPlayback, onClear, onRestore, onMovePose, onMovePoseFail, onLaunchRviz }) {
  const { t } = useLanguage();
  const [selectedPose, setSelectedPose] = useState('home');
  const [loading, setLoading] = useState(false);

  const isAutoRunning = Boolean(cellState?.auto_running);

  const posesList = posesData?.poses || [
    { name: 'home', recorded: false },
    { name: 'scan', recorded: false },
    { name: 'pick_approach', recorded: false },
    { name: 'pick', recorded: false },
    { name: 'place_approach', recorded: false },
    { name: 'place', recorded: false }
  ];

  const hasBackup = Boolean(posesData?.has_backup);
  const playbackStatus = posesData?.playback_status || 'idle';

  const handleAction = async (actionFn, ...args) => {
    if (isAutoRunning) return;
    setLoading(true);
    try {
      await actionFn(...args);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={`glass-card p-5 rounded-xl space-y-5 relative ${isAutoRunning ? 'opacity-70 pointer-events-none select-none' : ''}`}>
      {isAutoRunning && (
        <div className="bg-amber-500/20 border border-amber-500/40 text-amber-300 p-3 rounded-lg flex items-center justify-between text-xs font-bold shadow-lg">
          <span className="flex items-center gap-2">
            <Lock className="w-4 h-4 text-amber-400" />
            🔒 AUTOMATIC MODE RUNNING — Teach & Pose Calibration Panel Locked.
          </span>
          <span className="text-[10px] bg-amber-900/60 px-2 py-0.5 rounded text-amber-200 uppercase font-mono">
            Turn off auto mode to unlock
          </span>
        </div>
      )}

      <div className="flex items-center justify-between border-b border-slate-700 pb-3">
        <div>
          <h2 className="text-lg font-bold flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-blue-400" />
            {t('teachPanelTitle')}
          </h2>
          <p className="text-xs text-slate-400 flex items-center gap-1 mt-1">
            <Clock className="w-3.5 h-3.5" />
            {t('lastRecordSaved')} <span className="font-semibold text-slate-200">{posesData?.last_saved || '—'}</span>
          </p>
        </div>
        
        {/* Controles de Torque dos Motores e Launcher RViz 2 */}
        <div className="flex flex-wrap items-center gap-2">
          {onLaunchRviz && (
            <button
              onClick={() => handleAction(onLaunchRviz)}
              disabled={loading || isAutoRunning}
              className="px-3 py-1.5 bg-indigo-600/30 hover:bg-indigo-600 text-indigo-200 border border-indigo-500/40 text-xs font-bold rounded-lg flex items-center gap-1.5 btn-hover disabled:opacity-50"
            >
              🖥️ {t('openRviz')}
            </button>
          )}

          <button
            onClick={() => handleAction(onRelease)}
            disabled={loading || isAutoRunning}
            className="px-3 py-1.5 bg-amber-600/30 hover:bg-amber-600 text-amber-300 border border-amber-500/40 text-xs font-bold rounded-lg flex items-center gap-1.5 btn-hover disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Unlock className="w-4 h-4" />
            {t('releaseMotors')}
          </button>
          <button
            onClick={() => handleAction(onLock)}
            disabled={loading || isAutoRunning}
            className="px-3 py-1.5 bg-blue-600/30 hover:bg-blue-600 text-blue-300 border border-blue-500/40 text-xs font-bold rounded-lg flex items-center gap-1.5 btn-hover disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Lock className="w-4 h-4" />
            {t('lockMotors')}
          </button>
        </div>
      </div>

      {/* Tabela de Poses */}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-800/80 text-xs uppercase text-slate-400">
            <tr>
              <th className="p-3">{t('thPose')}</th>
              <th className="p-3">{t('thStatus')}</th>
              <th className="p-3">{t('thJoints')}</th>
              <th className="p-3 text-right">{t('thActions')}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800">
            {posesList.map((p) => (
              <tr key={p.name} className={selectedPose === p.name ? 'bg-blue-900/20' : 'hover:bg-slate-800/40'}>
                <td className="p-3 font-mono font-bold text-blue-300">{p.name}</td>
                <td className="p-3">
                  {p.recorded ? (
                    <span className="text-xs px-2.5 py-1 rounded-full bg-emerald-500/20 text-emerald-300 font-bold flex items-center gap-1 w-max">
                      <CheckCircle2 className="w-3.5 h-3.5" /> {t('recordedBadge')}
                    </span>
                  ) : (
                    <span className="text-xs px-2.5 py-1 rounded-full bg-red-500/20 text-red-300 font-bold flex items-center gap-1 w-max">
                      <XCircle className="w-3.5 h-3.5" /> PENDING
                    </span>
                  )}
                </td>
                <td className="p-3 font-mono text-xs text-slate-400">
                  {p.joints ? `[${p.joints.map(v => v.toFixed(2)).join(', ')}]` : '—'}
                </td>
                <td className="p-3 text-right flex items-center justify-end gap-2">
                  <button
                    onClick={() => {
                      if (!p.recorded) {
                        if (onMovePoseFail) onMovePoseFail(p.name);
                      } else {
                        handleAction(onMovePose, p.name);
                      }
                    }}
                    disabled={loading}
                    className={`px-2.5 py-1 text-xs font-bold rounded-md flex items-center gap-1 transition-colors ${
                      p.recorded
                        ? 'bg-blue-600 hover:bg-blue-500 text-white btn-hover'
                        : 'bg-slate-800 text-slate-500 border border-slate-700 cursor-not-allowed'
                    }`}
                  >
                    <Play className="w-3 h-3 fill-current" />
                    {t('goBtn')}
                  </button>

                  <button
                    onClick={() => {
                      setSelectedPose(p.name);
                      handleAction(onRecord, p.name);
                    }}
                    disabled={loading}
                    className="px-3 py-1 bg-emerald-600 hover:bg-emerald-500 text-xs font-bold rounded-md btn-hover"
                  >
                    {t('recordBtn')}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Botões do Menu Principal de Calibragem */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 pt-2">
        <button
          onClick={() => handleAction(onPlayback)}
          disabled={loading}
          className={`py-2.5 px-3 text-xs font-bold rounded-xl flex items-center justify-center gap-1.5 transition-all btn-hover ${
            playbackStatus === 'running'
              ? 'bg-amber-600 hover:bg-amber-500 text-white shadow-lg shadow-amber-900/30'
              : playbackStatus === 'paused'
              ? 'bg-emerald-600 hover:bg-emerald-500 text-white animate-pulse shadow-lg shadow-emerald-900/40'
              : 'bg-emerald-600 hover:bg-emerald-500 text-white'
          }`}
        >
          <Play className="w-4 h-4 fill-current" />
          PLAYBACK TEST (4)
        </button>

        <button
          onClick={() => handleAction(onSave)}
          disabled={loading}
          className="py-2.5 px-3 bg-blue-600 hover:bg-blue-500 text-xs font-bold rounded-xl flex items-center justify-center gap-1.5 btn-hover"
        >
          <Save className="w-4 h-4" />
          SAVE TO DISK (5)
        </button>

        <button
          onClick={() => handleAction(onClear)}
          disabled={loading}
          className="py-2.5 px-3 bg-red-600/30 hover:bg-red-600 text-red-300 border border-red-500/40 text-xs font-bold rounded-xl flex items-center justify-center gap-1.5 btn-hover"
        >
          <Trash2 className="w-4 h-4" />
          CLEAR POSES (6)
        </button>

        <button
          onClick={() => handleAction(onRestore)}
          disabled={loading || !hasBackup}
          className={`py-2.5 px-3 text-xs font-bold rounded-xl flex items-center justify-center gap-1.5 ${
            hasBackup && !loading
              ? 'bg-purple-600 hover:bg-purple-500 text-white shadow-lg shadow-purple-900/30 btn-hover'
              : 'bg-slate-800/50 text-slate-600 border border-slate-700/50 cursor-not-allowed'
          }`}
        >
          <RotateCcw className="w-4 h-4" />
          RESTORE LAST
        </button>
      </div>
    </div>
  );
}

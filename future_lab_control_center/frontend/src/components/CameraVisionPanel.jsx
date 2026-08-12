import React, { useState, useEffect, useRef } from 'react';
import { Camera, Power, PowerOff, CheckCircle, AlertTriangle, RefreshCw, FlaskConical, Search, XCircle, Loader2 } from 'lucide-react';
import { useLanguage } from '../context/LanguageContext';

export default function CameraVisionPanel({
  streamUrl,
  cameraOnline,
  lastYolo,
  yoloConfThreshold = 0.60,
  pumpActive,
  yoloTestActive,
  onTogglePump,
  onToggleYoloTest,
  onRestartCamera,
  onStopCamera,
  onLaunchYoloWindow
}) {
  const { t } = useLanguage();
  const [streamError, setStreamError] = useState(false);
  const [streamKey, setStreamKey] = useState(Date.now());
  const [restarting, setRestarting] = useState(false);
  const [stopping, setStopping] = useState(false);
  const retryTimers = useRef([]);

  const defaultHost = typeof window !== 'undefined' ? window.location.hostname : 'localhost';
  const rawUrl = streamUrl || `http://${defaultHost}:8080/stream.mjpg`;
  const liveUrl = `${rawUrl}${rawUrl.includes('?') ? '&' : '?'}t=${streamKey}`;

  const isFresh = Boolean(lastYolo && lastYolo.class && lastYolo.class !== 'none');

  useEffect(() => {
    if (streamError && !restarting && !stopping && cameraOnline) {
      const interval = setInterval(() => {
        setStreamKey(Date.now());
      }, 3000);
      return () => clearInterval(interval);
    }
  }, [streamError, restarting, stopping, cameraOnline]);

  useEffect(() => {
    return () => {
      retryTimers.current.forEach(clearTimeout);
    };
  }, []);

  const handleStartOrRestart = async () => {
    setRestarting(true);
    setStopping(false);
    setStreamError(false);
    
    if (onRestartCamera) {
      try {
        await onRestartCamera();
      } catch (e) {
        console.warn("Error restarting camera:", e);
      }
    }
    
    const retryDelays = [7000, 10000, 13000, 16000];
    retryDelays.forEach((delay, i) => {
      const timer = setTimeout(() => {
        setStreamError(false);
        setStreamKey(Date.now());
        if (i === retryDelays.length - 1) {
          setRestarting(false);
        }
      }, delay);
      retryTimers.current.push(timer);
    });
  };

  const handleStop = async () => {
    retryTimers.current.forEach(t => clearTimeout(t));
    retryTimers.current = [];

    setStopping(true);
    setRestarting(false);
    
    if (onStopCamera) {
      try {
        await onStopCamera();
      } catch (e) {
        console.warn("Error stopping camera:", e);
      }
    }

    setTimeout(() => {
      setStreamError(true);
      setStopping(false);
    }, 2000);
  };

  const getDetectionBadge = () => {
    if (!isFresh || !lastYolo || !lastYolo.class) return null;
    const cls = (lastYolo.class || '').toLowerCase();
    const confVal = lastYolo.confidence ?? 0;
    const confPct = (confVal * 100).toFixed(0);

    if (cls.includes('red') || cls.includes('vermelha') || cls.includes('triangle')) {
      return {
        bg: 'bg-red-950/90 border-red-500/70 text-red-200 shadow-red-900/50',
        dot: 'bg-red-500',
        label: `${t('redTin')} — ${confPct}%`
      };
    }
    if (cls.includes('blue') || cls.includes('azul') || cls.includes('square')) {
      return {
        bg: 'bg-blue-950/90 border-blue-500/70 text-blue-200 shadow-blue-900/50',
        dot: 'bg-blue-500',
        label: `${t('blueTin')} — ${confPct}%`
      };
    }
    return {
      bg: 'bg-emerald-950/90 border-emerald-500/70 text-emerald-200 shadow-emerald-900/50',
      dot: 'bg-emerald-500',
      label: `${t('objectDetected')} (${lastYolo.class}) — ${confPct}%`
    };
  };

  const badge = getDetectionBadge();
  const isBusy = restarting || stopping;

  return (
    <div className="glass-card p-5 rounded-xl space-y-4">
      <div className="flex flex-wrap items-center justify-between border-b border-slate-700 pb-3 gap-2">
        <h2 className="text-lg font-bold flex items-center gap-2">
          <Camera className="w-5 h-5 text-emerald-400" />
          {t('visionTitle')}
        </h2>
        
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={handleStartOrRestart}
            disabled={isBusy}
            className={`px-3 py-1.5 text-xs font-bold rounded-lg flex items-center gap-1.5 btn-hover transition-all duration-150 ${
              isBusy
                ? 'bg-slate-700 text-slate-400 cursor-not-allowed border border-slate-600'
                : cameraOnline
                  ? 'bg-blue-600/30 hover:bg-blue-600 text-blue-300 border border-blue-500/40'
                  : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-900/30'
            }`}
          >
            {restarting ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                {t('loading')}
              </>
            ) : cameraOnline ? (
              <>
                <RefreshCw className="w-3.5 h-3.5" />
                {t('restartCamera')}
              </>
            ) : (
              <>
                <Power className="w-3.5 h-3.5" />
                {t('startCamera')}
              </>
            )}
          </button>

          <button
            onClick={handleStop}
            disabled={!cameraOnline || isBusy}
            className={`px-3 py-1.5 text-xs font-bold rounded-lg flex items-center gap-1.5 transition-all duration-150 ${
              !cameraOnline || isBusy
                ? 'bg-slate-800/50 text-slate-600 cursor-not-allowed border border-slate-700/50'
                : 'bg-red-600/30 hover:bg-red-600 text-red-300 border border-red-500/40 btn-hover'
            }`}
          >
            {stopping ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                {t('loading')}
              </>
            ) : (
              <>
                <PowerOff className="w-3.5 h-3.5" />
                {t('turnOffCamera')}
              </>
            )}
          </button>

          <button
            onClick={() => onToggleYoloTest(!yoloTestActive)}
            disabled={!cameraOnline || isBusy}
            className={`px-3 py-1.5 text-xs font-bold rounded-lg flex items-center gap-1.5 transition-all duration-150 ${
              !cameraOnline || isBusy
                ? 'bg-slate-800/50 text-slate-600 cursor-not-allowed border border-slate-700/50'
                : yoloTestActive
                  ? 'bg-red-600 hover:bg-red-500 text-white shadow-lg shadow-red-900/40 btn-hover'
                  : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-900/30 btn-hover'
            }`}
          >
            <FlaskConical className={`w-3.5 h-3.5 ${yoloTestActive ? 'animate-pulse' : ''}`} />
            {yoloTestActive ? t('stopTestYolo') : t('testYolo')}
          </button>

          <button
            onClick={() => onTogglePump(!pumpActive)}
            className={`px-3 py-1.5 text-xs font-bold rounded-lg flex items-center gap-1.5 transition-all duration-150 ${
              pumpActive
                ? 'bg-red-600 hover:bg-red-500 text-white shadow-lg shadow-red-900/40'
                : 'bg-emerald-600 hover:bg-emerald-500 text-white'
            }`}
          >
            <Power className="w-3.5 h-3.5" />
            {pumpActive ? t('turnOffPump') : t('turnOnPump')}
          </button>

          {onLaunchYoloWindow && (
            <button
              onClick={onLaunchYoloWindow}
              className="px-3 py-1.5 bg-purple-600/30 hover:bg-purple-600 text-purple-200 border border-purple-500/40 text-xs font-bold rounded-lg flex items-center gap-1.5 btn-hover"
            >
              👁️ {t('opencvWindow')}
            </button>
          )}

          <a
            href={rawUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-600 text-xs font-bold rounded-lg flex items-center gap-1.5 btn-hover"
          >
            🔗 {t('rawStream')}
          </a>
        </div>
      </div>

      <div className="relative aspect-video bg-slate-900 rounded-xl overflow-hidden border border-slate-800 flex items-center justify-center">
        {restarting ? (
          <div className="text-center p-6 space-y-3">
            <Loader2 className="w-10 h-10 text-blue-400 mx-auto animate-spin" />
            <p className="text-sm font-semibold text-slate-200">{t('loading')}</p>
          </div>
        ) : stopping ? (
          <div className="text-center p-6 space-y-3">
            <Loader2 className="w-10 h-10 text-red-400 mx-auto animate-spin" />
            <p className="text-sm font-semibold text-slate-200">{t('loading')}</p>
          </div>
        ) : !streamError ? (
          <img
            key={streamKey}
            src={liveUrl}
            onError={() => {
              if (!restarting && !stopping) setStreamError(true);
            }}
            className="w-full h-full object-contain"
          />
        ) : (
          <div className="text-center p-6 space-y-2">
            <AlertTriangle className="w-10 h-10 text-amber-400 mx-auto animate-bounce" />
            <p className="text-sm font-semibold text-slate-300">
              {cameraOnline ? t('reconnecting') : t('cameraOffline')}
            </p>
          </div>
        )}

        {isFresh && badge && !isBusy && (
          <div className={`absolute top-3 left-3 backdrop-blur border px-3 py-2 rounded-lg flex items-center gap-2 shadow-lg ${badge.bg}`}>
            <span className={`w-2.5 h-2.5 rounded-full ${badge.dot} animate-ping`} />
            <div>
              <p className="text-[10px] text-slate-300 uppercase tracking-wider font-semibold">{t('liveDetection')}:</p>
              <p className="text-xs font-bold">{badge.label}</p>
            </div>
          </div>
        )}
      </div>

      <div className="p-3.5 bg-slate-800/60 rounded-xl border border-slate-700/50 flex flex-wrap items-center justify-between text-sm gap-2">
        <span className="text-slate-400 font-medium">{t('currentClass')}:</span>
        
        {restarting ? (
          <span className="font-bold text-blue-400 flex items-center gap-1.5 bg-blue-950/40 px-3 py-1 rounded-lg border border-blue-500/30">
            <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />
            {t('loading')}...
          </span>
        ) : stopping ? (
          <span className="font-bold text-red-400 flex items-center gap-1.5 bg-red-950/40 px-3 py-1 rounded-lg border border-red-500/30">
            <Loader2 className="w-4 h-4 text-red-400 animate-spin" />
            {t('loading')}...
          </span>
        ) : isFresh && badge ? (
          <span className="font-bold text-emerald-400 flex items-center gap-1.5 bg-emerald-950/40 px-3 py-1 rounded-lg border border-emerald-500/30">
            <CheckCircle className="w-4 h-4 text-emerald-400" />
            {badge.label}
          </span>
        ) : yoloTestActive ? (
          <span className="font-bold text-amber-400 flex items-center gap-1.5 bg-amber-950/40 px-3 py-1 rounded-lg border border-amber-500/30 animate-pulse">
            <Search className="w-4 h-4 text-amber-400 animate-spin" />
            {t('noTinDetected')}
          </span>
        ) : (
          <span className="text-slate-500 italic flex items-center gap-1">
            <XCircle className="w-4 h-4 text-slate-600" />
            {t('awaitingScan')}
          </span>
        )}
      </div>
    </div>
  );
}

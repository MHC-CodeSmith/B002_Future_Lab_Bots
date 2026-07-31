import React, { useState, useEffect } from 'react';
import { RefreshCw, Cpu, Camera, Bot, CheckCircle2, Loader2, AlertCircle } from 'lucide-react';

export default function RebootOverlayModal({ isRebooting, onRebootComplete }) {
  const [currentStep, setCurrentStep] = useState(0);
  const [progress, setProgress] = useState(0);

  const steps = [
    { id: 1, title: 'Parando processos antigos da Jetson Nano e MoveIt...', duration: 2000 },
    { id: 2, title: 'Iniciando ponte de comunicação de hardware (mycobot_hw) na Nano...', duration: 3500 },
    { id: 3, title: 'Subindo servidor de transmissão de vídeo da Câmera MJPEG...', duration: 2500 },
    { id: 4, title: 'Inicializando planejador MoveIt (galactic_demo) e RViz no PC...', duration: 3500 },
    { id: 5, title: 'Validando conexão da rede e telemetria das juntas...', duration: 2500 },
  ];

  useEffect(() => {
    if (!isRebooting) {
      setCurrentStep(0);
      setProgress(0);
      return;
    }

    const totalDuration = steps.reduce((acc, s) => acc + s.duration, 0);
    const startTime = Date.now();

    const interval = setInterval(() => {
      const elapsed = Date.now() - startTime;
      const pct = Math.min(Math.floor((elapsed / totalDuration) * 100), 100);
      setProgress(pct);

      let accumulated = 0;
      let activeStepIdx = 0;
      for (let i = 0; i < steps.length; i++) {
        accumulated += steps[i].duration;
        if (elapsed < accumulated) {
          activeStepIdx = i;
          break;
        }
        if (i === steps.length - 1) {
          activeStepIdx = steps.length - 1;
        }
      }
      setCurrentStep(activeStepIdx);

      if (elapsed >= totalDuration) {
        clearInterval(interval);
        setTimeout(() => {
          if (onRebootComplete) onRebootComplete();
        }, 500);
      }
    }, 100);

    return () => clearInterval(interval);
  }, [isRebooting]);

  if (!isRebooting) return null;

  return (
    <div className="fixed inset-0 z-50 bg-black/95 backdrop-blur-2xl flex items-center justify-center p-4 animate-in fade-in duration-300 select-none">
      <div className="max-w-xl w-full bg-slate-900/90 border border-blue-500/40 rounded-3xl p-6 md:p-8 space-y-6 shadow-2xl shadow-blue-950/80 text-center relative overflow-hidden">
        {/* Aura brilhante de inicialização de sistema */}
        <div className="absolute -top-32 -left-32 w-64 h-64 bg-blue-600/20 rounded-full blur-3xl animate-pulse" />
        <div className="absolute -bottom-32 -right-32 w-64 h-64 bg-cyan-600/20 rounded-full blur-3xl animate-pulse" />

        {/* Ícone de Progresso */}
        <div className="flex justify-center">
          <div className="relative w-20 h-20 bg-blue-600/10 border border-blue-500/40 rounded-full flex items-center justify-center text-blue-400">
            <RefreshCw className="w-10 h-10 animate-spin" />
            <div className="absolute inset-0 rounded-full border-2 border-cyan-400/40 border-t-transparent animate-spin" />
          </div>
        </div>

        {/* Título e Subtítulo */}
        <div className="space-y-2">
          <h2 className="text-xl md:text-2xl font-black tracking-wider text-slate-100 flex items-center justify-center gap-2">
            <Cpu className="w-6 h-6 text-cyan-400" />
            REINICIANDO HARDWARE & PLANEJADOR MOVEIT
          </h2>
          <p className="text-xs md:text-sm text-slate-400 leading-relaxed max-w-lg mx-auto">
            Por favor, aguarde enquanto a célula restabelece a ponte com a <span className="text-cyan-300 font-bold">Jetson Nano</span>, a câmera e o motor de planejamento ROS 2.
          </p>
        </div>

        {/* Barra de Progresso Gradiente */}
        <div className="space-y-1.5">
          <div className="flex justify-between text-xs font-bold px-1">
            <span className="text-cyan-400">Status de Conectividade</span>
            <span className="text-blue-400 font-mono">{progress}%</span>
          </div>
          <div className="w-full h-3 bg-slate-800 rounded-full overflow-hidden p-0.5 border border-slate-700">
            <div
              className="h-full bg-gradient-to-r from-blue-600 via-cyan-500 to-emerald-400 rounded-full transition-all duration-200 ease-out"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        {/* Checklist das Etapas de Boot */}
        <div className="space-y-2 text-left bg-slate-950/60 p-4 rounded-2xl border border-slate-800/80 text-xs font-medium">
          {steps.map((step, idx) => {
            const isDone = idx < currentStep;
            const isCurrent = idx === currentStep;

            return (
              <div
                key={step.id}
                className={`flex items-center gap-3 p-2 rounded-xl transition-colors ${
                  isCurrent
                    ? 'bg-blue-900/30 text-blue-200 border border-blue-500/30'
                    : isDone
                    ? 'text-emerald-400'
                    : 'text-slate-500'
                }`}
              >
                <div className="shrink-0">
                  {isDone ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  ) : isCurrent ? (
                    <Loader2 className="w-4 h-4 text-cyan-400 animate-spin" />
                  ) : (
                    <div className="w-4 h-4 rounded-full border border-slate-700 flex items-center justify-center text-[10px] text-slate-600">
                      {step.id}
                    </div>
                  )}
                </div>
                <span className={isCurrent ? 'font-bold text-slate-100' : ''}>
                  {step.title}
                </span>
              </div>
            );
          })}
        </div>

        {/* Alerta de Bloqueio do Dashboard */}
        <div className="p-3 bg-blue-950/40 border border-blue-500/30 rounded-xl text-[11px] text-blue-200 flex items-center justify-center gap-2">
          <AlertCircle className="w-4 h-4 text-cyan-400 shrink-0" />
          <span>O acesso ao painel está temporariamente bloqueado até a conclusão do boot.</span>
        </div>
      </div>
    </div>
  );
}

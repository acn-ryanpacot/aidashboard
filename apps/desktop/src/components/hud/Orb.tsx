import { useEffect, useRef } from 'react';

import { useAssistant, useVoiceAssistant } from '../../core/voice/hooks';
import { useUi } from '../../state/uiStore';
import { ORB_PALETTES, OrbRenderer } from './orbRenderer';

const STATE_LABEL = {
  idle: 'Standby',
  listening: 'Listening',
  thinking: 'Processing',
  speaking: 'Speaking',
} as const;

/**
 * The reactive core. Animates at display refresh rate from the live
 * AnalyserNode without re-rendering React. Click (or Enter/Space) to activate.
 */
export function Orb() {
  const assistant = useVoiceAssistant();
  const state = useAssistant((s) => s.state);
  const theme = useUi((s) => s.theme);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rendererRef = useRef<OrbRenderer | null>(null);

  useEffect(() => {
    rendererRef.current?.setPalette(ORB_PALETTES[theme]);
  }, [theme]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;

    const renderer = new OrbRenderer();
    renderer.setPalette(ORB_PALETTES[useUi.getState().theme]);
    rendererRef.current = renderer;
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let spectrum = new Uint8Array(128);
    let frameId = 0;
    const started = performance.now();

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.round(canvas.clientWidth * dpr);
      canvas.height = Math.round(canvas.clientHeight * dpr);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    resize();

    const tick = (now: number) => {
      const analyser = assistant.levelSource();
      let data: Uint8Array | null = null;
      if (analyser) {
        if (spectrum.length !== analyser.frequencyBinCount) {
          spectrum = new Uint8Array(analyser.frequencyBinCount);
        }
        analyser.getByteFrequencyData(spectrum);
        data = spectrum;
      }
      const time = reducedMotion ? 0 : (now - started) / 1000;
      renderer.draw(ctx, canvas.width, canvas.height, {
        time,
        state: assistant.store.getState().state,
        spectrum: data,
      });
      frameId = requestAnimationFrame(tick);
    };
    frameId = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(frameId);
      observer.disconnect();
    };
  }, [assistant]);

  return (
    <div className="relative flex aspect-square w-full max-w-[min(68vh,720px)] items-center justify-center">
      <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" aria-hidden />
      <button
        type="button"
        onClick={() => assistant.activate()}
        className="group relative z-10 h-[34%] w-[34%] rounded-full outline-none focus-visible:ring-2 focus-visible:ring-arc-400/60"
        aria-label="Activate Jarvis"
        title="Activate Jarvis"
      >
        <span className="sr-only">Activate Jarvis</span>
      </button>
      <div className="pointer-events-none absolute bottom-[6%] font-mono text-[10px] tracking-[0.4em] text-arc-300/60 uppercase">
        {STATE_LABEL[state]}
      </div>
    </div>
  );
}

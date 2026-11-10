import { RotateCcw } from 'lucide-react';
import {
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import {
  ApiError,
  type ModelsResponse,
  type RuntimeSettings,
  type VoiceOption,
  coreApi,
} from '../../core/api/client';
import { useAssistant, useVoiceAssistant } from '../../core/voice/hooks';
import { cn } from '../../lib/cn';
import { THEMES, useUi } from '../../state/uiStore';
import { Modal } from '../ui/Modal';
import { diffSettings } from './settingsDiff';

type Draft = { -readonly [K in keyof RuntimeSettings]: RuntimeSettings[K] };

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-8">
      <h3 className="mb-3 font-mono text-[10px] tracking-[0.3em] text-arc-300/70 uppercase">
        {title}
      </h3>
      <div className="space-y-4">{children}</div>
    </section>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 flex items-baseline justify-between">
        <span className="text-[13px] text-white/80">{label}</span>
        {hint && <span className="font-mono text-[10px] text-white/35">{hint}</span>}
      </span>
      {children}
    </label>
  );
}

const inputClass =
  'w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-[13px] text-white/90 placeholder:text-white/25 focus:border-arc-400/50 focus:outline-none';

function Select<T extends string>(props: {
  value: T;
  options: readonly { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <select
      value={props.value}
      onChange={(e) => props.onChange(e.target.value as T)}
      className={cn(inputClass, 'appearance-none')}
    >
      {props.options.map((o) => (
        <option key={o.value} value={o.value} className="bg-ink">
          {o.label}
        </option>
      ))}
    </select>
  );
}

function Slider(props: {
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
}) {
  return (
    <input
      type="range"
      min={props.min}
      max={props.max}
      step={props.step}
      value={props.value}
      onChange={(e) => props.onChange(Number(e.target.value))}
      className="w-full accent-[var(--color-arc-400)]"
    />
  );
}

const lines = (values: readonly string[]) => values.join('\n');
const parseLines = (text: string) =>
  text
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean);

/** Slide-over Settings drawer. Server settings apply live on Save. */
export function SettingsPanel() {
  const overlay = useUi((s) => s.overlay);
  const close = useUi((s) => s.close);
  const ui = useUi();
  const assistant = useVoiceAssistant();
  const soundsEnabled = useAssistant((s) => s.soundsEnabled);
  const caps = useAssistant((s) => s.capabilities);
  const open = overlay === 'settings';

  const [saved, setSaved] = useState<RuntimeSettings | null>(null);
  const [defaults, setDefaults] = useState<RuntimeSettings | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [voices, setVoices] = useState<readonly VoiceOption[]>([]);
  const [models, setModels] = useState<ModelsResponse | null>(null);
  const [status, setStatus] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  /** Set when the user tries to close with unsaved edits. */
  const [confirmingClose, setConfirmingClose] = useState(false);

  const load = useCallback(async () => {
    try {
      const [settings, voiceList, modelList] = await Promise.all([
        coreApi.getSettings(),
        coreApi.listVoices(),
        coreApi.listModels(),
      ]);
      setSaved(settings.values);
      setDefaults(settings.defaults);
      setDraft({ ...settings.values });
      setVoices(voiceList);
      setModels(modelList);
      setStatus(null);
      setConfirmingClose(false);
    } catch (error) {
      setStatus({ kind: 'error', text: `Couldn't load settings: ${String(error)}` });
    }
  }, []);

  useEffect(() => {
    if (open) void load();
  }, [open, load]);

  const patch = useMemo(() => (saved && draft ? diffSettings(saved, draft) : {}), [saved, draft]);
  const dirty = Object.keys(patch).length > 0;
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setDraft((d) => (d ? { ...d, [key]: value } : d));

  /** Send the changed fields; resolves to whether the save succeeded. */
  const save = async (): Promise<boolean> => {
    if (!dirty) return true;
    setBusy(true);
    try {
      const result = await coreApi.updateSettings(patch);
      setSaved(result.values);
      setDraft({ ...result.values });
      setStatus({ kind: 'ok', text: 'Saved — changes are live.' });
      return true;
    } catch (error) {
      setStatus({ kind: 'error', text: error instanceof ApiError ? error.message : String(error) });
      return false;
    } finally {
      setBusy(false);
    }
  };

  // Esc, the backdrop and × all come through here: never drop edits silently.
  const requestClose = () => {
    if (dirty) setConfirmingClose(true);
    else close();
  };

  const saveAndClose = async () => {
    if (await save()) close();
  };

  const discardAndClose = () => {
    setConfirmingClose(false);
    close(); // the draft is reloaded from the core next time the drawer opens
  };

  // Only ask while there is still something to lose.
  const askToSave = confirmingClose && dirty;

  // Ctrl/⌘+S saves while the drawer is open.
  const saveRef = useRef(save);
  useEffect(() => {
    saveRef.current = save;
  });
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
        event.preventDefault();
        void saveRef.current();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open]);

  /** Enter in a single-line field saves (textareas keep Enter for new lines). */
  const onFieldKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    const target = event.target as HTMLElement;
    if (event.key === 'Enter' && target instanceof HTMLInputElement && dirty && !busy) {
      event.preventDefault();
      void save();
    }
  };

  const reset = async () => {
    setBusy(true);
    try {
      const result = await coreApi.resetSettings();
      setSaved(result.values);
      setDraft({ ...result.values });
      setStatus({ kind: 'ok', text: 'Back to the values from .env.' });
    } finally {
      setBusy(false);
    }
  };

  const footer = askToSave ? (
    <div className="flex items-center gap-3">
      <p className="flex-1 text-[12px] text-arc-200" role="alert">
        Save your changes before closing?
      </p>
      <button
        type="button"
        onClick={discardAndClose}
        disabled={busy}
        className="rounded-lg px-3 py-2 text-[12px] text-white/60 transition hover:bg-white/5 hover:text-white/90"
      >
        Discard
      </button>
      <button
        type="button"
        onClick={() => void saveAndClose()}
        disabled={busy}
        autoFocus
        className="rounded-lg bg-arc-400/90 px-4 py-2 text-[12px] font-medium tracking-wide text-void transition hover:bg-arc-300"
      >
        Save &amp; close
      </button>
    </div>
  ) : (
    <div className="flex items-center gap-3">
      <p
        className={cn(
          'flex-1 text-[12px]',
          status?.kind === 'error'
            ? 'text-signal-red/90'
            : dirty
              ? 'text-arc-200'
              : 'text-white/45',
        )}
        role="status"
      >
        {status?.kind === 'error'
          ? status.text
          : dirty
            ? 'Unsaved changes — press Save (Ctrl+S)'
            : (status?.text ?? 'All changes saved')}
      </p>
      <button
        type="button"
        onClick={() => void reset()}
        disabled={busy}
        className="flex items-center gap-1.5 rounded-lg px-3 py-2 text-[12px] text-white/50 transition hover:bg-white/5 hover:text-white/80"
        title="Reset to the values from .env"
      >
        <RotateCcw className="size-3.5" /> Defaults
      </button>
      <button
        type="button"
        onClick={() => void save()}
        disabled={!dirty || busy}
        className="rounded-lg bg-arc-400/90 px-4 py-2 text-[12px] font-medium tracking-wide text-void transition hover:bg-arc-300 disabled:bg-white/5 disabled:text-white/30"
      >
        Save
      </button>
    </div>
  );

  return (
    <Modal
      open={open}
      onClose={requestClose}
      title="Settings"
      variant="drawer"
      footer={draft ? footer : undefined}
    >
      {!draft || !defaults ? (
        <p className="text-[13px] text-white/40">{status?.text ?? 'Loading…'}</p>
      ) : (
        <div onKeyDown={onFieldKeyDown}>
          <Section title="Persona">
            <Field label="Your name" hint="Used in the greeting">
              <input
                className={inputClass}
                value={draft.user_name}
                onChange={(e) => set('user_name', e.target.value)}
              />
            </Field>
            <div className="grid grid-cols-3 gap-3">
              <Field label="Formality">
                <Select
                  value={draft.persona_formality}
                  onChange={(v) => set('persona_formality', v)}
                  options={[
                    { value: 'formal', label: 'Formal' },
                    { value: 'balanced', label: 'Balanced' },
                    { value: 'casual', label: 'Casual' },
                  ]}
                />
              </Field>
              <Field label="Length">
                <Select
                  value={draft.persona_verbosity}
                  onChange={(v) => set('persona_verbosity', v)}
                  options={[
                    { value: 'brief', label: 'Brief' },
                    { value: 'balanced', label: 'Balanced' },
                    { value: 'detailed', label: 'Detailed' },
                  ]}
                />
              </Field>
              <Field label="Humour">
                <Select
                  value={draft.persona_humour}
                  onChange={(v) => set('persona_humour', v)}
                  options={[
                    { value: 'none', label: 'None' },
                    { value: 'dry', label: 'Dry' },
                    { value: 'playful', label: 'Playful' },
                  ]}
                />
              </Field>
            </div>
          </Section>

          <Section title="Voice">
            <Field label="Jarvis's voice">
              <Select
                value={draft.tts_voice}
                onChange={(v) => set('tts_voice', v)}
                options={voices.map((v) => ({ value: v.id, label: v.label }))}
              />
            </Field>
            <Field label="Speaking speed" hint={`${draft.tts_speed.toFixed(2)}×`}>
              <Slider
                value={draft.tts_speed}
                min={0.7}
                max={1.4}
                step={0.05}
                onChange={(v) => set('tts_speed', v)}
              />
            </Field>
          </Section>

          <Section title="Listening">
            <Field
              label="Wake-word sensitivity"
              hint={`threshold ${draft.wake_threshold.toFixed(2)}`}
            >
              {/* Higher sensitivity = lower threshold, so the slider is inverted. */}
              <Slider
                value={1 - draft.wake_threshold}
                min={0.1}
                max={0.8}
                step={0.05}
                onChange={(v) => set('wake_threshold', Number((1 - v).toFixed(2)))}
              />
            </Field>
            <Field label="Pause that ends your turn" hint={`${draft.end_of_speech_ms} ms`}>
              <Slider
                value={draft.end_of_speech_ms}
                min={400}
                max={2000}
                step={50}
                onChange={(v) => set('end_of_speech_ms', v)}
              />
            </Field>
            <Field
              label="Keep listening after an answer"
              hint={draft.follow_up_ms ? `${draft.follow_up_ms / 1000} s` : 'off'}
            >
              <Slider
                value={draft.follow_up_ms}
                min={0}
                max={15000}
                step={1000}
                onChange={(v) => set('follow_up_ms', v)}
              />
            </Field>
            <Field label="Interrupting Jarvis">
              <Select
                value={draft.barge_in}
                onChange={(v) => set('barge_in', v)}
                options={[
                  { value: 'wake_word', label: 'Say the wake word again' },
                  { value: 'voice', label: 'Just start talking (echo-aware)' },
                  { value: 'off', label: 'Off (use Esc)' },
                ]}
              />
            </Field>
            {draft.barge_in === 'voice' && (
              <Field
                label="Talk-over needed to interrupt"
                hint={`${draft.barge_in_min_speech_ms} ms`}
              >
                <Slider
                  value={draft.barge_in_min_speech_ms}
                  min={240}
                  max={1200}
                  step={40}
                  onChange={(v) => set('barge_in_min_speech_ms', v)}
                />
              </Field>
            )}
            {caps?.speaker_verification_enabled && (
              <>
                <Field
                  label="Voice ID strictness"
                  hint={`threshold ${draft.speaker_threshold.toFixed(2)}`}
                >
                  <Slider
                    value={draft.speaker_threshold}
                    min={0.1}
                    max={0.6}
                    step={0.02}
                    onChange={(v) => set('speaker_threshold', v)}
                  />
                </Field>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      close();
                      assistant.enrollVoice();
                    }}
                    className="rounded-lg border border-white/10 px-3 py-2 text-[12px] text-arc-200 transition hover:border-arc-400/50"
                  >
                    {caps.speaker_enrolled ? 'Re-train my voice' : 'Train my voice'}
                  </button>
                  {caps.speaker_enrolled && (
                    <button
                      type="button"
                      onClick={() => void coreApi.resetVoiceprint()}
                      className="rounded-lg px-3 py-2 text-[12px] text-white/45 transition hover:text-signal-red/80"
                    >
                      Forget my voice
                    </button>
                  )}
                </div>
              </>
            )}
          </Section>

          <Section title="Brain">
            <Field label="Language model" hint="Installed in Ollama">
              <Select
                value={draft.llm_model}
                onChange={(v) => set('llm_model', v)}
                options={(models?.available ?? [draft.llm_model]).map((m) => ({
                  value: m,
                  label: m,
                }))}
              />
            </Field>
            <Field label="Home location" hint="Weather & briefing">
              <input
                className={inputClass}
                value={draft.default_location}
                placeholder="e.g. Manila"
                onChange={(e) => set('default_location', e.target.value)}
              />
            </Field>
          </Section>

          <Section title="Briefing & feeds">
            <Field label="Daily spoken briefing" hint={draft.briefing_time ? 'on' : 'off'}>
              <div className="flex items-center gap-3">
                <input
                  type="time"
                  className={cn(inputClass, 'w-36')}
                  value={draft.briefing_time}
                  onChange={(e) => set('briefing_time', e.target.value)}
                />
                {draft.briefing_time && (
                  <button
                    type="button"
                    className="text-[12px] text-white/45 hover:text-white/80"
                    onClick={() => set('briefing_time', '')}
                  >
                    Turn off
                  </button>
                )}
              </div>
            </Field>
            <Field label="News feeds" hint="One RSS/Atom URL per line">
              <textarea
                rows={3}
                className={cn(inputClass, 'font-mono text-[11.5px]')}
                value={lines(draft.news_feeds)}
                onChange={(e) => set('news_feeds', parseLines(e.target.value))}
              />
            </Field>
            <Field label="Calendars" hint="Private ICS addresses, one per line">
              <textarea
                rows={3}
                className={cn(inputClass, 'font-mono text-[11.5px]')}
                value={lines(draft.calendar_urls)}
                placeholder="https://calendar.google.com/calendar/ical/…/basic.ics"
                onChange={(e) => set('calendar_urls', parseLines(e.target.value))}
              />
            </Field>
            <p className="text-[11.5px] leading-relaxed text-white/35">
              Google Calendar: Settings → your calendar → “Secret address in iCal format”. Treat it
              like a password.
            </p>
          </Section>

          <Section title="Appearance (this device)">
            <div className="grid grid-cols-3 gap-2">
              {THEMES.map((theme) => (
                <button
                  key={theme.id}
                  type="button"
                  onClick={() => ui.setTheme(theme.id)}
                  data-theme-preview={theme.id}
                  className={cn(
                    'rounded-xl border p-3 text-left transition',
                    ui.theme === theme.id
                      ? 'border-arc-400/60 bg-white/[0.05]'
                      : 'border-white/8 hover:border-white/20',
                  )}
                >
                  <span className="theme-swatch mb-2 block h-1.5 w-10 rounded-full" />
                  <span className="block text-[12.5px] text-white/85">{theme.label}</span>
                </button>
              ))}
            </div>
            <Field
              label="Ambient mode after"
              hint={ui.ambientAfterMin ? `${ui.ambientAfterMin} min idle` : 'never'}
            >
              <Select
                value={String(ui.ambientAfterMin)}
                onChange={(v) => ui.setAmbientAfter(Number(v))}
                options={[0, 2, 5, 10, 20, 30].map((m) => ({
                  value: String(m),
                  label: m ? `${m} minutes` : 'Never',
                }))}
              />
            </Field>
            <label className="flex items-center justify-between">
              <span className="text-[13px] text-white/80">Interface sounds</span>
              <input
                type="checkbox"
                checked={soundsEnabled}
                onChange={(e) => assistant.setSoundsEnabled(e.target.checked)}
                className="size-4 accent-[var(--color-arc-400)]"
              />
            </label>
          </Section>
        </div>
      )}
    </Modal>
  );
}

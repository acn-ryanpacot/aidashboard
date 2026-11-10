import { StatusDot, type Tone } from '../../components/ui/StatusDot';
import { useAssistant, useVoiceAssistant } from '../../core/voice/hooks';
import { wakePhrase } from '../../core/voice/protocol';
import { formatLatency } from '../../lib/format';

interface Row {
  readonly label: string;
  readonly value: string;
  readonly tone: Tone;
}

const BARGE_IN_LABEL = { off: 'Off', wake_word: 'Wake word', voice: 'Voice' } as const;

/** Live view of the core's subsystems, voice ID and last-turn latency. */
export function CoreLinkWidget() {
  const assistant = useVoiceAssistant();
  const connection = useAssistant((s) => s.connection);
  const caps = useAssistant((s) => s.capabilities);
  const micActive = useAssistant((s) => s.micActive);
  const micError = useAssistant((s) => s.micError);
  const metrics = useAssistant((s) => s.lastMetrics);
  const online = connection === 'online' && caps !== null;

  const rows: Row[] = online
    ? [
        {
          label: 'Wake word',
          value: caps.wake_word_enabled ? (wakePhrase(caps.wake_model) ?? 'On') : 'Manual',
          tone: caps.wake_word_enabled ? 'ok' : 'warn',
        },
        {
          label: 'Speech in / out',
          value: `${caps.speech_input_enabled ? 'Whisper' : '—'} / ${caps.speech_output_enabled ? 'Kokoro' : 'Text'}`,
          tone: caps.speech_input_enabled && caps.speech_output_enabled ? 'ok' : 'warn',
        },
        {
          label: 'Barge-in',
          value: BARGE_IN_LABEL[caps.barge_in],
          tone: caps.barge_in === 'off' ? 'muted' : 'ok',
        },
        {
          label: 'Tools',
          value: `${caps.tools.length} ready`,
          tone: caps.tools.length > 0 ? 'ok' : 'muted',
        },
        {
          label: 'Microphone',
          value: micError ? 'Blocked' : micActive ? 'Live' : 'Muted',
          tone: micError ? 'error' : micActive ? 'ok' : 'muted',
        },
      ]
    : [{ label: 'Core service', value: 'Offline', tone: 'error' }];

  const latencies: [string, number | null | undefined][] = [
    ['Heard', metrics?.stt_ms],
    ['First word', metrics?.first_audio_ms ?? metrics?.first_token_ms],
    ['Answer', metrics?.total_ms],
  ];

  return (
    <div className="flex flex-1 flex-col justify-between">
      <ul className="divide-y divide-white/5">
        {rows.map((row) => (
          <li key={row.label} className="flex items-center justify-between py-1.5">
            <span className="text-[13px] text-white/50">{row.label}</span>
            <span className="flex items-center gap-2 font-mono text-[11px] text-white/75">
              {row.value}
              <StatusDot tone={row.tone} />
            </span>
          </li>
        ))}
        {online && caps.speaker_verification_enabled && (
          <li className="flex items-center justify-between py-1.5">
            <span className="text-[13px] text-white/50">Voice ID</span>
            <button
              type="button"
              onClick={() => assistant.enrollVoice()}
              className="rounded-full border border-white/10 px-2.5 py-0.5 font-mono text-[10px] tracking-wider text-arc-300/80 uppercase transition hover:border-arc-400/50 hover:text-arc-200"
            >
              {caps.speaker_enrolled ? 'Re-train' : 'Enroll'}
            </button>
          </li>
        )}
      </ul>

      <div className="grid grid-cols-3 gap-2 pt-3" aria-label="Last turn latency">
        {latencies.map(([label, value]) => (
          <div key={label} className="rounded-lg bg-white/[0.025] px-2 py-1.5">
            <p className="font-mono text-[9px] tracking-[0.18em] text-white/30 uppercase">
              {label}
            </p>
            <p className="font-mono text-[12px] text-white/80 tabular-nums">
              {formatLatency(value)}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}

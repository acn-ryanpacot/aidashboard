import { StatusDot, type Tone } from '../../components/ui/StatusDot';
import { useAssistant } from '../../core/voice/hooks';
import { wakePhrase } from '../../core/voice/protocol';

interface Row {
  readonly label: string;
  readonly value: string;
  readonly tone: Tone;
}

/** Live view of which subsystems of the core service are available. */
export function CoreLinkWidget() {
  const connection = useAssistant((s) => s.connection);
  const caps = useAssistant((s) => s.capabilities);
  const micActive = useAssistant((s) => s.micActive);
  const micError = useAssistant((s) => s.micError);
  const online = connection === 'online' && caps !== null;

  const rows: Row[] = [
    {
      label: 'Wake word',
      value: online
        ? caps.wake_word_enabled
          ? (wakePhrase(caps.wake_model) ?? 'On')
          : 'Manual'
        : '—',
      tone: online ? (caps.wake_word_enabled ? 'ok' : 'warn') : 'muted',
    },
    {
      label: 'Speech in',
      value: online ? (caps.speech_input_enabled ? 'Whisper' : 'Disabled') : '—',
      tone: online ? (caps.speech_input_enabled ? 'ok' : 'warn') : 'muted',
    },
    {
      label: 'Speech out',
      value: online ? (caps.speech_output_enabled ? 'Kokoro' : 'Text only') : '—',
      tone: online ? (caps.speech_output_enabled ? 'ok' : 'warn') : 'muted',
    },
    {
      label: 'Microphone',
      value: micError ? 'Blocked' : micActive ? 'Live' : 'Muted',
      tone: micError ? 'error' : micActive ? 'ok' : 'muted',
    },
  ];

  return (
    <ul className="flex flex-1 flex-col justify-center divide-y divide-white/5">
      {rows.map((row) => (
        <li key={row.label} className="flex items-center justify-between py-2">
          <span className="text-[13px] text-white/50">{row.label}</span>
          <span className="flex items-center gap-2 font-mono text-[11px] text-white/75">
            {row.value}
            <StatusDot tone={row.tone} />
          </span>
        </li>
      ))}
    </ul>
  );
}

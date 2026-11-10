/**
 * Gapless playback of speech segments, with live caption tracking.
 *
 * @module
 */
import { activeWordIndex } from './captions';
import type { SpeechSegmentMessage } from './protocol';

/** The caption to display right now. */
export interface ActiveCaption {
  readonly segment: SpeechSegmentMessage;
  /** Index into `segment.words` of the word being spoken (-1 = not yet). */
  readonly wordIndex: number;
}

interface ScheduledSegment {
  readonly segment: SpeechSegmentMessage;
  readonly source: AudioBufferSourceNode;
  readonly startsAt: number;
  readonly endsAt: number;
}

/** Small lead time so the first segment never starts in the past (s). */
const SCHEDULE_LEAD_S = 0.05;

/**
 * Decodes WAV segments and schedules them back-to-back on the shared
 * AudioContext. All audio flows through {@link analyser}, which is what makes
 * the orb react to every syllable.
 */
export class SpeechPlayer {
  readonly analyser: AnalyserNode;
  readonly #context: AudioContext;
  readonly #onEnded: (segmentId: string) => void;
  #scheduled: ScheduledSegment[] = [];
  #nextStart = 0;
  #queue: Promise<void> = Promise.resolve();
  #generation = 0;

  /**
   * @param context - Shared audio context.
   * @param onEnded - Called with the segment id when a segment finishes playing.
   */
  constructor(context: AudioContext, onEnded: (segmentId: string) => void) {
    this.#context = context;
    this.#onEnded = onEnded;
    this.analyser = context.createAnalyser();
    this.analyser.fftSize = 256;
    this.analyser.smoothingTimeConstant = 0.72;
    this.analyser.connect(context.destination);
  }

  /** Whether any audio is playing or scheduled. */
  get busy(): boolean {
    return this.#scheduled.length > 0;
  }

  /**
   * Queue a segment for playback. Decoding happens in order, so segments are
   * always heard in the order they arrived.
   */
  enqueue(segment: SpeechSegmentMessage, wav: ArrayBuffer): Promise<void> {
    const generation = this.#generation;
    this.#queue = this.#queue
      .then(async () => {
        const buffer = await this.#context.decodeAudioData(wav);
        if (generation !== this.#generation) return; // stopped meanwhile
        this.#schedule(segment, buffer, generation);
      })
      .catch((error: unknown) => {
        console.error('Failed to play speech segment', error);
        this.#onEnded(segment.segment_id);
      });
    return this.#queue;
  }

  /** The caption for whatever is audible at this instant. */
  activeCaption(): ActiveCaption | null {
    const now = this.#context.currentTime;
    const current = this.#scheduled.find((s) => now >= s.startsAt && now < s.endsAt);
    if (!current) return null;
    return {
      segment: current.segment,
      wordIndex: activeWordIndex(current.segment.words, now - current.startsAt),
    };
  }

  /** Stop immediately and drop everything queued. */
  stop(): void {
    this.#generation += 1;
    for (const { source } of this.#scheduled) {
      source.onended = null;
      source.stop();
    }
    this.#scheduled = [];
    this.#nextStart = 0;
  }

  #schedule(segment: SpeechSegmentMessage, buffer: AudioBuffer, generation: number): void {
    const source = this.#context.createBufferSource();
    source.buffer = buffer;
    source.connect(this.analyser);

    const startsAt = Math.max(this.#context.currentTime + SCHEDULE_LEAD_S, this.#nextStart);
    const entry: ScheduledSegment = {
      segment,
      source,
      startsAt,
      endsAt: startsAt + buffer.duration,
    };
    this.#nextStart = entry.endsAt;
    this.#scheduled.push(entry);

    source.onended = () => {
      if (generation !== this.#generation) return;
      this.#scheduled = this.#scheduled.filter((s) => s !== entry);
      this.#onEnded(segment.segment_id);
    };
    source.start(startsAt);
  }
}

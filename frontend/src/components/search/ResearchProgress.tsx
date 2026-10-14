import { useEffect, useState } from 'react';
import { CheckCircle2, Circle, Loader2, Radio } from 'lucide-react';
import type { ResearchStage } from '../../types/api';

/**
 * Research progress panel — stages advance only when the backend actually
 * reaches that pipeline step (SSE `stage` events from POST /api/research/stream).
 * Nothing here animates on a fake timeline: if no event has arrived yet, the
 * first stage is shown as active and the rest as pending.
 *
 * The extraction stage is only listed when it can genuinely run for this
 * request (live search + extraction enabled), so demo runs never show a
 * stage that was never attempted.
 */

interface StageDef {
  key: ResearchStage;
  label: string;
  description: string;
}

const STAGES: StageDef[] = [
  {
    key: 'searching',
    label: 'Collecting search results',
    description: 'Querying the search backend and normalizing results.',
  },
  {
    key: 'extracting',
    label: 'Retrieving source pages',
    description: 'Fetching publicly available pages (SSRF-protected, best effort).',
  },
  {
    key: 'analyzing',
    label: 'Analyzing evidence',
    description: 'Building themes, claims, and coverage from collected sources.',
  },
  {
    key: 'validating',
    label: 'Validating citations',
    description: 'Checking every citation against the sources actually collected.',
  },
];

interface ResearchProgressProps {
  /** Latest stage reported by the backend, or null before the first event. */
  stage: ResearchStage | null;
  /** Whether page extraction will run for this request. */
  showExtraction: boolean;
}

export default function ResearchProgress({ stage, showExtraction }: ResearchProgressProps) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const id = window.setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => window.clearInterval(id);
  }, []);

  const stages = STAGES.filter((s) => s.key !== 'extracting' || showExtraction);
  // -1 = no event yet (fallback mode or before the first stage event).
  const currentIdx = stage ? stages.findIndex((s) => s.key === stage) : -1;
  const activeIdx = currentIdx === -1 ? 0 : currentIdx;

  return (
    <section className="panel p-5" aria-labelledby="research-progress">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h3 id="research-progress" className="section-title flex items-center gap-2">
          <Radio size={16} aria-hidden className="text-violetui-400" />
          Research in progress
        </h3>
        <span
          className="font-mono text-2xs tabular-nums text-slateui-400"
          aria-label={`${elapsed} seconds elapsed`}
        >
          {elapsed}s
        </span>
      </div>

      <ol className="space-y-3" role="status" aria-live="polite">
        {stages.map((s, i) => {
          const done = i < activeIdx;
          const active = i === activeIdx;
          return (
            <li key={s.key} className="flex items-start gap-3">
              <span
                className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center ${
                  done
                    ? 'text-cyanui-400'
                    : active
                      ? 'text-violetui-400'
                      : 'text-slateui-500'
                }`}
                aria-hidden
              >
                {done ? (
                  <CheckCircle2 size={18} />
                ) : active ? (
                  <Loader2 size={18} className="animate-spin" />
                ) : (
                  <Circle size={16} />
                )}
              </span>
              <div className="min-w-0">
                <p
                  className={`text-sm font-medium ${
                    done || active ? 'text-slateui-100' : 'text-slateui-400'
                  }`}
                >
                  {s.label}
                  {done && <span className="sr-only"> (completed)</span>}
                  {active && <span className="sr-only"> (in progress)</span>}
                </p>
                <p className="text-2xs leading-relaxed text-slateui-500">{s.description}</p>
              </div>
            </li>
          );
        })}
      </ol>

      <p className="mt-4 border-t border-slateui-700/40 pt-3 text-2xs text-slateui-500">
        Stages update as each backend step actually starts — this is not an estimated timeline.
        Analysis runs over the collected sources only.
      </p>
    </section>
  );
}

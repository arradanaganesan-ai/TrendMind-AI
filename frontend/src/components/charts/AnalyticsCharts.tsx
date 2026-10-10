import { useMemo } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { BarChart3, PieChart as PieIcon } from 'lucide-react';
import type { EvidenceCoverage, SourceRef, ThemeCard } from '../../types/api';

const AXIS_COLOR = '#5b6790';
const GRID_COLOR = 'rgba(148,163,184,0.10)';

const TOOLTIP_STYLE = {
  backgroundColor: '#0d1224',
  border: '1px solid rgba(148,163,184,0.25)',
  borderRadius: 8,
  fontSize: 12,
  color: '#dde3f2',
} as const;

function ChartFrame({
  title,
  description,
  children,
  empty,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
  empty?: boolean;
}) {
  return (
    <section className="panel p-5" aria-label={title}>
      <h3 className="section-title mb-1">{title}</h3>
      <p className="mb-4 text-xs text-slateui-400">{description}</p>
      {empty ? (
        <div className="grid h-52 place-items-center rounded-md border border-dashed border-slateui-600/60 bg-midnight-850 text-center">
          <div className="px-4">
            <BarChart3 size={22} className="mx-auto mb-2 text-slateui-500" aria-hidden />
            <p className="text-sm text-slateui-400">No computed data available yet.</p>
          </div>
        </div>
      ) : (
        <div className="h-56 w-full">{children}</div>
      )}
      {/* Accessible text alternative for the chart */}
      <p className="sr-only">{description}</p>
    </section>
  );
}

/** A. Theme distribution — how many collected sources mention each theme. */
export function ThemeDistributionChart({ themes }: { themes: ThemeCard[] }) {
  const data = useMemo(
    () =>
      themes
        .filter((t) => t.mentionCount > 0)
        .slice(0, 8)
        .map((t) => ({ name: t.name.length > 22 ? `${t.name.slice(0, 22)}…` : t.name, sources: t.mentionCount })),
    [themes],
  );

  return (
    <ChartFrame
      title="Theme distribution"
      description={`Number of collected sources mentioning each identified theme. ${
        data.length ? data.map((d) => `${d.name}: ${d.sources}`).join('; ') : 'No theme data.'
      }`}
      empty={data.length === 0}
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 4, right: 8, left: -18, bottom: 4 }}>
          <CartesianGrid stroke={GRID_COLOR} vertical={false} />
          <XAxis dataKey="name" tick={{ fill: AXIS_COLOR, fontSize: 11 }} interval={0} angle={-18} textAnchor="end" height={54} />
          <YAxis allowDecimals={false} tick={{ fill: AXIS_COLOR, fontSize: 11 }} />
          <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: 'rgba(139,108,255,0.08)' }} />
          <Bar dataKey="sources" name="Sources mentioning theme" fill="#8b6cff" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

/** B. Source distribution — collected results grouped by domain. */
export function SourceDistributionChart({ sources }: { sources: SourceRef[] }) {
  const data = useMemo(() => {
    const counts = new Map<string, number>();
    for (const s of sources) counts.set(s.domain, (counts.get(s.domain) ?? 0) + 1);
    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([domain, count]) => ({ name: domain, value: count }));
  }, [sources]);

  const PALETTE = ['#8b6cff', '#3b82f6', '#22d3ee', '#a78bff', '#60a5fa', '#5ee7f7', '#6d4aff', '#93c5fd'];

  return (
    <ChartFrame
      title="Source distribution"
      description={`Collected search results grouped by domain. ${
        data.length ? data.map((d) => `${d.name}: ${d.value}`).join('; ') : 'No source data.'
      }`}
      empty={data.length === 0}
    >
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            innerRadius={48}
            outerRadius={78}
            paddingAngle={2}
            stroke="#0a0e1c"
          >
            {data.map((_, i) => (
              <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
            ))}
          </Pie>
          <Tooltip contentStyle={TOOLTIP_STYLE} />
          <Legend
            verticalAlign="bottom"
            height={36}
            formatter={(value: string) => (
              <span style={{ color: '#b3bcd6', fontSize: 11 }}>{value}</span>
            )}
          />
        </PieChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

/** C. Evidence coverage — claims by grounding status. */
export function EvidenceCoverageChart({ coverage }: { coverage: EvidenceCoverage }) {
  const data = useMemo(
    () => [
      { name: 'Supported by sources', value: coverage.supported, fill: '#22d3ee' },
      { name: 'Conflicting evidence', value: coverage.conflicting, fill: '#f59e0b' },
      { name: 'Insufficient evidence', value: coverage.insufficient, fill: '#5b6790' },
    ],
    [coverage],
  );
  const total = data.reduce((sum, d) => sum + d.value, 0);

  return (
    <ChartFrame
      title="Evidence coverage"
      description={`How claims in this report are grounded: ${data
        .map((d) => `${d.name}: ${d.value}`)
        .join(', ')}.`}
      empty={total === 0}
    >
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie data={data} dataKey="value" nameKey="name" outerRadius={82} stroke="#0a0e1c">
            {data.map((d) => (
              <Cell key={d.name} fill={d.fill} />
            ))}
          </Pie>
          <Tooltip contentStyle={TOOLTIP_STYLE} />
          <Legend
            verticalAlign="bottom"
            height={36}
            formatter={(value: string) => (
              <span style={{ color: '#b3bcd6', fontSize: 11 }}>{value}</span>
            )}
          />
        </PieChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

export { ChartFrame };
export const EmptyChartIcon = PieIcon;

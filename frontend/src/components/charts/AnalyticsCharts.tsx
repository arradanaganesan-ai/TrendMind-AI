import { useMemo } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { BarChart3 } from 'lucide-react';
import type {
  ActivityPoint,
  EvidenceCoverage,
  SourceRef,
  ThemeCard,
  TimelineSnapshot,
} from '../../types/api';
import { useTheme } from '../ui/ThemeProvider';

/**
 * Chart colors are read from the design-token CSS variables
 * (src/styles/index.css) so charts follow the active light/dark theme.
 * The hook subscribes to the theme context, so components re-render
 * with fresh computed colors whenever the theme changes.
 */
interface ChartTokens {
  axis: string;
  grid: string;
  tooltip: { backgroundColor: string; border: string; borderRadius: number; fontSize: number; color: string };
  pieStroke: string;
  legendText: string;
  cursor: string;
  barFill: string;
  palette: string[];
  coverage: { supported: string; conflicting: string; insufficient: string };
}

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function useChartTokens(): ChartTokens {
  const { resolved } = useTheme();
  return useMemo(() => {
    const rgb = (name: string) => `rgb(${cssVar(name)})`;
    const rgba = (name: string, alpha: number) => `rgb(${cssVar(name)} / ${alpha})`;
    return {
      axis: rgb('--tm-chart-axis'),
      grid: rgba('--tm-chart-axis', Number(cssVar('--tm-chart-grid-alpha')) || 0.1),
      tooltip: {
        backgroundColor: rgb('--tm-chart-tooltip-bg'),
        border: `1px solid ${rgba('--tm-slateui-400', Number(cssVar('--tm-chart-tooltip-border-alpha')) || 0.25)}`,
        borderRadius: 8,
        fontSize: 12,
        color: rgb('--tm-chart-tooltip-text'),
      },
      pieStroke: rgb('--tm-chart-pie-stroke'),
      legendText: rgb('--tm-chart-legend-text'),
      cursor: rgba('--tm-violetui-500', 0.08),
      barFill: rgb('--tm-violetui-500'),
      palette: [
        rgb('--tm-violetui-500'),
        rgb('--tm-blueui-500'),
        rgb('--tm-cyanui-500'),
        rgb('--tm-violetui-400'),
        rgb('--tm-blueui-400'),
        rgb('--tm-cyanui-400'),
        rgb('--tm-violetui-600'),
        rgb('--tm-blueui-300'),
      ],
      coverage: {
        supported: rgb('--tm-cyanui-500'),
        conflicting: rgb('--tm-amber-400'),
        insufficient: rgb('--tm-slateui-400'),
      },
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-read on theme change
  }, [resolved]);
}

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
  const tokens = useChartTokens();
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
          <CartesianGrid stroke={tokens.grid} vertical={false} />
          <XAxis dataKey="name" tick={{ fill: tokens.axis, fontSize: 11 }} interval={0} angle={-18} textAnchor="end" height={54} />
          <YAxis allowDecimals={false} tick={{ fill: tokens.axis, fontSize: 11 }} />
          <Tooltip contentStyle={tokens.tooltip} cursor={{ fill: tokens.cursor }} />
          <Bar dataKey="sources" name="Sources mentioning theme" fill={tokens.barFill} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

/** B. Source distribution — collected results grouped by domain. */
export function SourceDistributionChart({ sources }: { sources: SourceRef[] }) {
  const tokens = useChartTokens();
  const data = useMemo(() => {
    const counts = new Map<string, number>();
    for (const s of sources) counts.set(s.domain, (counts.get(s.domain) ?? 0) + 1);
    return [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .map(([domain, count]) => ({ name: domain, value: count }));
  }, [sources]);

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
            stroke={tokens.pieStroke}
          >
            {data.map((_, i) => (
              <Cell key={i} fill={tokens.palette[i % tokens.palette.length]} />
            ))}
          </Pie>
          <Tooltip contentStyle={tokens.tooltip} />
          <Legend
            verticalAlign="bottom"
            height={36}
            formatter={(value: string) => (
              <span style={{ color: tokens.legendText, fontSize: 11 }}>{value}</span>
            )}
          />
        </PieChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

/** C. Evidence coverage — claims by grounding status. */
export function EvidenceCoverageChart({ coverage }: { coverage: EvidenceCoverage }) {
  const tokens = useChartTokens();
  const data = useMemo(
    () => [
      { name: 'Supported by sources', value: coverage.supported, fill: tokens.coverage.supported },
      { name: 'Conflicting evidence', value: coverage.conflicting, fill: tokens.coverage.conflicting },
      { name: 'Insufficient evidence', value: coverage.insufficient, fill: tokens.coverage.insufficient },
    ],
    [coverage, tokens],
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
          <Pie data={data} dataKey="value" nameKey="name" outerRadius={82} stroke={tokens.pieStroke}>
            {data.map((d) => (
              <Cell key={d.name} fill={d.fill} />
            ))}
          </Pie>
          <Tooltip contentStyle={tokens.tooltip} />
          <Legend
            verticalAlign="bottom"
            height={36}
            formatter={(value: string) => (
              <span style={{ color: tokens.legendText, fontSize: 11 }}>{value}</span>
            )}
          />
        </PieChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

/** D. Research activity — daily runs over the last N days (real rows, zero-filled). */
export function ActivityChart({ points }: { points: ActivityPoint[] }) {
  const tokens = useChartTokens();
  const emerald = `rgb(${cssVar('--tm-emerald-400')})`;
  const data = useMemo(
    () =>
      points.map((p) => ({
        date: p.date.slice(5), // MM-DD
        completed: p.completed,
        other: Math.max(0, p.count - p.completed),
      })),
    [points],
  );
  const total = points.reduce((s, p) => s + p.count, 0);
  const done = points.reduce((s, p) => s + p.completed, 0);
  const busiest = points.reduce(
    (best, p) => (p.count > best.count ? p : best),
    { date: '', count: 0, completed: 0 },
  );
  const description = total
    ? `Daily research runs for the last ${points.length} days: ${total} total, ${done} completed. ` +
      `Busiest day ${busiest.date} with ${busiest.count} run${busiest.count === 1 ? '' : 's'}.`
    : `No research runs were created in the last ${points.length} days.`;

  return (
    <ChartFrame
      title="Activity over time"
      description={description}
      empty={total === 0}
    >
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 4, right: 8, left: -18, bottom: 4 }}>
          <CartesianGrid stroke={tokens.grid} vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fill: tokens.axis, fontSize: 10 }}
            interval={Math.max(0, Math.ceil(data.length / 8) - 1)}
          />
          <YAxis allowDecimals={false} tick={{ fill: tokens.axis, fontSize: 11 }} />
          <Tooltip
            contentStyle={tokens.tooltip}
            cursor={{ fill: tokens.cursor }}
            formatter={(value: number, name: string) => [value, name]}
          />
          <Bar
            dataKey="completed"
            name="Completed"
            stackId="runs"
            fill={emerald}
            radius={[0, 0, 0, 0]}
          />
          <Bar
            dataKey="other"
            name="Not completed"
            stackId="runs"
            fill={tokens.barFill}
            radius={[4, 4, 0, 0]}
          />
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

/**
 * E. Trend history — real per-snapshot counts over dated snapshots.
 *
 * Parent pages MUST render this only when >= 2 dated snapshots exist: a
 * single point cannot show a trend, and no value here is interpolated.
 */
export function TrendHistoryChart({ snapshots }: { snapshots: TimelineSnapshot[] }) {
  const tokens = useChartTokens();
  const emerald = `rgb(${cssVar('--tm-emerald-400')})`;
  const data = useMemo(
    () =>
      snapshots.map((s) => ({
        // Short id disambiguates snapshots taken on the same day.
        label: `${s.searchedAt.slice(0, 10)} · ${s.researchId.slice(-4)}`,
        sources: s.sourceCount,
        domains: s.domainCount,
        findings: s.findingCount,
      })),
    [snapshots],
  );
  const description = `Per-snapshot counts from real stored runs: ${data
    .map((d) => `${d.label}: ${d.sources} sources, ${d.domains} domains, ${d.findings} findings`)
    .join('; ')}.`;

  return (
    <ChartFrame
      title="History over time"
      description={description}
      empty={data.length < 2}
    >
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 8, left: -18, bottom: 4 }}>
          <CartesianGrid stroke={tokens.grid} vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fill: tokens.axis, fontSize: 10 }}
            interval={Math.max(0, Math.ceil(data.length / 6) - 1)}
          />
          <YAxis allowDecimals={false} tick={{ fill: tokens.axis, fontSize: 11 }} />
          <Tooltip contentStyle={tokens.tooltip} cursor={{ stroke: tokens.cursor }} />
          <Legend
            verticalAlign="bottom"
            height={30}
            formatter={(value: string) => (
              <span style={{ color: tokens.legendText, fontSize: 11 }}>{value}</span>
            )}
          />
          <Line
            type="monotone"
            dataKey="sources"
            name="Sources"
            stroke={tokens.barFill}
            strokeWidth={2}
            dot={{ r: 3 }}
          />
          <Line
            type="monotone"
            dataKey="domains"
            name="Domains"
            stroke={emerald}
            strokeWidth={2}
            dot={{ r: 3 }}
          />
          <Line
            type="monotone"
            dataKey="findings"
            name="Findings"
            stroke={tokens.coverage.supported}
            strokeWidth={2}
            dot={{ r: 3 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

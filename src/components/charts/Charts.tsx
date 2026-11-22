import { useId } from 'react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts'

const AXIS = {
  stroke: 'var(--axis)',
  fontSize: 10,
  tickLine: false,
  axisLine: false,
} as const

const GRID = 'var(--grid-line)'

const TOOLTIP_STYLE = {
  background: 'var(--tooltip-bg)',
  border: '1px solid var(--tooltip-border)',
  borderRadius: 8,
  fontSize: 11,
  color: 'var(--tooltip-fg)',
  padding: '6px 9px',
} as const

const LABEL_STYLE = { color: 'var(--muted)' } as const

/**
 * Long trajectories are thinned for drawing only: every nth point plus the last
 * one. The data behind the chart is untouched.
 */
function thin<T>(data: T[], max = 480): T[] {
  if (data.length <= max) return data
  const step = Math.ceil(data.length / max)
  return data.filter((_, index) => index % step === 0 || index === data.length - 1)
}

export interface SeriesPoint {
  [key: string]: number | string | null
}

export function TelemetryChart({
  data,
  xKey,
  series,
  height = 180,
  yUnit,
  reference,
}: {
  data: SeriesPoint[]
  xKey: string
  series: { key: string; color: string; label: string }[]
  height?: number
  yUnit?: string
  reference?: { y: number; label: string }
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={thin(data)} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey={xKey} {...AXIS} />
        <YAxis {...AXIS} width={38} unit={yUnit} />
        <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={LABEL_STYLE} />
        {reference && (
          <ReferenceLine y={reference.y} stroke="var(--warn)" strokeOpacity={0.55} strokeDasharray="4 4"
            label={{ value: reference.label, fill: 'var(--warn)', fontSize: 9, position: 'insideTopRight' }} />
        )}
        {series.map((item) => (
          <Line
            key={item.key}
            type="monotone"
            dataKey={item.key}
            name={item.label}
            stroke={item.color}
            strokeWidth={1.6}
            dot={false}
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  )
}

export function AreaTrend({
  data,
  xKey,
  yKey,
  color = 'var(--chart-1)',
  height = 150,
  name,
}: {
  data: SeriesPoint[]
  xKey: string
  yKey: string
  color?: string
  height?: number
  name?: string
}) {
  // Unique per chart instance: two panels with the same yKey must not share a
  // gradient id, which silently painted the wrong colour before.
  const gradientId = `grad-${useId().replace(/[^a-zA-Z0-9_-]/g, '')}-${yKey}`
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={thin(data)} margin={{ top: 6, right: 8, left: -20, bottom: 0 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.32} />
            <stop offset="100%" stopColor={color} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey={xKey} {...AXIS} />
        <YAxis {...AXIS} width={38} />
        <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={LABEL_STYLE} />
        <Area type="monotone" dataKey={yKey} name={name ?? yKey} stroke={color} strokeWidth={1.6}
          fill={`url(#${gradientId})`} isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  )
}

export function BarsChart({
  data,
  xKey,
  yKey,
  height = 180,
  color = 'var(--chart-1)',
  horizontal = false,
}: {
  data: SeriesPoint[]
  xKey: string
  yKey: string
  height?: number
  color?: string
  horizontal?: boolean
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={thin(data)} layout={horizontal ? 'vertical' : 'horizontal'}
        margin={{ top: 6, right: 12, left: horizontal ? 8 : -22, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={horizontal} horizontal={!horizontal} />
        {horizontal ? (
          <>
            <XAxis type="number" {...AXIS} />
            <YAxis type="category" dataKey={xKey} {...AXIS} width={110} />
          </>
        ) : (
          <>
            <XAxis dataKey={xKey} {...AXIS} />
            <YAxis {...AXIS} width={38} />
          </>
        )}
        <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={LABEL_STYLE} />
        <Bar dataKey={yKey} fill={color} radius={[3, 3, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  )
}

export function ScatterPlot({
  data,
  height = 260,
  xLabel,
  yLabel,
  color = 'var(--chart-1)',
}: {
  data: { x: number; y: number; z?: number; name?: string }[]
  height?: number
  xLabel: string
  yLabel: string
  color?: string
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ScatterChart margin={{ top: 8, right: 12, bottom: 4, left: -14 }}>
        <CartesianGrid stroke={GRID} />
        <XAxis type="number" dataKey="x" name={xLabel} {...AXIS}
          label={{ value: xLabel, fill: 'var(--faint)', fontSize: 10, position: 'insideBottom', offset: -2 }} />
        <YAxis type="number" dataKey="y" name={yLabel} {...AXIS} width={40}
          label={{ value: yLabel, fill: 'var(--faint)', fontSize: 10, angle: -90, position: 'insideLeft' }} />
        <ZAxis type="number" dataKey="z" range={[24, 90]} />
        <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ strokeDasharray: '3 3' }} />
        <Scatter data={thin(data, 600)} fill={color} fillOpacity={0.62} isAnimationActive={false} />
      </ScatterChart>
    </ResponsiveContainer>
  )
}

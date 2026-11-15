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
  stroke: 'rgb(139 155 171 / 0.55)',
  fontSize: 10,
  tickLine: false,
  axisLine: false,
} as const

const GRID = 'rgb(148 178 205 / 0.07)'

const TOOLTIP_STYLE = {
  background: '#0d131a',
  border: '1px solid rgb(148 178 205 / 0.22)',
  borderRadius: 8,
  fontSize: 11,
  color: '#e8f0f7',
  padding: '6px 9px',
} as const

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
      <LineChart data={data} margin={{ top: 6, right: 8, left: -18, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey={xKey} {...AXIS} />
        <YAxis {...AXIS} width={38} unit={yUnit} />
        <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={{ color: '#8b9bab' }} />
        {reference && (
          <ReferenceLine y={reference.y} stroke="rgb(245 165 36 / 0.5)" strokeDasharray="4 4"
            label={{ value: reference.label, fill: '#f5a524', fontSize: 9, position: 'insideTopRight' }} />
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
  color = '#35d6f2',
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
  const gradientId = `grad-${yKey}`
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 6, right: 8, left: -20, bottom: 0 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.32} />
            <stop offset="100%" stopColor={color} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey={xKey} {...AXIS} />
        <YAxis {...AXIS} width={38} />
        <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={{ color: '#8b9bab' }} />
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
  color = '#35d6f2',
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
      <BarChart data={data} layout={horizontal ? 'vertical' : 'horizontal'}
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
        <Tooltip contentStyle={TOOLTIP_STYLE} labelStyle={{ color: '#8b9bab' }} />
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
  color = '#35d6f2',
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
          label={{ value: xLabel, fill: '#5d6b7a', fontSize: 10, position: 'insideBottom', offset: -2 }} />
        <YAxis type="number" dataKey="y" name={yLabel} {...AXIS} width={40}
          label={{ value: yLabel, fill: '#5d6b7a', fontSize: 10, angle: -90, position: 'insideLeft' }} />
        <ZAxis type="number" dataKey="z" range={[24, 90]} />
        <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ strokeDasharray: '3 3' }} />
        <Scatter data={data} fill={color} fillOpacity={0.62} isAnimationActive={false} />
      </ScatterChart>
    </ResponsiveContainer>
  )
}

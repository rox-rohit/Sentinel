import type { TwinReading, TwinSensorDef } from '../../lib/twin'

const NODES: { key: string; x: number; y: number; place: 'above' | 'below' }[] = [
  { key: 's2', x: 96, y: 58, place: 'above' },
  { key: 's3', x: 196, y: 58, place: 'above' },
  { key: 's4', x: 258, y: 58, place: 'above' },
  { key: 's7', x: 322, y: 58, place: 'above' },
  { key: 's8', x: 406, y: 142, place: 'below' },
  { key: 's11', x: 384, y: 58, place: 'above' },
  { key: 's12', x: 476, y: 58, place: 'above' },
  { key: 's15', x: 546, y: 58, place: 'above' },
]

function tone(z: number | undefined): string {
  if (z === undefined) return 'var(--faint)'
  const magnitude = Math.abs(z)
  if (magnitude < 1.5) return 'var(--good)'
  if (magnitude < 2.5) return 'var(--accent)'
  if (magnitude < 3.5) return 'var(--warn)'
  return 'var(--critical)'
}

/**
 * A schematic twin: casing, compressor stages, combustor and turbine with the
 * eight C-MAPSS channels the platform models. Node colour is the channel's
 * deviation from its own baseline, not a decoration.
 */
export function TwinSchematic({
  readings,
  sensors,
  running,
  assetId,
}: {
  readings: TwinReading[]
  sensors: TwinSensorDef[]
  running: boolean
  assetId: string | null
}) {
  const byKey = new Map(readings.map((entry) => [entry.sensor, entry]))
  const labelFor = (key: string) =>
    sensors.find((sensor) => sensor.key === key)?.label ?? key

  return (
    <div className="w-full">
      <svg viewBox="0 0 640 190" className="h-auto w-full" role="img"
        aria-label={`Digital twin schematic${assetId ? ` for ${assetId}` : ''}`}>
        <defs>
          <linearGradient id="twin-casing" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--overlay-3)" />
            <stop offset="100%" stopColor="var(--overlay-1)" />
          </linearGradient>
          <linearGradient id="twin-combustor" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="var(--warn-soft)" />
            <stop offset="100%" stopColor="var(--accent-soft)" />
          </linearGradient>
        </defs>

        <path
          d="M42 82 Q42 64 68 64 H512 Q556 64 578 100 Q556 136 512 136 H68 Q42 136 42 118 Z"
          fill="url(#twin-casing)"
          stroke="var(--line-strong)"
          strokeWidth="1.2"
        />

        {/* intake and fan */}
        <circle cx="74" cy="100" r="20" fill="none" stroke="var(--line-strong)" />
        <circle cx="74" cy="100" r="4" fill="var(--faint)" />
        {[0, 45, 90, 135].map((angle) => (
          <line key={angle} x1={74 + 6 * Math.cos((angle * Math.PI) / 180)}
            y1={100 + 6 * Math.sin((angle * Math.PI) / 180)}
            x2={74 + 18 * Math.cos((angle * Math.PI) / 180)}
            y2={100 + 18 * Math.sin((angle * Math.PI) / 180)}
            stroke="var(--line-strong)" strokeWidth="1.4" />
        ))}

        {/* compressor stages */}
        {[132, 158, 184, 210, 236, 262].map((x, index) => (
          <rect key={x} x={x} y={82} width="7" height={36 - index * 1.2} rx="2"
            fill="var(--line-strong)" opacity={0.5 + index * 0.06} />
        ))}

        {/* combustor */}
        <rect x="306" y="80" width="76" height="40" rx="10" fill="url(#twin-combustor)"
          stroke="var(--line-strong)" />
        <path d="M318 100 Q332 88 344 100 Q356 112 368 100" fill="none" stroke="var(--warn)"
          strokeWidth="1.4" opacity="0.8" />

        {/* turbine stages */}
        {[398, 424, 450, 476, 502].map((x, index) => (
          <rect key={x} x={x} y={84 - index * 0.6} width="6" height={32 + index * 1.2} rx="2"
            fill="var(--line-strong)" opacity={0.8 - index * 0.08} />
        ))}

        {/* shaft */}
        <line x1="96" y1="100" x2="540" y2="100" stroke="var(--line-strong)" strokeWidth="2"
          strokeDasharray="7 6" className={running ? 'twin-flow' : undefined} />

        {/* station labels */}
        {[
          { x: 74, label: 'INTAKE' },
          { x: 190, label: 'COMPRESSOR' },
          { x: 344, label: 'COMBUSTOR' },
          { x: 452, label: 'TURBINE' },
        ].map((station) => (
          <text key={station.label} x={station.x} y={176} textAnchor="middle"
            fill="var(--faint)" fontSize="8" letterSpacing="1.4">
            {station.label}
          </text>
        ))}

        {/* sensor hotspots */}
        {NODES.map((node) => {
          const reading = byKey.get(node.key)
          const color = tone(reading?.z_score)
          const above = node.place === 'above'
          return (
            <g key={node.key}>
              <line x1={node.x} y1={node.y} x2={node.x}
                y2={above ? 64 : 136} stroke="var(--line-strong)" strokeDasharray="3 3" />
              <circle cx={node.x} cy={node.y} r="8" fill={color} opacity="0.14" />
              <circle cx={node.x} cy={node.y} r="3.6" fill={color}>
                <title>
                  {`${node.key.toUpperCase()} · ${labelFor(node.key)}: ${
                    reading ? `${reading.value} (${reading.z_score > 0 ? '+' : ''}${reading.z_score}σ)` : 'no sample'
                  }`}
                </title>
              </circle>
              <text x={node.x} y={above ? node.y - 14 : node.y + 16} textAnchor="middle"
                fill="var(--muted)" fontSize="8.5" letterSpacing="0.6">
                {node.key.toUpperCase()}
              </text>
              <text x={node.x} y={above ? node.y - 25 : node.y + 27} textAnchor="middle"
                fill={color} fontSize="8" className="numeric">
                {reading ? `${reading.z_score > 0 ? '+' : ''}${reading.z_score.toFixed(1)}σ` : '—'}
              </text>
            </g>
          )
        })}
      </svg>
      <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-faint">
        {[
          ['normal', 'var(--good)'],
          ['elevated', 'var(--accent)'],
          ['high', 'var(--warn)'],
          ['critical', 'var(--critical)'],
        ].map(([label, color]) => (
          <span key={label} className="inline-flex items-center gap-1.5">
            <span className="size-1.5 rounded-full" style={{ background: color }} />
            {label}
          </span>
        ))}
        <span className="ml-auto">Deviation from the asset's healthy baseline</span>
      </div>
    </div>
  )
}

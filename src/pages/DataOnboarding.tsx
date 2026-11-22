import { AlertTriangle, CheckCircle2, FileUp, PlugZap, Save, ShieldCheck, Trash2, XCircle } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import { Badge } from '../components/ui/Badge'
import { Note, PageHeader } from '../components/ui/PageHeader'
import { Panel } from '../components/ui/Panel'
import { Cell, Row, Table } from '../components/ui/Table'
import {
  applyMappingProfile,
  deleteMappingProfile,
  fetchMappingProfiles,
  fetchPlantAssets,
  importPlantCsv,
  inspectPlantCsv,
  recomputePlantHealth,
  saveMappingProfile,
  scorePlantAsset,
  validatePlantCsv,
} from '../lib/api'
import { useData } from '../lib/data-context'
import { number } from '../lib/format'
import type {
  BackendPlantAsset,
  MappingProfile,
  OnboardingInspection,
  OnboardingReport,
  SchemaDrift,
} from '../data/types'

const REQUIRED = ['asset_id', 'cycle']
const TARGETS = [
  'asset_id', 'cycle', 'op1', 'op2', 'op3',
  ...Array.from({ length: 21 }, (_, index) => `s${index + 1}`),
]

function readinessTone(readiness: string) {
  return readiness === 'ready' ? 'healthy' : readiness === 'warnings' ? 'medium' : 'critical'
}

export function DataOnboarding() {
  const { source } = useData()
  const live = source === 'live'
  const [csvText, setCsvText] = useState('')
  const [filename, setFilename] = useState('plant.csv')
  const [assetName, setAssetName] = useState('')
  const [inspection, setInspection] = useState<OnboardingInspection | null>(null)
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [report, setReport] = useState<OnboardingReport | null>(null)
  const [registry, setRegistry] = useState<BackendPlantAsset[]>([])
  const [profiles, setProfiles] = useState<MappingProfile[]>([])
  const [profileName, setProfileName] = useState('')
  const [selectedProfile, setSelectedProfile] = useState<MappingProfile | null>(null)
  const [drift, setDrift] = useState<SchemaDrift | null>(null)
  const [acceptDrift, setAcceptDrift] = useState(false)
  const [busy, setBusy] = useState<'inspect' | 'validate' | 'import' | 'profile' | number | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [scoreMessage, setScoreMessage] = useState<string | null>(null)

  const refreshRegistry = useCallback(async () => {
    if (!live) return
    try {
      setRegistry(await fetchPlantAssets())
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Registry unreachable')
    }
  }, [live])

  const refreshProfiles = useCallback(async () => {
    if (!live) return
    try {
      setProfiles(await fetchMappingProfiles())
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Profiles unreachable')
    }
  }, [live])

  useEffect(() => {
    void refreshRegistry()
    void refreshProfiles()
  }, [refreshRegistry, refreshProfiles])

  async function handleInspect() {
    setBusy('inspect')
    setError(null)
    setNotice(null)
    setReport(null)
    setDrift(null)
    setAcceptDrift(false)
    try {
      const next = await inspectPlantCsv(csvText, filename)
      setInspection(next)
      setMapping(next.suggested_mapping)
      if (!assetName) setAssetName(filename.replace(/\.[^.]+$/, ''))
    } catch (cause) {
      setInspection(null)
      setError(cause instanceof Error ? cause.message : 'Inspection failed')
    } finally {
      setBusy(null)
    }
  }

  async function handleValidate() {
    setBusy('validate')
    setError(null)
    setNotice(null)
    try {
      const next = await validatePlantCsv(csvText, mapping, filename, selectedProfile?.id)
      setReport(next)
      setDrift(next.drift ?? null)
      setAcceptDrift(false)
    } catch (cause) {
      setReport(null)
      setError(cause instanceof Error ? cause.message : 'Validation failed')
    } finally {
      setBusy(null)
    }
  }

  async function handleImport() {
    if (!assetName.trim()) {
      setError('Give the asset a name before registering it.')
      return
    }
    setBusy('import')
    setError(null)
    setNotice(null)
    try {
      const result = await importPlantCsv(
        assetName.trim(), csvText, mapping, filename,
        selectedProfile?.id, acceptDrift,
      )
      setReport(result.report)
      setDrift(result.report.drift ?? drift)
      await refreshProfiles()
      setNotice(
        `Registered ${result.assets.length} asset(s): ${result.assets
          .map((asset) => `${asset.asset_id} (${asset.status})`)
          .join(', ')}.`,
      )
      await refreshRegistry()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Import failed')
    } finally {
      setBusy(null)
    }
  }

  async function handleHealth(asset: BackendPlantAsset) {
    setBusy(asset.id)
    setError(null)
    setScoreMessage(null)
    try {
      const result = await recomputePlantHealth(asset.id)
      const health = result.health
      await refreshRegistry()
      setScoreMessage(
        health.usable
          ? `${asset.name}: health ${health.health_score}/100 (${health.category}) from `
            + `${health.coverage.sensors} sensor(s), ${health.coverage.baseline_cycles}-cycle `
            + `baseline, ${health.coverage.confidence} confidence.`
          : `${asset.name}: no usable signal yet — ${(health.reasons ?? []).join(' ')}`,
      )
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Health refresh failed')
    } finally {
      setBusy(null)
    }
  }

  async function handleScore(asset: BackendPlantAsset) {
    setBusy(asset.id)
    setError(null)
    setScoreMessage(null)
    try {
      const result = await scorePlantAsset(asset.id)
      setScoreMessage(
        `${asset.asset_id}: RUL ${result.prediction.predicted_rul} cycles ` +
          `(${result.prediction.lower}–${result.prediction.upper}) · ${result.prediction.model}. ` +
          `Out-of-distribution check against a C-MAPSS-trained model.`,
      )
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Scoring blocked')
    } finally {
      setBusy(null)
    }
  }

  async function handleSaveProfile() {
    if (!inspection) return
    if (!profileName.trim()) {
      setError('Give the mapping profile a name.')
      return
    }
    setBusy('profile')
    setError(null)
    try {
      const created = await saveMappingProfile(
        profileName.trim(), filename, mapping, inspection.columns.map((column) => column.source),
      )
      setProfileName('')
      setSelectedProfile(created)
      await refreshProfiles()
      setNotice(`Saved profile “${created.name}” for ${created.expected_columns.length} columns.`)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not save the profile')
    } finally {
      setBusy(null)
    }
  }

  async function handleApplyProfile(profile: MappingProfile) {
    if (!csvText.trim()) {
      setError('Load or paste a CSV before applying a profile.')
      return
    }
    setBusy(profile.id)
    setError(null)
    setNotice(null)
    try {
      const result = await applyMappingProfile(profile.id, csvText)
      setSelectedProfile(profile)
      setMapping(result.mapping)
      setDrift(result.drift)
      setReport(null)
      setAcceptDrift(false)
      setNotice(
        result.drift.status === 'unchanged'
          ? `Profile “${profile.name}” matches this export exactly.`
          : `Profile “${profile.name}” applied with schema drift — review it below.`,
      )
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not apply the profile')
    } finally {
      setBusy(null)
    }
  }

  async function handleDeleteProfile(profile: MappingProfile) {
    setBusy(profile.id)
    setError(null)
    try {
      await deleteMappingProfile(profile.id)
      if (selectedProfile?.id === profile.id) {
        setSelectedProfile(null)
        setDrift(null)
      }
      await refreshProfiles()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not delete the profile')
    } finally {
      setBusy(null)
    }
  }

  function updateMapping(sourceColumn: string, target: string) {
    setReport(null)
    setSelectedProfile(null)
    setDrift(null)
    setMapping((current) => {
      const next = { ...current }
      if (!target) delete next[sourceColumn]
      else next[sourceColumn] = target
      return next
    })
  }

  const mappedTargets = new Set(Object.values(mapping))
  const missingRequired = REQUIRED.filter((target) => !mappedTargets.has(target))

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Platform · Onboarding"
        title="Plant data onboarding"
        description="Map a customer CSV into the canonical telemetry schema, validate it, and register each asset with the exact mapping used — before any model sees it."
        actions={<Badge tone="neutral">schema plant-telemetry-v1</Badge>}
      />

      {!live && (
        <Note tone="warn">
          Onboarding needs the FastAPI service: mapping, validation and the registry are live
          operations and are not stored in the artifact snapshot.
        </Note>
      )}

      <div className="grid gap-4 xl:grid-cols-[1.25fr_1fr]">
        <Panel
          title="1 · Source file"
          subtitle="CSV up to 5 MB · delimiter is detected · nothing is stored yet"
          action={<Badge tone="neutral">{inspection ? `${number(inspection.rows, 0)} rows` : 'awaiting CSV'}</Badge>}
        >
          <div className="space-y-3">
            <label className={`flex cursor-pointer items-center gap-2 rounded-[7px] border border-dashed border-[var(--color-line-strong)] px-3 py-2.5 text-[11px] ${live ? 'text-muted hover:text-fg' : 'pointer-events-none opacity-50'}`}>
              <FileUp className="size-3.5" />
              Choose a CSV from a plant historian export
              <input
                type="file"
                accept=".csv,.txt,text/csv,text/plain"
                className="hidden"
                onChange={async (event) => {
                  const file = event.target.files?.[0]
                  if (!file) return
                  setFilename(file.name)
                  setCsvText(await file.text())
                  setInspection(null)
                  setReport(null)
                }}
              />
            </label>
            <textarea
              value={csvText}
              onChange={(event) => {
                setCsvText(event.target.value)
                setInspection(null)
                setReport(null)
              }}
              placeholder={'engine_id,cycle,T24,P24,Nf,…\nTAG-01,1,641.2,553.1,2388,…'}
              spellCheck={false}
              className="h-40 w-full resize-y rounded-[7px] border border-[var(--color-line)] bg-[var(--code-bg)] px-3 py-2 font-mono text-[10.5px] leading-relaxed outline-none focus:border-[var(--accent-line)]"
            />
            <div className="flex flex-wrap items-center gap-2">
              <input
                value={filename}
                onChange={(event) => setFilename(event.target.value)}
                aria-label="Source filename"
                className="w-40 rounded-[7px] border border-[var(--color-line)] bg-[var(--overlay-1)] px-2.5 py-1.5 text-[11px] outline-none"
              />
              <button
                onClick={() => void handleInspect()}
                disabled={!live || !csvText.trim() || busy === 'inspect'}
                className="inline-flex items-center gap-1.5 rounded-[7px] border border-[var(--accent-line)] bg-[var(--accent-soft)] px-3 py-1.5 text-[11px] text-[var(--color-accent)] hover:bg-[var(--accent-soft-strong)] disabled:opacity-40"
              >
                <PlugZap className="size-3.5" />
                {busy === 'inspect' ? 'Inspecting…' : 'Inspect columns'}
              </button>
              <span className="text-[10px] text-faint">rows are never written by inspection</span>
            </div>
            {error && <Note tone="warn">{error}</Note>}
          </div>
        </Panel>

        <Panel title="Canonical target" subtitle="What a model may read after onboarding">
          <div className="space-y-1.5 text-[10.5px] text-muted">
            <p><span className="text-fg">Required:</span> asset_id, cycle.</p>
            <p><span className="text-fg">Optional:</span> op1–op3, s1–s21.</p>
            <p>
              Storage accepts a partial sensor set, but the current RUL model needs all 21 channels
              and 30+ cycles. Assets that do not meet that contract are registered as
              <span className="text-fg"> not score-eligible</span>.
            </p>
            <p className="text-faint">
              Column names are auto-suggested from common aliases (Unit, Engine, T24, Nf, …); every
              suggestion can be overridden.
            </p>
          </div>
        </Panel>
      </div>

      <Panel
        title="Mapping profiles"
        subtitle="Save a vendor/source mapping and reuse it on the next export"
        action={<Badge tone="neutral">{profiles.length} saved</Badge>}
        bodyClassName="p-0"
      >
        {!live ? (
          <div className="px-4 py-3">
            <Note tone="warn">Profiles live in the metadata database and need the API.</Note>
          </div>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-2 border-b border-[var(--color-line)] px-3 py-2.5">
              <input
                value={profileName}
                onChange={(event) => setProfileName(event.target.value)}
                placeholder="Profile name (e.g. Vendor A monthly export)"
                className="min-w-[220px] flex-1 rounded-[7px] border border-[var(--color-line)] bg-[var(--overlay-1)] px-3 py-1.5 text-[11.5px] outline-none"
              />
              <button
                onClick={() => void handleSaveProfile()}
                disabled={!inspection || busy === 'profile'}
                title={inspection ? 'Save the current mapping' : 'Inspect a CSV first'}
                className="inline-flex items-center gap-1.5 rounded-[7px] border border-[var(--color-line)] px-3 py-1.5 text-[11px] text-muted hover:text-fg disabled:opacity-40"
              >
                <Save className="size-3.5" />
                {busy === 'profile' ? 'Saving…' : 'Save current mapping'}
              </button>
            </div>
            <Table head={['Profile', 'Source', 'Columns', 'Used', 'Status', '']}>
              {profiles.map((profile) => (
                <Row key={profile.id}>
                  <Cell className="text-fg">{profile.name}</Cell>
                  <Cell className="max-w-[220px] truncate text-muted">{profile.source || '—'}</Cell>
                  <Cell className="numeric text-muted">
                    {profile.expected_columns.length}
                  </Cell>
                  <Cell className="numeric text-faint">{profile.use_count}</Cell>
                  <Cell>
                    {selectedProfile?.id === profile.id
                      ? <Badge tone="attention">selected</Badge>
                      : <span className="text-[10px] text-faint">—</span>}
                  </Cell>
                  <Cell>
                    <div className="flex items-center gap-1.5">
                      <button
                        onClick={() => void handleApplyProfile(profile)}
                        disabled={!csvText.trim() || busy === profile.id}
                        className="rounded-[6px] border border-[var(--color-line)] px-2 py-1 text-[10.5px] text-muted hover:text-fg disabled:opacity-30"
                      >
                        {busy === profile.id ? 'Applying…' : 'Apply'}
                      </button>
                      <button
                        onClick={() => void handleDeleteProfile(profile)}
                        disabled={busy === profile.id}
                        title="Delete profile"
                        className="rounded-[6px] border border-[var(--color-line)] p-1.5 text-faint hover:text-[var(--color-bad)] disabled:opacity-30"
                      >
                        <Trash2 className="size-3" />
                      </button>
                    </div>
                  </Cell>
                </Row>
              ))}
              {profiles.length === 0 && (
                <Row><Cell className="text-muted">No profiles yet. Inspect a CSV, map it, then save the mapping here.</Cell></Row>
              )}
            </Table>
          </>
        )}
      </Panel>

      {drift && drift.status === 'drift' && (
        <Panel
          title="Schema drift detected"
          subtitle={drift.profile_name ? `Compared with “${drift.profile_name}”` : 'Compared with the saved profile'}
          action={<Badge tone={drift.blocking ? 'critical' : 'medium'}>{drift.blocking ? 'needs acknowledgement' : 'reported'}</Badge>}
        >
          <div className="space-y-2 text-[10.5px] leading-relaxed">
            {drift.renamed.map((rename) => (
              <div key={`${rename.from}-${rename.to}`} className="flex flex-wrap items-center gap-2">
                <Badge tone="attention">renamed</Badge>
                <span className="text-muted">{rename.from}</span>
                <span className="text-faint">→</span>
                <span className="text-fg">{rename.to}</span>
                <span className="text-faint">mapping carried to {rename.target ?? '—'} ({Math.round(rename.confidence * 100)}%)</span>
              </div>
            ))}
            {drift.added.length > 0 && (
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="neutral">added</Badge>
                <span className="text-muted">{drift.added.join(', ')}</span>
                <span className="text-faint">left unmapped unless you assign them</span>
              </div>
            )}
            {drift.missing.length > 0 && (
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="critical">missing</Badge>
                <span className="text-muted">{drift.missing.join(', ')}</span>
                <span className="text-faint">dropped fields: {drift.dropped_targets.join(', ') || '—'}</span>
              </div>
            )}
            {drift.reason && <p className="text-muted">{drift.reason}</p>}
            {drift.blocking && (
              <label className="mt-1 flex cursor-pointer items-center gap-2 text-[11px] text-muted">
                <input
                  type="checkbox"
                  checked={acceptDrift}
                  onChange={(event) => setAcceptDrift(event.target.checked)}
                  className="size-3.5 accent-[var(--color-accent)]"
                />
                Accept this schema drift for the import and refresh the profile to the new columns
              </label>
            )}
          </div>
        </Panel>
      )}

      {inspection && (
        <Panel
          title="2 · Column mapping"
          subtitle={`${inspection.columns.length} source columns · ${missingRequired.length ? `${missingRequired.length} required field(s) missing` : 'required fields mapped'}`}
          action={<Badge tone={missingRequired.length ? 'critical' : 'healthy'}>
            {Object.keys(mapping).length} mapped
          </Badge>}
          bodyClassName="p-0"
        >
          <Table head={['Source column', 'Sample', 'Target field', 'Confidence']}>
            {inspection.columns.map((column) => (
              <Row key={column.source}>
                <Cell className="text-fg">
                  {column.source}
                  <span className="ml-2 text-[9.5px] text-faint">{column.dtype}</span>
                </Cell>
                <Cell className="max-w-[260px] truncate text-muted">
                  {column.sample.map((value) => (value === null ? '—' : String(value))).join(' · ')}
                </Cell>
                <Cell>
                  <select
                    value={mapping[column.source] ?? ''}
                    onChange={(event) => updateMapping(column.source, event.target.value)}
                    className="rounded-[6px] border border-[var(--color-line)] bg-[var(--color-surface-2)] px-2 py-1 text-[11px] text-fg outline-none"
                  >
                    <option value="">ignore</option>
                    {TARGETS.map((target) => (
                      <option key={target} value={target}>
                        {target}{REQUIRED.includes(target) ? ' (required)' : ''}
                      </option>
                    ))}
                  </select>
                </Cell>
                <Cell className="numeric text-faint">
                  {column.target ? `${Math.round(column.confidence * 100)}%` : '—'}
                </Cell>
              </Row>
            ))}
          </Table>
          <div className="flex flex-wrap items-center gap-2 border-t border-[var(--color-line)] px-3 py-2.5">
            <input
              value={assetName}
              onChange={(event) => setAssetName(event.target.value)}
              placeholder="Asset name (e.g. Compressor A)"
              className="min-w-[220px] flex-1 rounded-[7px] border border-[var(--color-line)] bg-[var(--overlay-1)] px-3 py-1.5 text-[11.5px] outline-none"
            />
            <button
              onClick={() => void handleValidate()}
              disabled={busy === 'validate'}
              className="inline-flex items-center gap-1.5 rounded-[7px] border border-[var(--accent-line)] bg-[var(--accent-soft)] px-3 py-1.5 text-[11px] text-[var(--color-accent)] disabled:opacity-40"
            >
              <ShieldCheck className="size-3.5" />
              {busy === 'validate' ? 'Validating…' : 'Validate mapping'}
            </button>
          </div>
        </Panel>
      )}

      {report && (
        <Panel
          title="3 · Validation report"
          subtitle={`${report.rows} rows · ${report.asset_count} asset(s) · quality ${report.quality_score}/100`}
          action={<Badge tone={readinessTone(report.readiness) as 'healthy' | 'medium' | 'critical'}>
            {report.readiness}
          </Badge>}
          bodyClassName="p-0"
        >
          <div className="grid gap-3 border-b border-[var(--color-line)] px-3 py-2.5 md:grid-cols-2">
            <div className="flex items-start gap-2 text-[11px]">
              {report.scoring.eligible ? (
                <CheckCircle2 className="mt-0.5 size-3.5 text-[var(--color-good)]" />
              ) : (
                <AlertTriangle className="mt-0.5 size-3.5 text-[var(--color-warn)]" />
              )}
              <div>
                <p className="text-fg">
                  {report.scoring.eligible ? 'Eligible for scoring' : 'Not eligible for scoring'}
                </p>
                <p className="mt-0.5 text-[10.5px] leading-relaxed text-muted">
                  {report.scoring.mapped_sensors}/21 sensors mapped
                  {report.scoring.reasons.length > 0 && <> · {report.scoring.reasons.join(' ')}</>}
                </p>
              </div>
            </div>
            <div className="text-[10.5px] leading-relaxed text-muted">
              {report.assets.map((asset) => (
                <div key={asset.asset_id} className="flex justify-between gap-2">
                  <span className="truncate text-fg">{asset.asset_id}</span>
                  <span className="numeric">
                    {asset.rows} cycles · {asset.min_cycle}–{asset.max_cycle}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <ul className="max-h-44 divide-y divide-[var(--color-line)] overflow-y-auto">
            {report.issues.map((issue, index) => (
              <li key={`${issue.code}-${index}`} className="flex gap-2 px-3 py-1.5 text-[10.5px]">
                <span className={
                  issue.severity === 'error' ? 'text-[var(--color-critical)]'
                    : issue.severity === 'warning' ? 'text-[var(--color-warn)]' : 'text-faint'
                }>
                  {issue.severity === 'error' ? <XCircle className="size-3" />
                    : issue.severity === 'warning' ? <AlertTriangle className="size-3" />
                      : <CheckCircle2 className="size-3" />}
                </span>
                <span className="text-muted">{issue.message}</span>
                {issue.column && <span className="ml-auto shrink-0 text-faint">{issue.column}</span>}
              </li>
            ))}
          </ul>

          {report.preview.length > 0 && (
            <Table head={Object.keys(report.preview[0]).slice(0, 8)}>
              {report.preview.map((row, index) => (
                <Row key={index}>
                  {Object.keys(report.preview[0]).slice(0, 8).map((key) => (
                    <Cell key={key} className="numeric text-muted">
                      {row[key] === null ? '—' : String(row[key])}
                    </Cell>
                  ))}
                </Row>
              ))}
            </Table>
          )}

          <div className="flex flex-wrap items-center gap-2 border-t border-[var(--color-line)] px-3 py-2.5">
            <button
              onClick={() => void handleImport()}
              disabled={busy === 'import' || report.readiness === 'blocked' || Boolean(drift?.blocking && !acceptDrift)}
              className="inline-flex items-center gap-1.5 rounded-[7px] border border-[var(--color-good)]/40 bg-[var(--good-soft)] px-3 py-1.5 text-[11px] text-[var(--color-good)] disabled:opacity-40"
            >
              <PlugZap className="size-3.5" />
              {busy === 'import' ? 'Registering…' : 'Validate & register asset'}
            </button>
            <span className="text-[10px] text-faint">
              Import is refused while any blocking error remains.
            </span>
          </div>
          {notice && <div className="px-3 pb-3"><Note>{notice}</Note></div>}
        </Panel>
      )}

      <Panel
        title="Asset registry"
        subtitle="Onboarded plant assets, their per-asset mapping, and scoring readiness"
        action={<Badge tone="neutral">{registry.length} registered</Badge>}
        bodyClassName="p-0"
      >
        <Table head={['Asset', 'Canonical id', 'Status', 'Health', 'Coverage', 'Cycles', 'Sensors', 'Mapping', 'Actions']}>
          {registry.map((asset) => (
            <Row key={asset.id}>
              <Cell className="text-fg">{asset.name}</Cell>
              <Cell className="text-muted">{asset.asset_id}</Cell>
              <Cell>
                <Badge tone={asset.status === 'ready' ? 'healthy' : 'medium'}>{asset.status}</Badge>
              </Cell>
              <Cell>
                {asset.health_score != null ? (
                  <span className="inline-flex items-center gap-1.5">
                    <Badge tone={(asset.health_status ?? 'attention') as 'healthy' | 'attention' | 'warning' | 'critical'}>
                      {number(asset.health_score, 0)}
                    </Badge>
                    <span className="text-[10px] text-faint">{asset.severity}</span>
                  </span>
                ) : (
                  <span className="text-[10px] text-faint" title={(asset.health?.reasons ?? []).join(' ')}>
                    no signal
                  </span>
                )}
              </Cell>
              <Cell className="text-[10px] text-muted">
                {asset.baseline_cycles}c · {asset.health?.coverage?.confidence ?? 'none'}
              </Cell>
              <Cell className="numeric">{number(asset.cycles, 0)}</Cell>
              <Cell className="numeric">{asset.sensors.length}/21</Cell>
              <Cell className="max-w-[240px] truncate text-faint">
                {Object.entries(asset.mapping)
                  .slice(0, 3)
                  .map(([source, target]) => `${source}→${target}`)
                  .join(' · ')}
                {Object.keys(asset.mapping).length > 3 && ' …'}
              </Cell>
              <Cell>
                <div className="flex items-center gap-1.5">
                  <button
                    onClick={() => void handleHealth(asset)}
                    disabled={busy === asset.id}
                    title="Recompute baseline-relative health from the mapped sensors"
                    className="rounded-[6px] border border-[var(--color-line)] px-2 py-1 text-[10.5px] text-muted hover:text-fg disabled:opacity-30"
                  >
                    Health
                  </button>
                  <button
                    onClick={() => void handleScore(asset)}
                    disabled={busy === asset.id || !asset.score_eligible}
                    title={asset.score_eligible ? 'Run the gated RUL check' : 'Asset does not satisfy the 21-sensor model contract'}
                    className="rounded-[6px] border border-[var(--color-line)] px-2 py-1 text-[10.5px] text-muted hover:text-fg disabled:opacity-30"
                  >
                    {busy === asset.id ? '…' : 'RUL'}
                  </button>
                </div>
              </Cell>
            </Row>
          ))}
          {registry.length === 0 && (
            <Row>
              <Cell className="text-muted">
                No plant assets registered yet. Inspect a CSV above to start.
              </Cell>
            </Row>
          )}
        </Table>
        {scoreMessage && <div className="border-t border-[var(--color-line)] px-3 py-2"><Note>{scoreMessage}</Note></div>}
        <div className="border-t border-[var(--color-line)] px-3 py-2 text-[10.5px] text-faint">
          Health uses each asset's own early-cycle baseline and every mapped sensor, so partial
          exports still produce a signal: 1 sensor with 10 cycles is the minimum, 3 sensors with
          20 cycles is the recommended minimum, 6+ sensors give high confidence. RUL remains
          opt-in and still requires all 21 sensors and 30 cycles; the model is trained on C-MAPSS,
          so a plant RUL result is an out-of-distribution check, not a validated prediction.
        </div>
      </Panel>
    </div>
  )
}

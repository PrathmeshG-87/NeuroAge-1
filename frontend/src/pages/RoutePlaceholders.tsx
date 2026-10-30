import React, { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  AlertCircle,
  ArrowRight,
  Brain,
  ChartColumn,
  FileText,
  Settings2,
} from 'lucide-react'
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  LineChart,
  Line,
  AreaChart,
  Area,
} from 'recharts'
import { MRIUploader } from '@/components/mri/MRIUploader'
import { MRIViewer } from '@/components/mri/MRIViewer'
import { MedicalDisclaimer } from '@/components/assessment/MedicalDisclaimer'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { assessmentService, type AssessmentResult } from '@/services/assessment'
import {
  historyService,
  reportService,
  type AssessmentHistoryEntry,
  type ReportRecord,
  type ReportStatus,
} from '@/services/reports'

interface PlaceholderPageProps {
  title: string
  description: string
  eyebrow: string
  detail?: string
  ctaLabel?: string
  ctaTo?: string
  icon?: React.ReactNode
}

const PlaceholderPage: React.FC<PlaceholderPageProps> = ({
  title,
  description,
  eyebrow,
  detail,
  ctaLabel = 'New assessment',
  ctaTo = '/assessment',
  icon,
}) => {
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 rounded-[28px] border border-white/[0.08] bg-[#111217] p-6 sm:p-8 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#5eead4]">
            {eyebrow}
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-0.05em] text-[#ebecef] sm:text-4xl">
            {title}
          </h1>
        </div>

        <Link
          to={ctaTo}
          className="inline-flex items-center gap-2 self-start rounded-xl border border-[#5eead4]/35 bg-[#5eead4]/12 px-4 py-2.5 text-sm font-medium text-[#5eead4] transition-colors hover:border-[#5eead4]/60 hover:bg-[#5eead4]/18 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#5eead4]"
        >
          {ctaLabel}
          <ArrowRight className="h-4 w-4" />
        </Link>
      </div>

      <div className="rounded-[28px] border border-white/[0.08] bg-[#0a0b0e] p-6 sm:p-8">
        <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-2xl border border-[#5eead4]/25 bg-[#5eead4]/10 text-[#5eead4]">
          {icon ?? <Brain className="h-5 w-5" />}
        </div>

        <p className="max-w-2xl text-base leading-7 text-[#c6c9d2]">
          {description}
        </p>

        {detail && (
          <div className="mt-6 rounded-2xl border border-white/[0.08] bg-[#111217] p-4 text-sm leading-7 text-[#c6c9d2]">
            {detail}
          </div>
        )}
      </div>
    </div>
  )
}

export const AssessmentPage: React.FC = () => (
  <div className="space-y-6">
    <div className="flex flex-col gap-4 rounded-[28px] border border-white/[0.08] bg-[#111217] p-6 sm:p-8 lg:flex-row lg:items-center lg:justify-between">
      <div>
        <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#5eead4]">
          Assessment intake
        </p>
        <h1 className="mt-3 text-3xl font-semibold tracking-[-0.05em] text-[#ebecef] sm:text-4xl">
          New brain-age assessment
        </h1>
      </div>

    </div>

    <div className="max-w-5xl">
      <MRIUploader />
    </div>
  </div>
)

export const AssessmentDetailPage: React.FC = () => {
  const { id } = useParams()
  const [liveResult, setLiveResult] = useState<AssessmentResult | null>(null)
  const [resultId, setResultId] = useState<string | null>(null)
  const [loadedId, setLoadedId] = useState<string | null>(null)
  const [loading, setLoading] = useState(Boolean(id))
  const [error, setError] = useState<string | null>(null)
  const [openingReport, setOpeningReport] = useState(false)
  const [reportError, setReportError] = useState<string | null>(null)
  const currentResult = resultId === id ? liveResult : null
  const isLoadingCurrent = loading || loadedId !== id

  useEffect(() => {
    if (!id) return

    let isActive = true

    const loadResult = async () => {
      try {
        setLoading(true)
        setError(null)
        const nextResult = await assessmentService.fetchAssessmentResult(id)
        if (isActive) {
          setLiveResult(nextResult)
          setResultId(id)
        }

        if (
          nextResult.status === 'queued' ||
          nextResult.status === 'processing'
        ) {
          void (async () => {
            while (isActive) {
              await new Promise((resolve) => window.setTimeout(resolve, 2000))
              if (!isActive) return

              const status = await assessmentService.fetchAssessmentStatus(id)
              const refreshedResult =
                await assessmentService.fetchAssessmentResult(id)
              if (isActive) {
                setLiveResult(refreshedResult)
                setResultId(id)
              }

              const normalizedStatus = status.status.toLowerCase()
              if (
                [
                  'completed',
                  'success',
                  'failed',
                  'rejected',
                  'error',
                ].includes(normalizedStatus)
              ) {
                return
              }
            }
          })().catch((pollError: unknown) => {
            if (isActive) {
              setError(
                pollError instanceof Error
                  ? pollError.message
                  : 'Unable to refresh the assessment status.',
              )
            }
          })
        }
      } catch (loadError) {
        if (isActive) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : 'Unable to load the assessment result right now.',
          )
        }
      } finally {
        if (isActive) {
          setLoading(false)
          setLoadedId(id)
        }
      }
    }

    loadResult()
    return () => {
      isActive = false
    }
  }, [id])

  if (!id) {
    return (
      <div className="space-y-6">
        <div className="rounded-[28px] border border-red-500/30 bg-[#111217] p-6 sm:p-8">
          <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#fca5a5]">
            Assessment error
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-0.06em] text-[#ebecef] sm:text-4xl">
            Unable to load assessment
          </h1>
          <p className="mt-3 text-sm text-[#c6c9d2]">
            The assessment id is missing from this route.
          </p>
        </div>
      </div>
    )
  }

  if (isLoadingCurrent && !currentResult) {
    return (
      <div className="space-y-6">
        <div className="rounded-[28px] border border-white/[0.08] bg-[#111217] p-6 sm:p-8">
          <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#5eead4]">
            Assessment results
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-0.06em] text-[#ebecef] sm:text-4xl">
            Loading assessment {id ?? 'details'}…
          </h1>
        </div>
      </div>
    )
  }

  if (error && !currentResult) {
    return (
      <div className="space-y-6">
        <div className="rounded-[28px] border border-red-500/30 bg-[#111217] p-6 sm:p-8">
          <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#fca5a5]">
            Assessment error
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-0.06em] text-[#ebecef] sm:text-4xl">
            Unable to load assessment
          </h1>
          <p className="mt-3 text-sm text-[#c6c9d2]">{error}</p>
        </div>
      </div>
    )
  }

  if (!currentResult) {
    return (
      <div className="space-y-6">
        <div className="rounded-[28px] border border-white/[0.08] bg-[#111217] p-6 sm:p-8">
          <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#8d909c]">
            Assessment results
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-0.06em] text-[#ebecef] sm:text-4xl">
            No result is available for this assessment.
          </h1>
        </div>
      </div>
    )
  }

  const result = currentResult

  const comparisonData = [
    { label: 'Chronological age', value: result.chronologicalAge ?? 0 },
    { label: 'Predicted brain age', value: result.predictedBrainAge ?? 0 },
  ]
  const hasComparisonData =
    typeof result.chronologicalAge === 'number' &&
    Number.isFinite(result.chronologicalAge) &&
    typeof result.predictedBrainAge === 'number' &&
    Number.isFinite(result.predictedBrainAge)

  const formatAgeValue = (value: number | null | undefined) => {
    if (
      typeof value !== 'number' ||
      Number.isNaN(value) ||
      !Number.isFinite(value)
    ) {
      return 'Not available'
    }
    return `${value.toFixed(1)} years`
  }

  const difference =
    typeof result.chronologicalAge === 'number' &&
    typeof result.predictedBrainAge === 'number' &&
    Number.isFinite(result.chronologicalAge) &&
    Number.isFinite(result.predictedBrainAge)
      ? result.predictedBrainAge - result.chronologicalAge
      : null

  const handleViewReport = async () => {
    if (openingReport) return

    const reportWindow = window.open('', '_blank')
    if (!reportWindow) {
      setReportError('Allow pop-ups to open the report PDF in a new tab.')
      return
    }

    reportWindow.opener = null
    setOpeningReport(true)
    setReportError(null)
    try {
      const { blob } = await reportService.downloadReport(result.assessmentId)
      const reportUrl = window.URL.createObjectURL(blob)
      reportWindow.location.href = reportUrl
      reportWindow.addEventListener(
        'beforeunload',
        () => window.URL.revokeObjectURL(reportUrl),
        { once: true },
      )
    } catch (reportLoadError) {
      reportWindow.close()
      setReportError(
        reportLoadError instanceof Error
          ? reportLoadError.message
          : 'Unable to open the report PDF.',
      )
    } finally {
      setOpeningReport(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 rounded-[28px] border border-white/[0.08] bg-[#111217] p-6 sm:p-8 xl:flex-row xl:items-center xl:justify-between">
        <div>
          <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#5eead4]">
            Assessment results
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-0.06em] text-[#ebecef] sm:text-4xl">
            {result.subjectName
              ? `${result.subjectName} — Brain-age assessment`
              : `Assessment ${result.assessmentId.slice(0, 20)}`}
          </h1>
          <p className="mt-2 text-xs font-mono text-[#8d909c]">
            ID: {result.assessmentId}
          </p>
          <p className="mt-3 text-sm text-[#8d909c]">
            Processing status: {result.processingStatus}
          </p>
        </div>

        <div className="flex items-center gap-2 self-start">
          <Badge variant="teal">{result.modelName}</Badge>
          <Badge variant="neutral">{result.processingStatus}</Badge>
        </div>
      </div>

      {error ? (
        <p role="alert" className="text-sm text-[#fca5a5]">
          {error}
        </p>
      ) : null}
      {result.status === 'failed' ? (
        <p
          role="alert"
          className="rounded-xl border border-[#ef4444]/25 bg-[#ef4444]/8 p-4 text-sm text-[#fca5a5]"
        >
          {result.message || 'The model could not generate a result.'}
        </p>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <Card className="rounded-[24px] border border-white/[0.08] bg-[#111217] p-5">
          <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#8d909c]">
            Chronological age
          </p>
          <p className="mt-4 text-3xl font-semibold tracking-[-0.06em] text-[#ebecef]">
            {formatAgeValue(result.chronologicalAge)}
          </p>
        </Card>

        <Card className="rounded-[24px] border border-white/[0.08] bg-[#111217] p-5">
          <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#8d909c]">
            Predicted brain age
          </p>
          <p className="mt-4 text-3xl font-semibold tracking-[-0.06em] text-[#5eead4]">
            {formatAgeValue(result.predictedBrainAge)}
          </p>
        </Card>

        <Card className="rounded-[24px] border border-white/[0.08] bg-[#111217] p-5">
          <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#8d909c]">
            Brain age difference
          </p>
          <p className="mt-4 text-3xl font-semibold tracking-[-0.06em] text-[#fb923c]">
            {difference === null
              ? 'Not available'
              : `${difference > 0 ? '+' : ''}${difference.toFixed(1)} years`}
          </p>
        </Card>

      </div>

      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <Card className="rounded-[28px] border border-white/[0.08] bg-[#111217] p-4 sm:p-6">
          <div className="mb-5">
            <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#5eead4]">
              Interpretation
            </p>
            <h2 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-[#ebecef]">
              Brain-age comparison
            </h2>
          </div>

          {hasComparisonData ? (
            <div
              className="h-64 w-full"
              aria-label="Bar chart comparing chronological age and predicted brain age"
              role="img"
            >
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={comparisonData}
                  margin={{ top: 12, right: 16, left: 8, bottom: 16 }}
                >
                  <CartesianGrid
                    stroke="rgba(255,255,255,0.08)"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="label"
                    tick={{ fill: '#8d909c', fontSize: 12 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fill: '#8d909c', fontSize: 12 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    formatter={(value) => {
                      const numericValue = Number(value)
                      return [
                        `${Number.isFinite(numericValue) ? numericValue.toFixed(1) : '—'} years`,
                        'Age',
                      ] as [string, string]
                    }}
                    contentStyle={{
                      backgroundColor: '#171921',
                      border: '1px solid rgba(255,255,255,0.12)',
                      borderRadius: '12px',
                      color: '#ebecef',
                    }}
                  />
                  <Bar dataKey="value" radius={[8, 8, 0, 0]} fill="#5eead4" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="flex h-64 items-center justify-center rounded-2xl border border-dashed border-white/10 text-center text-sm text-[#8d909c]">
              Age comparison will be available after assessment processing.
            </div>
          )}

          <p className="mt-5 text-sm leading-7 text-[#c6c9d2]">
            The brain age difference is calculated as predicted brain age minus
            chronological age. In this example, the model estimates a difference
            of{' '}
            <span className="font-semibold text-[#fb923c]">
              {difference === null
                ? 'not available'
                : `${difference.toFixed(1)} years`}
            </span>
            , which is interpreted as a research-oriented estimate rather than a
            diagnosis.
          </p>
        </Card>

        <MRIViewer
          previewStatus={
            result.preview?.volumeEndpoint ? 'ready' : 'unavailable'
          }
          volumeEndpoint={result.preview?.volumeEndpoint}
          unavailableReason={
            result.preview?.message ??
            'No MRI volume is available for this assessment.'
          }
          title="MRI volume viewer"
        />
      </div>

      <Card className="rounded-[28px] border border-white/[0.08] bg-[#111217] p-4 sm:p-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#5eead4]">
              Assessment metadata
            </p>
            <h2 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-[#ebecef]">
              Result details
            </h2>
          </div>
          <Badge variant="neutral">Assessment ID: {result.assessmentId}</Badge>
        </div>

        <div className="mt-6 grid gap-4 md:grid-cols-2">
          <div className="rounded-[20px] border border-white/[0.08] bg-[#0a0b0e] p-4">
            <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#8d909c]">
              Model
            </p>
            <p className="mt-3 text-lg font-semibold text-[#ebecef]">
              {result.modelName}
            </p>
          </div>
          <div className="rounded-[20px] border border-white/[0.08] bg-[#0a0b0e] p-4">
            <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#8d909c]">
              Processed
            </p>
            <p className="mt-3 text-lg font-semibold text-[#ebecef]">
              {new Date(result.assessmentDate).toLocaleString()}
            </p>
          </div>
        </div>
      </Card>

      <Card className="rounded-[28px] border border-white/[0.08] bg-[#111217] p-4 sm:p-6">
        <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#5eead4]">
          Model limitations
        </p>
        <ul className="mt-4 space-y-3 text-sm leading-7 text-[#c6c9d2]">
          {result.modelLimitations.map((limit) => (
            <li key={limit} className="flex items-start gap-3">
              <span className="mt-2 h-2 w-2 rounded-full bg-[#5eead4]" />
              <span>{limit}</span>
            </li>
          ))}
        </ul>
      </Card>

      <div className="space-y-3">
        <Button
          type="button"
          onClick={() => void handleViewReport()}
          isLoading={openingReport}
          disabled={result.status !== 'completed'}
        >
          <FileText className="h-4 w-4" />
          {openingReport ? 'Opening report…' : 'View report PDF'}
        </Button>
        {reportError ? (
          <p role="alert" className="text-sm text-[#fca5a5]">
            {reportError}
          </p>
        ) : null}
      </div>

      <MedicalDisclaimer />
    </div>
  )
}

export const ReportsPage: React.FC = () => {
  const [reports, setReports] = React.useState<ReportRecord[]>([])
  const [search, setSearch] = React.useState('')
  const [statusFilter, setStatusFilter] = React.useState<'all' | ReportStatus>(
    'all',
  )
  const [loading, setLoading] = React.useState(true)
  const [loadError, setLoadError] = React.useState<string | null>(null)
  const [downloadError, setDownloadError] = React.useState<string | null>(null)
  const [downloadInFlight, setDownloadInFlight] = React.useState<string | null>(
    null,
  )

  React.useEffect(() => {
    let isActive = true

    const load = async () => {
      try {
        setLoading(true)
        setLoadError(null)
        const items = await reportService.listReports()
        if (isActive) {
          setReports(items)
        }
      } catch (loadError) {
        if (isActive) {
          setLoadError(
            loadError instanceof Error
              ? loadError.message
              : 'Unable to load reports right now.',
          )
        }
      } finally {
        if (isActive) {
          setLoading(false)
        }
      }
    }

    load()
    return () => {
      isActive = false
    }
  }, [])

  const filteredReports = reports.filter((report) => {
    const matchesStatus =
      statusFilter === 'all' || report.status === statusFilter
    const query = search.trim().toLowerCase()
    const matchesQuery =
      !query ||
      [report.assessmentId, report.title, report.summary ?? '']
        .join(' ')
        .toLowerCase()
        .includes(query)
    return matchesStatus && matchesQuery
  })

  const handleDownload = async (assessmentId: string) => {
    if (downloadInFlight) {
      return
    }

    setDownloadInFlight(assessmentId)
    setDownloadError(null)

    try {
      const result = await reportService.downloadReport(assessmentId)
      const url = window.URL.createObjectURL(result.blob)
      const link = document.createElement('a')
      link.href = url
      link.download = result.fileName
      link.rel = 'noopener'
      try {
        document.body.appendChild(link)
        link.click()
      } finally {
        link.remove()
        window.setTimeout(() => window.URL.revokeObjectURL(url), 1000)
      }
    } catch (downloadError) {
      setDownloadError(
        downloadError instanceof Error
          ? downloadError.message
          : 'Unable to download the report.',
      )
    } finally {
      setDownloadInFlight(null)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 rounded-[28px] border border-white/[0.08] bg-[#111217] p-6 sm:p-8 xl:flex-row xl:items-center xl:justify-between">
        <div>
          <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#5eead4]">
            Reports
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-0.06em] text-[#ebecef] sm:text-4xl">
            Authorized report archive
          </h1>
        </div>

        <div className="flex items-center gap-2 self-start rounded-full border border-white/10 bg-[#0a0b0e] px-3 py-1.5 text-[10px] font-mono uppercase tracking-[0.18em] text-[#8d909c]">
          <FileText className="h-3.5 w-3.5 text-[#5eead4]" />
          {reports.length} reports
        </div>
      </div>

      <div className="rounded-[28px] border border-white/[0.08] bg-[#111217] p-4 sm:p-6">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <input
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search by assessment ID or report title"
            className="w-full rounded-xl border border-white/10 bg-[#0a0b0e] px-3 py-2.5 text-sm text-[#ebecef] placeholder:text-[#6d7280] focus:border-[#5eead4]/40 focus:outline-none lg:max-w-md"
            aria-label="Search reports"
          />

          <div className="flex flex-wrap gap-2">
            {(
              [
                'all',
                'completed',
                'processing',
                'failed',
                'unavailable',
              ] as const
            ).map((filter) => (
              <button
                key={filter}
                type="button"
                onClick={() => setStatusFilter(filter)}
                className={`rounded-xl border px-3 py-2 text-xs font-medium transition-colors ${
                  statusFilter === filter
                    ? 'border-[#5eead4]/35 bg-[#5eead4]/12 text-[#5eead4]'
                    : 'border-white/10 bg-[#0a0b0e] text-[#c6c9d2]'
                }`}
              >
                {filter === 'all' ? 'All' : filter}
              </button>
            ))}
          </div>
        </div>
      </div>

      {loading ? (
        <Card className="rounded-[28px] border border-white/[0.08] bg-[#111217] p-8 text-center">
          <div className="mx-auto h-10 w-10 animate-spin rounded-full border-2 border-[#5eead4] border-t-transparent" />
          <p className="mt-4 text-sm text-[#c6c9d2]">Loading reports...</p>
        </Card>
      ) : loadError ? (
        <Card className="rounded-[28px] border border-[#ef4444]/25 bg-[#ef4444]/8 p-6 text-[#fca5a5]">
          <p className="font-medium text-[#fca5a5]">Unable to load reports</p>
          <p className="mt-2 text-sm leading-7">{loadError}</p>
        </Card>
      ) : filteredReports.length === 0 ? (
        <Card className="rounded-[28px] border border-dashed border-white/[0.1] bg-[#111217] p-8 text-center">
          <p className="text-xl font-semibold text-[#ebecef]">
            No matching reports
          </p>
          <p className="mt-2 text-sm text-[#c6c9d2]">
            No authorized reports are available for the selected filters yet.
          </p>
        </Card>
      ) : (
        <div className="space-y-4">
          {filteredReports.map((report) => (
            <Card
              key={report.id}
              className="rounded-[28px] border border-white/[0.08] bg-[#111217] p-4 sm:p-5"
            >
              <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#8d909c]">
                      Assessment {report.assessmentId}
                    </p>
                    <span
                      className={`rounded-full border px-2 py-1 text-[10px] font-mono uppercase tracking-[0.14em] ${
                        report.status === 'completed'
                          ? 'border-[#5eead4]/25 bg-[#5eead4]/10 text-[#5eead4]'
                          : report.status === 'processing'
                            ? 'border-[#60a5fa]/25 bg-[#60a5fa]/10 text-[#60a5fa]'
                            : report.status === 'failed'
                              ? 'border-[#ef4444]/25 bg-[#ef4444]/10 text-[#fca5a5]'
                              : 'border-white/10 bg-white/5 text-[#c6c9d2]'
                      }`}
                    >
                      {report.status}
                    </span>
                  </div>

                  <h2 className="mt-3 text-xl font-semibold tracking-[-0.04em] text-[#ebecef]">
                    {report.title}
                  </h2>
                  <p className="mt-2 text-sm text-[#c6c9d2]">
                    {report.summary ?? 'Report summary unavailable.'}
                  </p>
                  <p className="mt-2 text-xs font-mono text-[#8d909c]">
                    {report.generatedAt
                      ? new Date(report.generatedAt).toLocaleString()
                      : 'Not generated yet'}
                  </p>
                </div>

                <div className="flex flex-col gap-2 sm:flex-row">
                  <Link
                    to={`/assessments/${report.assessmentId}`}
                    className="inline-flex items-center justify-center rounded-xl border border-white/10 bg-[#0a0b0e] px-4 py-2.5 text-sm font-medium text-[#ebecef] transition-colors hover:border-white/20"
                  >
                    View assessment
                  </Link>

                  <button
                    type="button"
                    onClick={() => handleDownload(report.assessmentId)}
                    disabled={
                      report.status !== 'completed' ||
                      downloadInFlight !== null ||
                      downloadInFlight === report.assessmentId
                    }
                    className="inline-flex items-center justify-center gap-2 rounded-xl bg-[#5eead4] px-4 py-2.5 text-sm font-medium text-[#0a0b0e] transition-all duration-150 hover:bg-[#7feee0] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {downloadInFlight === report.assessmentId
                      ? 'Downloading...'
                      : 'Download PDF'}
                  </button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {downloadError ? (
        <Card
          role="alert"
          className="border border-[#ef4444]/25 bg-[#ef4444]/8 text-[#fca5a5]"
        >
          <p className="font-medium">Report download failed</p>
          <p className="mt-2 text-sm leading-6">{downloadError}</p>
        </Card>
      ) : null}
    </div>
  )
}

export const ProgressPage: React.FC = () => {
  const [history, setHistory] = React.useState<AssessmentHistoryEntry[]>([])
  const [loading, setLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    let active = true

    const load = async () => {
      try {
        setLoading(true)
        setError(null)
        const nextHistory = await historyService.listHistory()
        if (active) {
          setHistory(nextHistory)
        }
      } catch (loadError) {
        if (active) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : 'Unable to load historical assessments right now.',
          )
        }
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    load()
    return () => {
      active = false
    }
  }, [])

  const completedRecords = React.useMemo(
    () =>
      history
        .filter(
          (item) =>
            item.status === 'Completed' &&
            typeof item.predictedBrainAge === 'number' &&
            Number.isFinite(item.predictedBrainAge),
        )
        .sort(
          (a, b) =>
            new Date(a.assessmentDate).getTime() -
            new Date(b.assessmentDate).getTime(),
        ),
    [history],
  )

  const chartData = completedRecords.map((entry) => ({
    id: entry.assessmentId,
    date: new Date(entry.assessmentDate),
    dateLabel: new Intl.DateTimeFormat('en-US', {
      month: 'short',
      day: 'numeric',
    }).format(new Date(entry.assessmentDate)),
    assessmentId: entry.assessmentId,
    predictedBrainAge: entry.predictedBrainAge ?? null,
    brainAgeDifference: entry.brainAgeDifference ?? null,
  }))

  const latestAssessment = chartData.at(-1)
  const completedCount = completedRecords.length

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 rounded-[28px] border border-white/[0.08] bg-[#111217] p-6 sm:p-8 xl:flex-row xl:items-center xl:justify-between">
        <div>
          <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#5eead4]">
            Progress
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-[-0.06em] text-[#ebecef] sm:text-4xl">
            Assessment progress
          </h1>
        </div>

        <div className="flex items-center gap-2 self-start rounded-full border border-white/10 bg-[#0a0b0e] px-3 py-1.5 text-[10px] font-mono uppercase tracking-[0.18em] text-[#8d909c]">
          <ChartColumn className="h-3.5 w-3.5 text-[#5eead4]" />
          {completedCount} completed
        </div>
      </div>

      {loading ? (
        <Card className="rounded-[28px] border border-white/[0.08] bg-[#111217] p-8 text-center">
          <div className="mx-auto h-10 w-10 animate-spin rounded-full border-2 border-[#5eead4] border-t-transparent" />
          <p className="mt-4 text-sm text-[#c6c9d2]">
            Loading assessment history...
          </p>
        </Card>
      ) : error ? (
        <Card className="rounded-[28px] border border-[#ef4444]/25 bg-[#ef4444]/8 p-6 text-[#fca5a5]">
          <p className="font-medium text-[#fca5a5]">Unable to load progress</p>
          <p className="mt-2 text-sm leading-7">{error}</p>
        </Card>
      ) : completedCount === 0 ? (
        <Card className="rounded-[28px] border border-dashed border-white/[0.1] bg-[#111217] p-8 text-center">
          <p className="text-xl font-semibold text-[#ebecef]">
            Insufficient historical data
          </p>
          <p className="mt-2 text-sm leading-7 text-[#c6c9d2]">
            At least one completed assessment is required to visualize trends.
            This workspace does not yet have enough completed records to
            estimate longitudinal change.
          </p>
        </Card>
      ) : (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            <Card className="rounded-[24px] border border-white/[0.08] bg-[#111217] p-5">
              <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#8d909c]">
                Completed assessments
              </p>
              <p className="mt-4 text-3xl font-semibold tracking-[-0.06em] text-[#ebecef]">
                {completedCount}
              </p>
            </Card>

            <Card className="rounded-[24px] border border-white/[0.08] bg-[#111217] p-5">
              <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#8d909c]">
                Latest predicted age
              </p>
              <p className="mt-4 text-3xl font-semibold tracking-[-0.06em] text-[#5eead4]">
                {latestAssessment
                  ? `${latestAssessment.predictedBrainAge?.toFixed(1) ?? '—'} yrs`
                  : 'Not available'}
              </p>
            </Card>

            <Card className="rounded-[24px] border border-white/[0.08] bg-[#111217] p-5">
              <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#8d909c]">
                Latest difference
              </p>
              <p className="mt-4 text-3xl font-semibold tracking-[-0.06em] text-[#fb923c]">
                {latestAssessment
                  ? `${(latestAssessment.brainAgeDifference ?? 0) > 0 ? '+' : ''}${(latestAssessment.brainAgeDifference ?? 0).toFixed(1)} yrs`
                  : 'Not available'}
              </p>
            </Card>
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <Card className="rounded-[28px] border border-white/[0.08] bg-[#111217] p-4 sm:p-6">
              <div className="mb-5">
                <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#5eead4]">
                  Trend
                </p>
                <h2 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-[#ebecef]">
                  Predicted brain age over time
                </h2>
              </div>
              <div
                className="h-72 w-full"
                aria-label="Trend of predicted brain age across assessments"
                role="img"
              >
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={chartData}
                    margin={{ top: 8, right: 16, left: 0, bottom: 20 }}
                  >
                    <CartesianGrid
                      stroke="rgba(255,255,255,0.08)"
                      vertical={false}
                    />
                    <XAxis
                      dataKey="dateLabel"
                      tick={{ fill: '#8d909c', fontSize: 12 }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      tick={{ fill: '#8d909c', fontSize: 12 }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <Tooltip
                      labelFormatter={(label, payload) =>
                        payload?.[0]?.payload?.assessmentId
                          ? `${label} · ${payload[0].payload.assessmentId}`
                          : `${label}`
                      }
                      formatter={(value) => [
                        `${Number(value).toFixed(1)} years`,
                        'Predicted brain age',
                      ]}
                      contentStyle={{
                        backgroundColor: '#171921',
                        border: '1px solid rgba(255,255,255,0.12)',
                        borderRadius: '12px',
                        color: '#ebecef',
                      }}
                    />
                    <Line
                      type="monotone"
                      dataKey="predictedBrainAge"
                      name="Predicted brain age"
                      stroke="#5eead4"
                      strokeWidth={3}
                      dot={{ r: 4 }}
                      connectNulls
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </Card>

            <Card className="rounded-[28px] border border-white/[0.08] bg-[#111217] p-4 sm:p-6">
              <div className="mb-5">
                <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#5eead4]">
                  Difference
                </p>
                <h2 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-[#ebecef]">
                  Brain age difference over time
                </h2>
              </div>
              <div
                className="h-72 w-full"
                aria-label="Trend of brain age difference across assessments"
                role="img"
              >
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart
                    data={chartData}
                    margin={{ top: 8, right: 16, left: 0, bottom: 20 }}
                  >
                    <defs>
                      <linearGradient
                        id="differenceGlow"
                        x1="0"
                        x2="0"
                        y1="0"
                        y2="1"
                      >
                        <stop
                          offset="0%"
                          stopColor="#fb923c"
                          stopOpacity={0.4}
                        />
                        <stop
                          offset="100%"
                          stopColor="#fb923c"
                          stopOpacity={0.05}
                        />
                      </linearGradient>
                    </defs>
                    <CartesianGrid
                      stroke="rgba(255,255,255,0.08)"
                      vertical={false}
                    />
                    <XAxis
                      dataKey="dateLabel"
                      tick={{ fill: '#8d909c', fontSize: 12 }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      tick={{ fill: '#8d909c', fontSize: 12 }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <Tooltip
                      labelFormatter={(label, payload) =>
                        payload?.[0]?.payload?.assessmentId
                          ? `${label} · ${payload[0].payload.assessmentId}`
                          : `${label}`
                      }
                      formatter={(value) => [
                        `${Number(value).toFixed(1)} years`,
                        'Brain age difference',
                      ]}
                      contentStyle={{
                        backgroundColor: '#171921',
                        border: '1px solid rgba(255,255,255,0.12)',
                        borderRadius: '12px',
                        color: '#ebecef',
                      }}
                    />
                    <Area
                      type="monotone"
                      dataKey="brainAgeDifference"
                      name="Brain age difference"
                      stroke="#fb923c"
                      fill="url(#differenceGlow)"
                      strokeWidth={3}
                      connectNulls
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </div>

          <Card className="rounded-[28px] border border-white/[0.08] bg-[#111217] p-4 sm:p-6">
            <div className="mb-4">
              <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#5eead4]">
                Assessment log
              </p>
              <h2 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-[#ebecef]">
                Available records
              </h2>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs font-mono">
                <thead className="border-b border-white/[0.08] bg-[#171921] text-[#8d909c] uppercase tracking-wider">
                  <tr>
                    <th className="px-3 py-3">Date</th>
                    <th className="px-3 py-3">Assessment ID</th>
                    <th className="px-3 py-3">Predicted age</th>
                    <th className="px-3 py-3">Difference</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.06]">
                  {chartData.map((entry) => (
                    <tr
                      key={entry.id}
                      className="hover:bg-white/[0.02] transition-colors"
                    >
                      <td className="px-3 py-3 text-[#8d909c]">
                        {entry.dateLabel}
                      </td>
                      <td className="px-3 py-3 text-[#ebecef]">
                        {entry.assessmentId}
                      </td>
                      <td className="px-3 py-3 text-[#5eead4]">
                        {entry.predictedBrainAge === null
                          ? 'Not yet evaluated'
                          : `${entry.predictedBrainAge.toFixed(1)} yrs`}
                      </td>
                      <td className="px-3 py-3 text-[#fb923c]">
                        {entry.brainAgeDifference === null
                          ? 'Not yet evaluated'
                          : `${entry.brainAgeDifference > 0 ? '+' : ''}${entry.brainAgeDifference.toFixed(1)} yrs`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <div className="rounded-[28px] border border-[#fb923c]/25 bg-[#fb923c]/8 p-5 text-sm leading-7 text-[#fcd7b0]">
            <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#fb923c]">
              Interpretation note
            </p>
            <p className="mt-3">
              Changes between predictions may reflect measurement error, model
              variability, or differences in acquisition, preprocessing, or scan
              quality. A change in predicted brain age should not be interpreted
              as proof that the brain has biologically aged faster or slower.
            </p>
          </div>
        </>
      )}

      <MedicalDisclaimer />
    </div>
  )
}

export const MethodologyPage: React.FC = () => (
  <div className="space-y-6">
    <div className="flex flex-col gap-4 rounded-[28px] border border-white/[0.08] bg-[#111217] p-6 sm:p-8 xl:flex-row xl:items-center xl:justify-between">
      <div>
        <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#5eead4]">
          Methodology
        </p>
        <h1 className="mt-3 text-3xl font-semibold tracking-[-0.06em] text-[#ebecef] sm:text-4xl">
          Scientific methodology
        </h1>
      </div>

      <div className="flex items-center gap-2 self-start rounded-full border border-white/10 bg-[#0a0b0e] px-3 py-1.5 text-[10px] font-mono uppercase tracking-[0.18em] text-[#8d909c]">
        <Brain className="h-3.5 w-3.5 text-[#5eead4]" />
        Research only
      </div>
    </div>

    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Card className="rounded-[24px] border border-white/[0.08] bg-[#111217] p-5">
        <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#8d909c]">
          MAE
        </p>
        <p className="mt-4 text-3xl font-semibold tracking-[-0.06em] text-[#5eead4]">
          4.18
        </p>
        <p className="mt-2 text-sm text-[#c6c9d2]">years on the test set</p>
      </Card>
      <Card className="rounded-[24px] border border-white/[0.08] bg-[#111217] p-5">
        <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#8d909c]">
          RMSE
        </p>
        <p className="mt-4 text-3xl font-semibold tracking-[-0.06em] text-[#5eead4]">
          5.32
        </p>
        <p className="mt-2 text-sm text-[#c6c9d2]">years, residual spread</p>
      </Card>
      <Card className="rounded-[24px] border border-white/[0.08] bg-[#111217] p-5">
        <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#8d909c]">
          Pearson r
        </p>
        <p className="mt-4 text-3xl font-semibold tracking-[-0.06em] text-[#5eead4]">
          0.91
        </p>
        <p className="mt-2 text-sm text-[#c6c9d2]">
          chronological vs predicted age
        </p>
      </Card>
      <Card className="rounded-[24px] border border-white/[0.08] bg-[#111217] p-5">
        <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#8d909c]">
          Test set
        </p>
        <p className="mt-4 text-3xl font-semibold tracking-[-0.06em] text-[#ebecef]">
          184
        </p>
        <p className="mt-2 text-sm text-[#c6c9d2]">subjects evaluated</p>
      </Card>
    </div>

    <div className="grid gap-6 xl:grid-cols-2">
      <Card className="rounded-[28px] border border-white/[0.08] bg-[#111217] p-5 sm:p-6">
        <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#5eead4]">
          Pipeline
        </p>
        <h2 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-[#ebecef]">
          MRI preprocessing
        </h2>
        <ul className="mt-5 space-y-3 text-sm leading-7 text-[#c6c9d2]">
          <li>
            <span className="text-[#5eead4]">•</span> Structural MRI inputs are
            validated and checked for compatible file type, voxel dimensions,
            and scan metadata.
          </li>
          <li>
            <span className="text-[#5eead4]">•</span> A standard preprocessing
            workflow includes reorientation, bias-field correction, tissue
            segmentation, and spatial normalization to a common anatomical
            frame.
          </li>
          <li>
            <span className="text-[#5eead4]">•</span> Only quality-controlled
            and anatomically consistent images proceed to model inference.
          </li>
        </ul>
      </Card>

      <Card className="rounded-[28px] border border-white/[0.08] bg-[#111217] p-5 sm:p-6">
        <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#5eead4]">
          Model
        </p>
        <h2 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-[#ebecef]">
          Brain-age regression
        </h2>
        <p className="mt-5 text-sm leading-7 text-[#c6c9d2]">
          The model learns a mapping from MRI-derived structural features to
          chronological age using a subject-level train/validation/test split
          designed to reduce leakage between individuals. The output is a
          predicted brain age, not a direct biological readout of aging speed.
        </p>
      </Card>
    </div>

    <div className="grid gap-6 xl:grid-cols-2">
      <Card className="rounded-[28px] border border-white/[0.08] bg-[#111217] p-5 sm:p-6">
        <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#5eead4]">
          Age interpretation
        </p>
        <h2 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-[#ebecef]">
          Chronological age vs predicted brain age
        </h2>
        <p className="mt-5 text-sm leading-7 text-[#c6c9d2]">
          Chronological age is the actual calendar age at scan time. Predicted
          brain age is the model’s estimate derived from MRI patterns. The
          difference, sometimes called Brain-PAD, is calculated as predicted
          brain age minus chronological age. A positive value suggests the MRI
          pattern looks older than the person’s chronological age, while a
          negative value suggests the opposite; neither should be treated as a
          diagnosis.
        </p>
      </Card>

      <Card className="rounded-[28px] border border-white/[0.08] bg-[#111217] p-5 sm:p-6">
        <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#5eead4]">
          Uncertainty
        </p>
        <h2 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-[#ebecef]">
          Prediction uncertainty and model support
        </h2>
        <p className="mt-5 text-sm leading-7 text-[#c6c9d2]">
          Prediction uncertainty is not yet evaluated or surfaced in this build.
          In a more complete deployment, uncertainty would be reported as
          confidence intervals or predictive intervals, ideally together with
          quality-control flags, acquisition metadata, and calibration checks.
          At present, this project marks such values as not yet evaluated rather
          than inventing a number.
        </p>
      </Card>
    </div>

    <div className="grid gap-6 xl:grid-cols-2">
      <Card className="rounded-[28px] border border-white/[0.08] bg-[#111217] p-5 sm:p-6">
        <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#5eead4]">
          Dataset limits
        </p>
        <h2 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-[#ebecef]">
          Limitations and bias
        </h2>
        <ul className="mt-5 space-y-3 text-sm leading-7 text-[#c6c9d2]">
          <li>
            <span className="text-[#5eead4]">•</span> The currently documented
            evaluation uses public datasets including IXI and OASIS-1/OASIS-3,
            with adult cohorts and a 3T Philips setting for IXI.
          </li>
          <li>
            <span className="text-[#5eead4]">•</span> Population composition,
            scanner manufacturer, field strength, and acquisition protocol can
            influence the regression output.
          </li>
          <li>
            <span className="text-[#5eead4]">•</span> These limitations mean the
            model should be interpreted cautiously across demographics, imaging
            devices, and clinical contexts.
          </li>
        </ul>
      </Card>

      <Card className="rounded-[28px] border border-white/[0.08] bg-[#111217] p-5 sm:p-6">
        <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#5eead4]">
          Interpretation
        </p>
        <h2 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-[#ebecef]">
          Explainability vs causality
        </h2>
        <p className="mt-5 text-sm leading-7 text-[#c6c9d2]">
          Model explainability can help identify which anatomical patterns
          correlate with age-related structure, but explainability does not
          establish a causal mechanism. A highlighted region does not prove that
          the model has identified the direct biological cause of accelerated or
          delayed aging in an individual. These outputs remain probabilistic,
          contextual, and research-oriented.
        </p>
      </Card>
    </div>

    <Card className="rounded-[28px] border border-white/[0.08] bg-[#111217] p-5 sm:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#5eead4]">
            Validation summary
          </p>
          <h2 className="mt-2 text-xl font-semibold tracking-[-0.04em] text-[#ebecef]">
            Documented performance in project materials
          </h2>
        </div>
        <Badge variant="neutral">Subject-level split</Badge>
      </div>

      <p className="mt-5 text-sm leading-7 text-[#c6c9d2]">
        The current project documentation reports a test-set MAE of 4.18 years,
        RMSE of 5.32 years, and Pearson correlation of 0.91 between
        chronological age and predicted age for 184 subjects. Age-bias
        correction was fitted on the training set only and the project notes
        that regression-to-the-mean is a known challenge in brain-age models.
        These figures are informative but should be interpreted as a research
        benchmark, not a clinical performance claim.
      </p>
    </Card>

    <MedicalDisclaimer />
  </div>
)

export const SettingsPage: React.FC = () => (
  <PlaceholderPage
    eyebrow="Settings"
    title="Application settings"
    description="Use this area for workspace preferences, display settings, and future research profile configuration. No authentication or session logic is assumed in this phase."
    detail="Demo account controls and settings are presented as placeholders only."
    icon={<Settings2 className="h-5 w-5" />}
  />
)

export const NotFoundPage: React.FC = () => (
  <div className="flex min-h-screen items-center justify-center bg-[#0a0b0e] px-4 text-[#ebecef]">
    <div className="w-full max-w-xl rounded-[28px] border border-white/[0.08] bg-[#111217] p-8 text-center">
      <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl border border-[#fb923c]/25 bg-[#fb923c]/10 text-[#fb923c]">
        <AlertCircle className="h-6 w-6" />
      </div>
      <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#5eead4]">
        Not found
      </p>
      <h1 className="mt-4 text-3xl font-semibold tracking-[-0.05em] text-[#ebecef]">
        This page does not exist.
      </h1>
      <p className="mt-4 text-base leading-7 text-[#c6c9d2]">
        The requested route is unavailable. Use an assessment or the navigation
        to continue.
      </p>
      <div className="mt-6 flex justify-center">
        <Link
          to="/assessment"
          className="inline-flex items-center gap-2 rounded-xl bg-[#5eead4] px-4 py-2.5 text-sm font-medium text-[#0a0b0e] transition-transform duration-200 hover:-translate-y-0.5 hover:bg-[#7feee0] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#5eead4]"
        >
          Start an assessment
          <ArrowRight className="h-4 w-4" />
        </Link>
      </div>
    </div>
  </div>
)

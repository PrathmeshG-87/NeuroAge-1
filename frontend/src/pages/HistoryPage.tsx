import React from 'react'
import { Link } from 'react-router-dom'
import { Calendar, ExternalLink, Gauge, RefreshCw } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { MedicalDisclaimer } from '@/components/assessment/MedicalDisclaimer'
import { historyService, type AssessmentHistoryEntry } from '@/services/reports'

const statusTone: Record<
  AssessmentHistoryEntry['status'],
  'teal' | 'neutral' | 'coral'
> = {
  Queued: 'neutral',
  Completed: 'teal',
  Processing: 'neutral',
  Failed: 'coral',
  Unavailable: 'neutral',
}

export const HistoryPage: React.FC = () => {
  const [records, setRecords] = React.useState<AssessmentHistoryEntry[]>([])
  const [isLoading, setIsLoading] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    let isMounted = true

    const load = async () => {
      try {
        setIsLoading(true)
        setError(null)
        const history = await historyService.listHistory()
        if (isMounted) {
          setRecords(history)
        }
      } catch (loadError) {
        if (isMounted) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : 'Unable to load assessment history right now.',
          )
        }
      } finally {
        if (isMounted) {
          setIsLoading(false)
        }
      }
    }

    load()
    return () => {
      isMounted = false
    }
  }, [])

  const formatAge = (value: number | null) => {
    if (
      typeof value !== 'number' ||
      Number.isNaN(value) ||
      !Number.isFinite(value)
    ) {
      return '—'
    }
    return `${value.toFixed(1)} yrs`
  }

  const formatDifference = (value: number | null) => {
    if (
      typeof value !== 'number' ||
      Number.isNaN(value) ||
      !Number.isFinite(value)
    ) {
      return '—'
    }
    return `${value > 0 ? '+' : ''}${value.toFixed(1)} yrs`
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-[#ebecef]">
            Assessment history & records
          </h2>
          <p className="text-xs text-[#8d909c] font-mono mt-0.5">
            Prior assessments with accessible status, summaries, and report
            availability.
          </p>
        </div>
        <Badge variant="neutral">Records: {records.length}</Badge>
      </div>

      {isLoading ? (
        <Card className="rounded-[28px] border border-white/[0.08] bg-[#111217] p-8 text-center">
          <div className="mx-auto h-10 w-10 animate-spin rounded-full border-2 border-[#5eead4] border-t-transparent" />
          <p className="mt-4 text-sm text-[#c6c9d2]">
            Loading assessment history...
          </p>
        </Card>
      ) : error ? (
        <Card className="rounded-[28px] border border-[#ef4444]/25 bg-[#ef4444]/8 p-6 text-[#fca5a5]">
          <div className="flex items-start gap-3">
            <RefreshCw className="mt-0.5 h-4 w-4" />
            <div>
              <p className="font-medium text-[#fca5a5]">History unavailable</p>
              <p className="mt-2 text-sm leading-7">{error}</p>
            </div>
          </div>
        </Card>
      ) : records.length === 0 ? (
        <Card className="rounded-[28px] border border-dashed border-white/[0.1] bg-[#111217] p-8 text-center">
          <p className="text-xl font-semibold text-[#ebecef]">
            No assessment history
          </p>
          <p className="mt-2 text-sm text-[#c6c9d2]">
            Once assessments are processed, they will appear here with status
            and estimated age results.
          </p>
        </Card>
      ) : (
        <Card className="overflow-hidden p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead className="border-b border-white/[0.08] bg-[#171921] text-[#8d909c] uppercase tracking-wider">
                <tr>
                  <th className="px-4 py-3">Assessment</th>
                  <th className="px-4 py-3">Subject</th>
                  <th className="px-4 py-3">Date</th>
                  <th className="px-4 py-3">Predicted age</th>
                  <th className="px-4 py-3">Brain age diff</th>
                  <th className="px-4 py-3">Status</th>
                  <th className="px-4 py-3 text-right">Open</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.06]">
                {records.map((record) => (
                  <tr
                    key={record.assessmentId}
                    className="hover:bg-white/[0.02] transition-colors"
                  >
                    <td className="px-4 py-3.5 font-semibold text-[#ebecef]">
                      <div>{record.subjectName || record.assessmentId}</div>
                      {record.subjectName ? (
                        <div className="mt-1 text-[10px] font-normal text-[#8d909c]">
                          {record.assessmentId}
                        </div>
                      ) : null}
                    </td>
                    <td className="px-4 py-3.5 text-[#c6c9d2]">
                      {record.subjectId ?? 'Not available'}
                    </td>
                    <td className="px-4 py-3.5 text-[#8d909c]">
                      <span className="inline-flex items-center gap-1.5">
                        <Calendar className="h-3.5 w-3.5" />
                        {new Date(record.assessmentDate).toLocaleString()}
                      </span>
                    </td>
                    <td className="px-4 py-3.5 text-[#5eead4] font-semibold">
                      {formatAge(record.predictedBrainAge)}
                    </td>
                    <td className="px-4 py-3.5 text-[#fb923c]">
                      {formatDifference(record.brainAgeDifference)}
                    </td>
                    <td className="px-4 py-3.5">
                      <Badge variant={statusTone[record.status]}>
                        {record.status}
                      </Badge>
                    </td>
                    <td className="px-4 py-3.5 text-right">
                      <Link
                        to={`/assessments/${record.assessmentId}`}
                        className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-[#0a0b0e] px-2.5 py-1.5 text-[#5eead4] transition-colors hover:border-white/20"
                      >
                        <ExternalLink className="h-3.5 w-3.5" />
                        Open
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <div className="rounded-[28px] border border-white/[0.08] bg-[#111217] p-4 sm:p-5">
        <div className="flex items-start gap-3">
          <Gauge className="mt-0.5 h-4 w-4 text-[#5eead4]" />
          <div>
            <p className="text-sm font-medium text-[#ebecef]">
              History guidance
            </p>
            <p className="mt-1 text-sm leading-7 text-[#c6c9d2]">
              Completed records show predictions when available. Failed or
              unavailable assessments are clearly labeled and are not treated as
              valid results or actionable diagnoses.
            </p>
          </div>
        </div>
      </div>

      <MedicalDisclaimer />
    </div>
  )
}

import React from 'react'
import { Link } from 'react-router-dom'
import { AlertTriangle, Upload } from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { MRIViewer } from '@/components/mri/MRIViewer'
import { MedicalDisclaimer } from '@/components/assessment/MedicalDisclaimer'
import { assessmentService, type AssessmentResult } from '@/services/assessment'

export const ViewerPage: React.FC = () => {
  const activeRequest = React.useRef(0)
  const [file, setFile] = React.useState<File | null>(null)
  const [subjectName, setSubjectName] = React.useState('')
  const [result, setResult] = React.useState<AssessmentResult | null>(null)
  const [isLoading, setIsLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(
    () => () => {
      activeRequest.current += 1
    },
    [],
  )

  const loadVolume = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!file || isLoading) {
      return
    }

    setIsLoading(true)
    setError(null)
    setResult(null)
    const requestId = activeRequest.current + 1
    activeRequest.current = requestId
    try {
      const normalizedSubjectName = subjectName.trim()
      if (!normalizedSubjectName) {
        throw new Error('Enter a name for this assessment.')
      }
      const submission = await assessmentService.createAssessment({
        file,
        subjectName: normalizedSubjectName,
      })
      const assessment = await assessmentService.fetchAssessmentResult(
        submission.assessmentId,
      )
      if (activeRequest.current !== requestId) return
      if (!assessment.preview?.volumeEndpoint) {
        throw new Error(
          assessment.preview?.message ??
            'The backend did not provide the authorized MRI volume for this upload.',
        )
      }
      setResult(assessment)
      setIsLoading(false)

      if (
        assessment.status === 'queued' ||
        assessment.status === 'processing'
      ) {
        void assessmentService
          .waitForCompletion(submission.assessmentId, {
            intervalMs: 2000,
            maxAttempts: 60,
          })
          .then((completedAssessment) => {
            if (activeRequest.current === requestId) {
              setResult(completedAssessment)
            }
          })
          .catch((processingError: unknown) => {
            if (activeRequest.current === requestId) {
              setError(
                processingError instanceof Error
                  ? processingError.message
                  : 'The MRI assessment could not be completed.',
              )
            }
          })
      }
    } catch (loadError) {
      if (activeRequest.current === requestId) {
        setError(
          loadError instanceof Error
            ? loadError.message
            : 'Unable to load the MRI volume.',
        )
      }
    } finally {
      if (activeRequest.current === requestId) setIsLoading(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold tracking-tight text-[#ebecef]">
          Interactive NIfTI volume viewer
        </h2>
        <p className="mt-0.5 text-xs font-mono text-[#8d909c]">
          Inspect the actual NIfTI volume in synchronized anatomical views.
        </p>
      </div>

      <Card>
        <form
          onSubmit={loadVolume}
          className="flex flex-col gap-4 sm:flex-row sm:items-end"
        >
          <label className="flex-1 space-y-2 text-sm text-[#c6c9d2]">
            <span>Subject name</span>
            <input
              type="text"
              maxLength={120}
              required
              value={subjectName}
              onChange={(event) => setSubjectName(event.target.value)}
              placeholder="Enter a short name for this assessment"
              className="block w-full rounded-xl border border-white/10 bg-[#0a0b0e] p-2.5 text-sm text-[#c6c9d2] placeholder:text-[#6d7280]"
            />
          </label>
          <label className="flex-1 space-y-2 text-sm text-[#c6c9d2]">
            <span>MRI volume (.nii or .nii.gz)</span>
            <input
              type="file"
              accept=".nii,.nii.gz"
              onChange={(event) => {
                setFile(event.target.files?.[0] ?? null)
                setError(null)
              }}
              className="block w-full rounded-xl border border-white/10 bg-[#0a0b0e] p-2.5 text-sm text-[#c6c9d2] file:mr-3 file:rounded-lg file:border-0 file:bg-white/10 file:px-3 file:py-1.5 file:text-sm file:text-[#ebecef]"
            />
          </label>
          <button
            type="submit"
            disabled={!file || isLoading}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-[#5eead4] px-4 py-2.5 text-sm font-medium text-[#0a0b0e] transition-colors hover:bg-[#7feee0] disabled:cursor-not-allowed disabled:opacity-60"
          >
            <Upload className="h-4 w-4" />
            {isLoading ? 'Preparing volume...' : 'Upload and view slices'}
          </button>
        </form>
        <p className="mt-3 text-xs leading-5 text-[#8d909c]">
          The file is uploaded to the backend and an assessment record is
          created. MRI visualization is for research use only.
        </p>
      </Card>

      {error ? (
        <Card className="border border-[#ef4444]/25 bg-[#ef4444]/8 text-[#fca5a5]">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <p role="alert" className="text-sm leading-6">
              {error}
            </p>
          </div>
        </Card>
      ) : null}

      {isLoading ? (
        <Card className="text-center text-sm text-[#c6c9d2]">
          Validating and preparing your MRI volume...
        </Card>
      ) : result ? (
        <>
          <Card className="flex flex-col gap-3 text-sm text-[#c6c9d2] sm:flex-row sm:items-center sm:justify-between">
            <span>
              {result.subjectName || 'Brain-age assessment'}:{' '}
              {result.processingStatus}
              {result.predictedBrainAge !== null
                ? ` · ${result.predictedBrainAge.toFixed(1)} years`
                : ''}
            </span>
            <Link
              to={`/assessments/${result.assessmentId}`}
              className="inline-flex items-center gap-2 font-medium text-[#5eead4] hover:text-[#7feee0]"
            >
              View assessment result
            </Link>
          </Card>
          {result.preview?.volumeEndpoint ? (
            <MRIViewer
              previewStatus="ready"
              volumeEndpoint={result.preview.volumeEndpoint}
              title={`MRI volume ${result.subjectName || result.assessmentId}`}
            />
          ) : null}
        </>
      ) : (
        <Card className="text-sm leading-6 text-[#8d909c]">
          Choose a NIfTI scan above to load the interactive volume viewer.
        </Card>
      )}

      <MedicalDisclaimer />
    </div>
  )
}

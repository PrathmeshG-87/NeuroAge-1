import React, { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  Info,
  RefreshCw,
  ShieldCheck,
  UploadCloud,
  X,
} from 'lucide-react'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import {
  ASSESSMENT_BACKEND_CONTRACT,
  type AssessmentSubmissionRequest,
  type AssessmentWorkflowState,
  assessmentService,
} from '@/services/assessment'

const SUPPORTED_EXTENSIONS = ['.nii', '.nii.gz']
const MAX_FILE_SIZE_BYTES = ASSESSMENT_BACKEND_CONTRACT.maxFileSizeBytes

const formatBytes = (bytes: number) => {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const index = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  )
  const size = bytes / 1024 ** index
  return `${size.toFixed(size >= 10 || index === 0 ? 0 : 1)} ${units[index]}`
}

const getValidationError = (file: File) => {
  const lowerName = file.name.toLowerCase()
  if (
    !SUPPORTED_EXTENSIONS.some((extension) => lowerName.endsWith(extension))
  ) {
    return `Unsupported format: ${file.name}. Only ${SUPPORTED_EXTENSIONS.join(', ')} are currently accepted.`
  }
  if (file.size <= 0) {
    return 'The selected MRI file is empty. Please choose a non-empty volume.'
  }
  if (file.size > MAX_FILE_SIZE_BYTES) {
    return `The selected MRI file exceeds the supported size limit of ${formatBytes(MAX_FILE_SIZE_BYTES)}.`
  }
  return null
}

export const MRIUploader: React.FC = () => {
  const inputRef = useRef<HTMLInputElement | null>(null)
  const navigate = useNavigate()

  const [dragActive, setDragActive] = useState(false)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [subjectName, setSubjectName] = useState('')
  const [chronologicalAge, setChronologicalAge] = useState('')
  const [status, setStatus] = useState<AssessmentWorkflowState>('idle')
  const [error, setError] = useState<string | null>(null)
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    return () => {
      setSelectedFile(null)
      setSubjectName('')
      setChronologicalAge('')
      setProgress(0)
      setError(null)
    }
  }, [])

  const resetSelection = () => {
    setSelectedFile(null)
    setSubjectName('')
    setChronologicalAge('')
    setStatus('idle')
    setProgress(0)
    setError(null)
    if (inputRef.current) {
      inputRef.current.value = ''
    }
  }

  const handleFileSelection = (file: File | null) => {
    if (!file) {
      resetSelection()
      return
    }

    const validationError = getValidationError(file)
    if (validationError) {
      setSelectedFile(null)
      setStatus('failure')
      setError(validationError)
      setProgress(0)
      return
    }

    setSelectedFile(file)
    setStatus('selected')
    setError(null)
    setProgress(0)
  }

  const handleSubmit = async () => {
    const normalizedSubjectName = subjectName.trim()
    if (!normalizedSubjectName) {
      setStatus('failure')
      setError('Enter a name for this assessment.')
      return
    }

    if (!selectedFile) {
      setStatus('failure')
      setError('Choose an MRI file to start the assessment.')
      return
    }

    if (
      status === 'validating' ||
      status === 'uploading' ||
      status === 'processing'
    ) {
      return
    }

    const ageText = chronologicalAge.trim()
    if (ageText !== '') {
      const ageValue = Number(ageText)
      if (Number.isNaN(ageValue) || ageValue < 0 || ageValue > 120) {
        setStatus('failure')
        setError(
          'Chronological age must be a valid number between 0 and 120 years.',
        )
        return
      }
    }

    setError(null)
    setStatus('validating')
    setProgress(5)

    try {
      await new Promise((resolve) => window.setTimeout(resolve, 450))
      setStatus('uploading')
      setProgress(15)

      const request: AssessmentSubmissionRequest = {
        file: selectedFile,
        subjectName: normalizedSubjectName,
        chronologicalAge: ageText === '' ? undefined : Number(ageText),
      }

      const createdAssessment = await assessmentService.createAssessment(
        request,
        ({ phase, progress: nextProgress }) => {
          setStatus(phase === 'uploading' ? 'uploading' : 'processing')
          setProgress(nextProgress)
        },
      )

      setStatus('success')
      setProgress(100)
      navigate(`/assessments/${createdAssessment.assessmentId}`)
    } catch (submitError) {
      const message =
        submitError instanceof Error
          ? submitError.message
          : 'Assessment submission failed. Please review the file and try again.'

      setStatus('failure')
      setError(message)
      setProgress(0)
    }
  }

  const canSubmit =
    Boolean(selectedFile) &&
    !['validating', 'uploading', 'processing'].includes(status)

  return (
    <Card className="space-y-5 rounded-[28px] border border-white/[0.08] bg-[#111217] p-5 sm:p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-[11px] font-mono uppercase tracking-[0.2em] text-[#5eead4]">
            Assessment initiation
          </p>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.05em] text-[#ebecef]">
            MRI assessment intake
          </h2>
        </div>
        <div className="flex items-center gap-2 rounded-full border border-white/10 bg-[#0a0b0e] px-3 py-1.5 text-[10px] font-mono uppercase tracking-[0.18em] text-[#8d909c]">
          <ShieldCheck className="h-3.5 w-3.5 text-[#5eead4]" />
          {SUPPORTED_EXTENSIONS.join(', ')} only
        </div>
      </div>

      <div
        onDragEnter={(event) => {
          event.preventDefault()
          setDragActive(true)
        }}
        onDragOver={(event) => {
          event.preventDefault()
          setDragActive(true)
        }}
        onDragLeave={(event) => {
          event.preventDefault()
          setDragActive(false)
        }}
        onDrop={(event) => {
          event.preventDefault()
          setDragActive(false)
          const file = event.dataTransfer.files?.[0] ?? null
          handleFileSelection(file)
        }}
        className={`cursor-pointer rounded-[24px] border-2 border-dashed p-6 text-center transition-all duration-200 ${
          dragActive
            ? 'border-[#5eead4] bg-[#5eead4]/6'
            : 'border-white/10 bg-[#0a0b0e] hover:border-white/20'
        }`}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".nii,.nii.gz"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0] ?? null
            handleFileSelection(file)
          }}
        />

        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full border border-[#5eead4]/25 bg-[#5eead4]/10 text-[#5eead4]">
          <UploadCloud className="h-6 w-6" />
        </div>

        <p className="mt-4 text-base font-medium text-[#ebecef]">
          Drag & drop an MRI volume here or{' '}
          <span className="text-[#5eead4] underline decoration-[#5eead4]/50 underline-offset-4">
            browse files
          </span>
        </p>
        <p className="mt-2 text-sm text-[#8d909c]">
          Maximum size: {formatBytes(MAX_FILE_SIZE_BYTES)}. Approved formats:{' '}
          {SUPPORTED_EXTENSIONS.join(', ')}.
        </p>
      </div>

      {selectedFile ? (
        <div className="rounded-[22px] border border-white/[0.08] bg-[#0a0b0e] p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl border border-[#5eead4]/25 bg-[#5eead4]/10 text-[#5eead4]">
                <FileText className="h-5 w-5" />
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-[#ebecef]">
                  {selectedFile.name}
                </p>
                <p className="text-xs text-[#8d909c]">
                  {formatBytes(selectedFile.size)}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => inputRef.current?.click()}
                className="rounded-lg border border-white/10 bg-[#111217] px-3 py-2 text-xs font-medium text-[#c6c9d2] transition-colors hover:border-white/20 hover:text-[#ebecef]"
              >
                Replace
              </button>
              <button
                type="button"
                onClick={resetSelection}
                className="rounded-lg border border-[#ef4444]/25 bg-[#ef4444]/8 px-3 py-2 text-xs font-medium text-[#fca5a5] transition-colors hover:border-[#ef4444]/40 hover:bg-[#ef4444]/12"
              >
                Remove
              </button>
            </div>
          </div>

          {(status === 'uploading' ||
            status === 'processing' ||
            status === 'validating') && (
            <div className="mt-4 space-y-2">
              <div className="flex items-center justify-between text-[11px] font-mono uppercase tracking-[0.16em] text-[#8d909c]">
                <span>
                  {status === 'validating'
                    ? 'Validating file'
                    : status === 'uploading'
                      ? 'Uploading file'
                      : 'Processing assessment'}
                </span>
                <span>{progress}%</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-white/5">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-[#5eead4] to-[#7dd3fc] transition-all duration-300"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}
        </div>
      ) : null}

      <div className="space-y-2">
        <label
          htmlFor="subject-name"
          className="text-xs font-mono uppercase tracking-[0.16em] text-[#8d909c]"
        >
          Subject name
        </label>
        <input
          id="subject-name"
          type="text"
          maxLength={120}
          required
          value={subjectName}
          onChange={(event) => setSubjectName(event.target.value)}
          placeholder="Enter a short name for this assessment"
          className="w-full rounded-xl border border-white/10 bg-[#0a0b0e] px-3 py-3 text-sm text-[#ebecef] placeholder:text-[#6d7280] focus:border-[#5eead4]/40 focus:outline-none"
        />
      </div>

      <div className="space-y-2">
        <label
          htmlFor="chronological-age"
          className="text-xs font-mono uppercase tracking-[0.16em] text-[#8d909c]"
        >
          Chronological age (years)
        </label>
        <input
          id="chronological-age"
          type="number"
          min={0}
          max={120}
          inputMode="numeric"
          value={chronologicalAge}
          onChange={(event) => setChronologicalAge(event.target.value)}
          placeholder="Optional until backend contract confirms this field"
          className="w-full rounded-xl border border-white/10 bg-[#0a0b0e] px-3 py-3 text-sm text-[#ebecef] placeholder:text-[#6d7280] focus:border-[#5eead4]/40 focus:outline-none"
        />
      </div>

      <div className="rounded-[22px] border border-white/[0.08] bg-[#0a0b0e] p-4 text-sm leading-7 text-[#c6c9d2]">
        <div className="flex items-start gap-3">
          <Info className="mt-1 h-4 w-4 shrink-0 text-[#5eead4]" />
          <div>
            <p className="font-medium text-[#ebecef]">Privacy notice</p>
            <p className="mt-1">
              The browser does not store your MRI file. The backend stores the
                uploaded file and assessment record for processing; follow your
                deployment’s retention and deletion policy.
            </p>
          </div>
        </div>
      </div>

      <div className="rounded-[22px] border border-[#fb923c]/20 bg-[#fb923c]/8 p-4 text-sm leading-7 text-[#f6d1b2]">
        <p className="font-medium text-[#fbbf24]">Research-use only</p>
        <p className="mt-1">
          This workflow is intended for research and exploratory analysis.
          Outputs are not medical diagnoses and should not be used as a
          substitute for clinical review.
        </p>
      </div>

      {error ? (
        <div className="flex items-start gap-3 rounded-[20px] border border-[#ef4444]/30 bg-[#ef4444]/8 p-4 text-sm text-[#fca5a5]">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="font-medium text-[#fca5a5]">Action required</p>
            <p className="mt-1">{error}</p>
          </div>
        </div>
      ) : null}

      {status === 'success' ? (
        <div className="flex items-start gap-3 rounded-[20px] border border-[#5eead4]/30 bg-[#5eead4]/8 p-4 text-sm text-[#8ef0dd]">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            <p className="font-medium text-[#8ef0dd]">Assessment submitted</p>
            <p className="mt-1">
              The MRI was accepted and the assessment was queued. Results will
              appear when processing is available; the uploaded scan can be
              reviewed in the MRI viewer.
            </p>
          </div>
        </div>
      ) : null}

      <div className="flex flex-col gap-3 pt-2 sm:flex-row sm:justify-end">
        <Button
          type="button"
          variant="secondary"
          size="md"
          onClick={resetSelection}
          disabled={!selectedFile}
        >
          <X className="h-4 w-4" />
          Cancel
        </Button>

        <Button
          type="button"
          variant="primary"
          size="md"
          disabled={!canSubmit}
          isLoading={
            status === 'validating' ||
            status === 'uploading' ||
            status === 'processing'
          }
          onClick={handleSubmit}
        >
          {status === 'validating'
            ? 'Validating...'
            : status === 'uploading'
              ? 'Uploading...'
              : status === 'processing'
                ? 'Processing...'
                : 'Submit assessment'}
        </Button>
      </div>

      {status === 'failure' ? (
        <div className="flex justify-end">
          <Button
            type="button"
            variant="outline"
            size="md"
            onClick={() => {
              setStatus(selectedFile ? 'selected' : 'idle')
              setError(null)
              setProgress(0)
            }}
          >
            <RefreshCw className="h-4 w-4" />
            Retry
          </Button>
        </div>
      ) : null}

      <div className="rounded-[18px] border border-white/[0.08] bg-[#0a0b0e] p-3 text-[11px] leading-6 text-[#8d909c]">
        <p className="font-mono uppercase tracking-[0.2em] text-[#5eead4]">
          Integration contract
        </p>
        <p className="mt-2">
          Backend contract target:{' '}
          <span className="font-mono text-[#ebecef]">
            {ASSESSMENT_BACKEND_CONTRACT.path}
          </span>
        </p>
        <p>
          Supported formats:{' '}
          {ASSESSMENT_BACKEND_CONTRACT.supportedFormats.join(', ')} • Max file
          size: {formatBytes(ASSESSMENT_BACKEND_CONTRACT.maxFileSizeBytes)}
        </p>
      </div>
    </Card>
  )
}

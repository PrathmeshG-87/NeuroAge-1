import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const mockNavigate = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>(
    'react-router-dom',
  )
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  }
})

import { MRIUploader } from './MRIUploader'
import { assessmentService } from '@/services/assessment'

describe('MRIUploader', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    mockNavigate.mockClear()
  })

  it('opens the assessment as soon as the backend accepts the upload', async () => {
    const waitForCompletion = vi.spyOn(
      assessmentService,
      'waitForCompletion',
    )
    vi.spyOn(assessmentService, 'createAssessment').mockResolvedValue({
      assessmentId: 'assessment-123',
      status: 'queued',
      message: 'Assessment accepted and queued for processing.',
      createdAt: new Date().toISOString(),
      accessToken: 'token-123',
    })

    render(<MRIUploader />)

    const file = new File(['nii-data'], 'brain.nii.gz', {
      type: 'application/octet-stream',
    })

    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [file] } })
    fireEvent.change(screen.getByLabelText('Subject name'), {
      target: { value: 'Alex Morgan' },
    })

    fireEvent.click(screen.getByRole('button', { name: /submit assessment/i }))

    await waitFor(() => {
      expect(assessmentService.createAssessment).toHaveBeenCalledTimes(1)
    })
    expect(assessmentService.createAssessment).toHaveBeenCalledWith(
      expect.objectContaining({ subjectName: 'Alex Morgan' }),
      expect.any(Function),
    )

    await waitFor(() => {
      expect(screen.getByText(/assessment submitted/i)).toBeInTheDocument()
    })
    expect(waitForCompletion).not.toHaveBeenCalled()
  })

  it('navigates to the detail page after a successful upload', async () => {
    vi.spyOn(assessmentService, 'createAssessment').mockResolvedValue({
      assessmentId: 'assessment-123',
      status: 'queued',
      message: 'Assessment accepted and queued for processing.',
      createdAt: new Date().toISOString(),
      accessToken: 'token-123',
    })

    render(<MRIUploader />)

    const file = new File(['nii-data'], 'brain.nii.gz', {
      type: 'application/octet-stream',
    })

    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [file] } })
    fireEvent.change(screen.getByLabelText('Subject name'), {
      target: { value: 'Alex Morgan' },
    })
    fireEvent.click(screen.getByRole('button', { name: /submit assessment/i }))

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/assessments/assessment-123')
    })
  })
})

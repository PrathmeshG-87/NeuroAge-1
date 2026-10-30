import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AssessmentResult } from '@/services/assessment'
import { assessmentService } from '@/services/assessment'
import { ViewerPage } from './ViewerPage'

vi.mock('@/services/assessment', () => ({
  assessmentService: {
    createAssessment: vi.fn(),
    fetchAssessmentResult: vi.fn(),
    fetchAssessmentStatus: vi.fn(),
    waitForCompletion: vi.fn(),
  },
}))

vi.mock('@/components/mri/MRIViewer', () => ({
  MRIViewer: ({ volumeEndpoint }: { volumeEndpoint?: string }) => (
    <div data-testid="mri-viewer" data-endpoint={volumeEndpoint} />
  ),
}))

describe('ViewerPage', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('shows the MRI volume while brain-age processing is still pending', async () => {
    vi.mocked(assessmentService.createAssessment).mockResolvedValue({
      assessmentId: 'assessment-processing',
      status: 'processing',
      message: 'Processing',
      createdAt: '2026-10-27T00:00:00.000Z',
    })
    vi.mocked(assessmentService.fetchAssessmentResult).mockResolvedValue({
      assessmentId: 'assessment-processing',
      subjectName: 'Research scan',
      status: 'processing',
      message: 'Inference is still running.',
      chronologicalAge: null,
      predictedBrainAge: null,
      brainAgeDifference: null,
      modelName: 'NeuroAge model',
      assessmentDate: '2026-10-27T00:00:00.000Z',
      processingStatus: 'Processing',
      preview: {
        available: true,
        volumeEndpoint: '/api/v1/assessments/assessment-processing/mri/volume',
      },
      modelLimitations: [],
      disclaimer: 'Research use only.',
    } satisfies AssessmentResult)
    vi.mocked(assessmentService.waitForCompletion).mockReturnValue(
      new Promise<AssessmentResult>(() => {}),
    )

    render(
      <MemoryRouter>
        <ViewerPage />
      </MemoryRouter>,
    )

    fireEvent.change(screen.getByLabelText('Subject name'), {
      target: { value: 'Research scan' },
    })
    fireEvent.change(screen.getByLabelText('MRI volume (.nii or .nii.gz)'), {
      target: {
        files: [new File([new Uint8Array([0])], 'scan.nii')],
      },
    })
    fireEvent.click(
      screen.getByRole('button', { name: 'Upload and view slices' }),
    )

    expect(await screen.findByTestId('mri-viewer')).toHaveAttribute(
      'data-endpoint',
      '/api/v1/assessments/assessment-processing/mri/volume',
    )
    await waitFor(() => {
      expect(assessmentService.waitForCompletion).toHaveBeenCalledWith(
        'assessment-processing',
        expect.objectContaining({ intervalMs: 2000 }),
      )
    })
  })
})

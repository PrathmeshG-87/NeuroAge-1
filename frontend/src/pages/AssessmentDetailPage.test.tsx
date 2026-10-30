import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AssessmentDetailPage } from './RoutePlaceholders'
import { assessmentService, type AssessmentResult } from '@/services/assessment'

vi.mock('@/components/mri/MRIViewer', () => ({
  MRIViewer: () => null,
}))

vi.mock('@/services/assessment', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@/services/assessment')>()
  return {
    ...actual,
    assessmentService: {
      ...actual.assessmentService,
      fetchAssessmentResult: vi.fn(),
      fetchAssessmentStatus: vi.fn(),
    },
  }
})

describe('AssessmentDetailPage', () => {
  beforeEach(() => {
    vi.mocked(assessmentService.fetchAssessmentResult).mockResolvedValue({
      assessmentId: 'test-assessment',
      subjectName: 'Research participant',
      status: 'completed',
      message: 'Assessment completed.',
      chronologicalAge: 38,
      predictedBrainAge: 36.881649017333984,
      brainAgeDifference: -1.118350982666016,
      uncertaintyInterval: null,
      modelName: 'NeuroAge-ResNet3D-18',
      assessmentDate: '2026-10-29T17:12:35.000Z',
      processingStatus: 'Completed',
      preview: { available: false },
      modelLimitations: [],
      disclaimer: 'Research use only.',
    } satisfies AssessmentResult)
  })

  it('shows the assessment age values without the removed test-set metric card', async () => {
    render(
      <MemoryRouter initialEntries={['/assessments/test-assessment']}>
        <Routes>
          <Route
            path="/assessments/:id"
            element={<AssessmentDetailPage />}
          />
        </Routes>
      </MemoryRouter>,
    )

    expect(await screen.findByText('38.0 years')).toBeInTheDocument()
    expect(screen.getAllByText('-1.1 years').length).toBeGreaterThan(0)
    expect(screen.queryByText('Prediction interval')).not.toBeInTheDocument()
    expect(screen.queryByText('Test-set MAE')).not.toBeInTheDocument()
    expect(screen.getByText('36.9 years')).toBeInTheDocument()
  })
})

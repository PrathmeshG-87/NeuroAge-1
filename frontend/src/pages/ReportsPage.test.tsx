import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ReportsPage } from './RoutePlaceholders'
import { MOCK_REPORTS, reportService } from '@/services/reports'

describe('ReportsPage', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('keeps the report archive usable when a download fails', async () => {
    vi.spyOn(reportService, 'listReports').mockResolvedValue(MOCK_REPORTS)
    vi.spyOn(reportService, 'downloadReport').mockRejectedValue(
      new Error('The report endpoint returned an error.'),
    )

    render(
      <MemoryRouter>
        <ReportsPage />
      </MemoryRouter>,
    )

    fireEvent.click((await screen.findAllByRole('button', { name: 'Download PDF' }))[0])

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'The report endpoint returned an error.',
    )
    expect(screen.getByRole('heading', { name: 'Authorized report archive' }))
      .toBeInTheDocument()
    expect(screen.getByText('Assessment AS-2408-014')).toBeInTheDocument()
    await waitFor(() => {
      expect(
        screen.getAllByRole('button', { name: 'Download PDF' })[0],
      ).toBeEnabled()
    })
  })

  it('downloads a report as a PDF blob without navigating away', async () => {
    const blob = new Blob(['%PDF-1.4'], { type: 'application/pdf' })
    vi.spyOn(reportService, 'listReports').mockResolvedValue(MOCK_REPORTS)
    vi.spyOn(reportService, 'downloadReport').mockResolvedValue({
      blob,
      fileName: 'assessment.pdf',
    })
    const originalCreateObjectUrl = Object.getOwnPropertyDescriptor(
      window.URL,
      'createObjectURL',
    )
    const originalRevokeObjectUrl = Object.getOwnPropertyDescriptor(
      window.URL,
      'revokeObjectURL',
    )
    const createObjectUrl = vi.fn(() => 'blob:report')
    const revokeObjectUrl = vi.fn()
    Object.defineProperty(window.URL, 'createObjectURL', {
      configurable: true,
      value: createObjectUrl,
    })
    Object.defineProperty(window.URL, 'revokeObjectURL', {
      configurable: true,
      value: revokeObjectUrl,
    })
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => undefined)

    try {
      render(
        <MemoryRouter>
          <ReportsPage />
        </MemoryRouter>,
      )

      fireEvent.click((await screen.findAllByRole('button', { name: 'Download PDF' }))[0])

      await waitFor(() => expect(click).toHaveBeenCalledOnce())
      expect(createObjectUrl).toHaveBeenCalledWith(blob)
      expect(screen.getByRole('heading', { name: 'Authorized report archive' }))
        .toBeInTheDocument()
    } finally {
      if (originalCreateObjectUrl) {
        Object.defineProperty(window.URL, 'createObjectURL', originalCreateObjectUrl)
      } else {
        delete (window.URL as Partial<typeof URL>).createObjectURL
      }
      if (originalRevokeObjectUrl) {
        Object.defineProperty(window.URL, 'revokeObjectURL', originalRevokeObjectUrl)
      } else {
        delete (window.URL as Partial<typeof URL>).revokeObjectURL
      }
    }
  })
})

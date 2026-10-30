import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from './App'

describe('application routes', () => {
  it('opens assessment workspace without an account prompt', () => {
    render(
      <MemoryRouter initialEntries={['/assessment']}>
        <App />
      </MemoryRouter>,
    )

    expect(
      screen.getByRole('heading', { name: /new brain-age assessment/i }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('heading', { name: /sign in|create account/i }),
    ).not.toBeInTheDocument()
  })

  it('does not expose the removed dashboard route', () => {
    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <App />
      </MemoryRouter>,
    )

    expect(
      screen.getByRole('heading', { name: /this page does not exist/i }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('heading', { name: /dashboard/i }),
    ).not.toBeInTheDocument()
  })

  it('returns to the landing page when the sidebar brand is clicked', () => {
    render(
      <MemoryRouter initialEntries={['/methodology']}>
        <App />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getAllByRole('link', { name: 'NeuroAge home' })[0])

    expect(
      screen.getByRole('heading', {
        name: /estimating brain age from MRI/i,
      }),
    ).toBeInTheDocument()
  })
})

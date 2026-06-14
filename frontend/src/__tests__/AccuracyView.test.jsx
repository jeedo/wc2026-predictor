import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '../mocks/server'
import AccuracyView from '../components/AccuracyView'

test('shows overall score', async () => {
  render(<AccuracyView />)
  await waitFor(() => {
    expect(screen.getByText('8 / 12')).toBeInTheDocument()
  })
})

test('shows per-group rows', async () => {
  render(<AccuracyView />)
  await waitFor(() => {
    expect(screen.getByText('Group A')).toBeInTheDocument()
    expect(screen.getByText('Group B')).toBeInTheDocument()
  })
})

test('correct groups show a correct indicator', async () => {
  render(<AccuracyView />)
  await waitFor(() => {
    const rows = screen.getAllByRole('row')
    const groupARow = rows.find(r => r.textContent.includes('Group A'))
    expect(groupARow).toHaveClass('correct')
  })
})

test('incorrect groups show an incorrect indicator', async () => {
  render(<AccuracyView />)
  await waitFor(() => {
    const rows = screen.getAllByRole('row')
    const groupBRow = rows.find(r => r.textContent.includes('Group B'))
    expect(groupBRow).toHaveClass('incorrect')
  })
})

test('shows predicted and actual values', async () => {
  render(<AccuracyView />)
  await waitFor(() => {
    expect(screen.getAllByText('Germany').length).toBeGreaterThan(0)
    expect(screen.getByText('France')).toBeInTheDocument()
  })
})

test('shows loading state initially', () => {
  server.use(http.get('/api/accuracy', () => new Promise(() => {})))
  render(<AccuracyView />)
  expect(document.querySelector('phantom-ui')).toBeInTheDocument()
})

test('shows 404 message when no data', async () => {
  server.use(
    http.get('/api/accuracy', () => new HttpResponse(null, { status: 404 }))
  )
  render(<AccuracyView />)
  await waitFor(() => {
    expect(screen.getByText(/no accuracy/i)).toBeInTheDocument()
  })
})

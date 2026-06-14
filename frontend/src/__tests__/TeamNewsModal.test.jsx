import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { server } from '../mocks/server'
import TeamNewsModal from '../components/TeamNewsModal'

test('shows team name in heading', async () => {
  render(<TeamNewsModal teamName="Germany" onClose={() => {}} />)
  expect(screen.getByText(/Germany/)).toBeInTheDocument()
})

test('shows loading state initially', () => {
  server.use(http.get('/api/news/:team', () => new Promise(() => {})))
  render(<TeamNewsModal teamName="Germany" onClose={() => {}} />)
  expect(screen.getByText(/loading/i)).toBeInTheDocument()
})

test('renders snippets after load', async () => {
  render(<TeamNewsModal teamName="Germany" onClose={() => {}} />)
  await waitFor(() => {
    expect(screen.getByText('Müller back in full training')).toBeInTheDocument()
    expect(screen.getByText('Germany prep warm-up win')).toBeInTheDocument()
  })
})

test('shows no-news message when snippets empty', async () => {
  server.use(
    http.get('/api/news/:team', () =>
      HttpResponse.json({ snippets: [], date: null })
    )
  )
  render(<TeamNewsModal teamName="Germany" onClose={() => {}} />)
  await waitFor(() => expect(screen.getByText(/no recent news/i)).toBeInTheDocument())
})

test('shows error message on fetch failure', async () => {
  server.use(http.get('/api/news/:team', () => HttpResponse.error()))
  render(<TeamNewsModal teamName="Germany" onClose={() => {}} />)
  await waitFor(() => expect(screen.getByText(/could not load/i)).toBeInTheDocument())
})

test('calls onClose when close button clicked', async () => {
  const onClose = vi.fn()
  render(<TeamNewsModal teamName="Germany" onClose={onClose} />)
  fireEvent.click(screen.getByRole('button', { name: /close/i }))
  expect(onClose).toHaveBeenCalledOnce()
})

test('calls onClose when backdrop clicked', async () => {
  const onClose = vi.fn()
  render(<TeamNewsModal teamName="Germany" onClose={onClose} />)
  fireEvent.click(screen.getByRole('dialog'))
  expect(onClose).toHaveBeenCalledOnce()
})

test('calls onClose when Escape key pressed', async () => {
  const onClose = vi.fn()
  render(<TeamNewsModal teamName="Germany" onClose={onClose} />)
  fireEvent.keyDown(document, { key: 'Escape' })
  expect(onClose).toHaveBeenCalledOnce()
})

test('does not close when clicking inside modal box', async () => {
  const onClose = vi.fn()
  render(<TeamNewsModal teamName="Germany" onClose={onClose} />)
  await waitFor(() => screen.getByText('Müller back in full training'))
  fireEvent.click(screen.getByText('Müller back in full training'))
  expect(onClose).not.toHaveBeenCalled()
})

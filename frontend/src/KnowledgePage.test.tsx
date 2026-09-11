import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import App from './App'

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  window.history.replaceState({}, '', '/')
})

describe('KnowledgePage', () => {
  it('shows accessible administrator login when no session exists', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse({ detail: 'Required' }, 401)))
    window.history.replaceState({}, '', '/knowledge')

    render(<App />)

    expect(await screen.findByRole('heading', { name: 'Sign in to continue' })).toBeTruthy()
    const password = screen.getByLabelText('Password') as HTMLInputElement
    expect(password.autocomplete).toBe('current-password')
    expect(screen.getByText('Official Cadre AI domains')).toBeTruthy()
  })

  it('announces and focuses a login error', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ detail: 'Required' }, 401))
      .mockResolvedValueOnce(jsonResponse({ detail: 'Invalid administrator credentials' }, 401))
    vi.stubGlobal('fetch', fetchMock)
    window.history.replaceState({}, '', '/knowledge')
    render(<App />)

    fireEvent.change(await screen.findByLabelText('Password'), {
      target: { value: 'wrong password' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    const alert = await screen.findByRole('alert')
    expect(alert.textContent).toContain('Invalid administrator credentials')
    expect(document.activeElement).toBe(alert)
  })

  it('uploads an approved file and refreshes active sources', async () => {
    let uploaded = false
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.endsWith('/session')) return jsonResponse({ authenticated: true })
      if (url.endsWith('/files')) {
        expect(init?.method).toBe('POST')
        expect(init?.body).toBeInstanceOf(FormData)
        uploaded = true
        return jsonResponse({
          results: [
            {
              source_id: 'file-services',
              name: 'services.txt',
              status: 'indexed',
              detail: 'Source indexed successfully',
              chunk_count: 1,
            },
          ],
        })
      }
      if (url.endsWith('/sources')) {
        return jsonResponse(
          uploaded
            ? [
                {
                  source_id: 'file-services',
                  kind: 'file',
                  title: 'Services',
                  locator: 'services.txt',
                  retrieved_at: '2026-09-11T10:00:00Z',
                  content_hash: 'hash',
                  content_file: 'contents/file-services.json',
                  chunk_count: 1,
                },
              ]
            : [],
        )
      }
      return jsonResponse({ detail: 'Unexpected request' }, 500)
    })
    vi.stubGlobal('fetch', fetchMock)
    window.history.replaceState({}, '', '/knowledge')
    render(<App />)

    await screen.findByRole('heading', { name: 'Add approved sources' })
    const fileInput = screen.getByLabelText('Choose files') as HTMLInputElement
    fireEvent.change(fileInput, {
      target: { files: [new File(['approved content'], 'services.txt', { type: 'text/plain' })] },
    })
    fireEvent.click(
      screen.getByLabelText(/I confirm these sources are official and approved/i),
    )
    fireEvent.click(screen.getByRole('button', { name: 'Add 1 file' }))

    expect(await screen.findByText('Source indexed successfully')).toBeTruthy()
    await waitFor(() => expect(screen.getByText('Services')).toBeTruthy())
    expect(screen.getByText('1 approved source')).toBeTruthy()
  })
})

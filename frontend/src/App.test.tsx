import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import App from './App'

describe('App', () => {
  it('renders the Phase 1 support shell without an active chat connection', () => {
    render(<App />)

    expect(screen.getByRole('heading', { name: 'How can we help?' })).toBeTruthy()
    expect(
      (screen.getByRole('textbox', { name: 'Message Cadre AI' }) as HTMLTextAreaElement)
        .disabled,
    ).toBe(true)
    expect(
      screen.getByText(/does not call OpenAI, OpenRouter, or any external API/i),
    ).toBeTruthy()
  })
})

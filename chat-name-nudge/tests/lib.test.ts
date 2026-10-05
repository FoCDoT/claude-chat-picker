import { describe, expect, test } from 'claude-code/testing'

import { conventionsFor, digest, namesSession, namingPrompt, parseNames, slug, userText } from '../hooks/lib'

describe('chat-name-nudge helpers', () => {
  test('slug matches Claude Code project folders', async () => {
    expect(slug('/Users/me/code/my-app')).toBe('-Users-me-code-my-app')
    expect(slug('/a/my project')).toBe('-a-my-project')
  })

  test('longest folder prefix wins and is added to the default', async () => {
    const conf = { default: 'BASE', folders: { '/w': 'W', '/w/app/': 'APP', '/w/appx': 'NO' } }
    expect(conventionsFor(conf, '/w/app/sub')).toBe('BASE\nAPP')
    expect(conventionsFor(conf, '/w/other')).toBe('BASE\nW')
    expect(conventionsFor(conf, '/elsewhere')).toBe('BASE')
    expect(conventionsFor(null, '/x')).toContain('3-7 words')
  })

  test('userText drops harness rows and unwraps commands', async () => {
    expect(userText('<command-name>/lavish-pages</command-name><command-args></command-args>')).toBe('/lavish-pages')
    expect(userText('<bash-stdout>x</bash-stdout>')).toBeNull()
    expect(userText('<system-reminder>x</system-reminder>')).toBeNull()
    expect(userText('[Image #1] <pasted_content id="a">fix my mouse</pasted_content>')).toBe('fix my mouse')
  })

  test('digest lists prompts, tools and replies', async () => {
    const d = digest(
      [
        { role: 'user', text: 'my MX Master is dead', toolUses: [] },
        { role: 'assistant', text: 'Restart BTLEServer', toolUses: [{ tool: 'Bash' }, { tool: 'Bash' }] },
      ],
      '/w/app',
    )
    expect(d).toContain('- my MX Master is dead')
    expect(d).toContain('Bash×2')
    expect(d).toContain('- Restart BTLEServer')
    expect(namingPrompt('C', d, ['old one'])).toContain('Do not repeat these earlier suggestions: old one')
  })

  test('parseNames strips numbering, quotes and periods', async () => {
    expect(parseNames('1. "mx master fix".\n- cswap setup\n\n* mx master fix\nfour')).toEqual(['mx master fix', 'cswap setup', 'four'])
  })

  test('clean strips escapes so a name cannot inject terminal codes or newlines', async () => {
    expect(parseNames('evil\u001b[31m red\u202e name')).toEqual(['evil [31m red  name'])
  })

  test('namesSession spots /rename and --name rows', async () => {
    expect(namesSession('{"type":"custom-title","customTitle":"x"}')).toBe(true)
    expect(namesSession('{"type":"agent-name","agentName":"x"}')).toBe(true)
    expect(namesSession('{"type":"ai-title","aiTitle":"x"}')).toBe(false)
  })
})

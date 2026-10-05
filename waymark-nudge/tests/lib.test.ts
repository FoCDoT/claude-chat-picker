import { describe, expect, test } from 'claude-code/testing'

import { rulesFor, digest, namesSession, namingPrompt, parseNames, slug, userText } from '../hooks/lib'

describe('waymark-nudge helpers', () => {
  test('slug matches Claude Code project folders', async () => {
    expect(slug('/Users/me/code/my-app')).toBe('-Users-me-code-my-app')
    expect(slug('/a/my project')).toBe('-a-my-project')
  })

  test('longest folder prefix wins and is added to the default', async () => {
    const conf = { default: 'BASE', folders: { '/w': 'W', '/w/app/': 'APP', '/w/appx': 'NO' } }
    expect(rulesFor(conf, '/w/app/sub')).toBe('BASE\nAPP')
    expect(rulesFor(conf, '/w/app')).toBe('BASE\nAPP')
    expect(rulesFor(conf, '/w/other')).toBe('BASE\nW')
    expect(rulesFor(conf, '/elsewhere')).toBe('BASE')
    expect(rulesFor(null, '/x')).toContain('3-7 words')
  })

  test('userText drops harness rows and unwraps commands', async () => {
    expect(userText('<command-name>/review</command-name><command-args>42</command-args>')).toBe('/review 42')
    expect(userText('<bash-stdout>x</bash-stdout>')).toBeNull()
    expect(userText('<system-reminder>x</system-reminder>')).toBeNull()
    expect(userText('[Image #1] <pasted_content id="a">trace</pasted_content>')).toBe('trace')
  })

  test('digest lists prompts, tools and replies', async () => {
    const d = digest(
      [
        { role: 'user', text: 'add retries to the uploader', toolUses: [] },
        { role: 'assistant', text: 'Added exponential backoff', toolUses: [{ tool: 'Bash' }, { tool: 'Bash' }] },
      ],
      '/w/app',
    )
    expect(d).toContain('- add retries to the uploader')
    expect(d).toContain('Bash×2')
    expect(d).toContain('- Added exponential backoff')
    expect(namingPrompt('C', d, ['old one'])).toContain('Do not repeat these earlier suggestions: old one')
  })

  test('parseNames strips numbering, quotes and periods', async () => {
    expect(parseNames('1. "uploader retries".\n- cache cleanup\n\n* uploader retries\nfourth')).toEqual(['uploader retries', 'cache cleanup', 'fourth'])
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

/** Pure helpers, shared shape with bin/claude-chat-picker. */

export const MODEL = 'claude-sonnet-5-5'

/** Turns at which an unnamed chat gets a (fresh) suggestion: the chat drifts, so look again. */
export const SUGGEST_AT = [1, 4, 10, 25]

export type Conventions = { default?: string; folders?: Record<string, string> }

export type Msg = { role: 'user' | 'assistant'; text: string; toolUses: { tool: string }[] }

/** Claude Code's project folder name for a cwd. */
export function slug(cwd: string): string {
  return cwd.replace(/[^A-Za-z0-9]/g, '-')
}

export function conventionsFor(conf: Conventions | null, folder: string): string {
  let text = conf?.default || '3-7 words, lowercase, no trailing period. Say what the chat is about.'
  let best = ''
  for (const prefix of Object.keys(conf?.folders ?? {})) {
    const p = prefix.replace(/\/+$/, '')
    if ((folder === p || folder.startsWith(p + '/')) && p.length > best.length) best = prefix
  }
  if (best) text += '\n' + conf!.folders![best]
  return text
}

/** The person's typed text, without harness wrappers; null when there is none. */
export function userText(raw: string): string | null {
  let t = raw.trim()
  const cmd = /<command-name>(.*?)<\/command-name>/.exec(t)
  if (cmd) {
    const args = /<command-args>([\s\S]*?)<\/command-args>/.exec(t)
    return `${cmd[1]} ${args?.[1] ?? ''}`.trim()
  }
  if (/^(<local-command|<system-reminder|Caveat:|\[Request interrupted|<task-notification|<bash-|This session is being continued)/.test(t)) return null
  t = t.replace(/<system-reminder>[\s\S]*?<\/system-reminder>/g, '')
  t = t.replace(/<pasted_content[^>]*>/g, '').replace(/<\/pasted_content>/g, '').replace(/\[Image #\d+\]/g, '').trim()
  return t || null
}

export function digest(messages: readonly Msg[], folder: string): string {
  const prompts: string[] = []
  const replies: string[] = []
  const tools = new Map<string, number>()
  for (const m of messages) {
    if (m.role === 'user') {
      const t = userText(m.text)
      if (t) prompts.push(t.slice(0, 500))
    } else {
      if (m.text.trim()) replies.push(m.text.trim().slice(0, 300))
      for (const u of m.toolUses) tools.set(u.tool, (tools.get(u.tool) ?? 0) + 1)
    }
  }
  const keep = <T,>(xs: T[], head: number, tail: number) => (xs.length <= head + tail ? xs : [...xs.slice(0, head), ...xs.slice(-tail)])
  const lines = [`Folder: ${folder}`, 'What the person asked, in order:', ...keep(prompts, 12, 8).map(p => `- ${p}`)]
  const top = [...tools].sort((a, b) => b[1] - a[1]).slice(0, 8)
  if (top.length) lines.push('Tools used: ' + top.map(([k, v]) => `${k}×${v}`).join(', '))
  if (replies.length) lines.push("Some of the assistant's replies:", ...keep(replies, 3, 5).map(r => `- ${r}`))
  return lines.join('\n').slice(0, 9000)
}

export function namingPrompt(conventions: string, dig: string, avoid: readonly string[] = []): string {
  return (
    'You name Claude Code chats so the person can find them later in a list.\n\n' +
    `Naming conventions:\n${conventions}\n\n` +
    `Chat digest:\n${dig}\n\n` +
    (avoid.length ? `Do not repeat these earlier suggestions: ${avoid.join(', ')}\n\n` : '') +
    'Give 3 different candidate names, most accurate first, one per line, nothing else: ' +
    'no numbering, no quotes, no commentary. Base them on what the chat actually covered ' +
    "across the WHOLE conversation, not just the end. If it covered two unrelated topics, join them with ' + ' " +
    "(e.g. 'mx master fix + open source tool hunt'). Never use the folder's own name as the project name."
  )
}

/** Control characters (incl. ESC) and bidi overrides: model output must not reach the prompt or terminal as escapes. */
export function clean(s: string): string {
  return s.replace(/[\u0000-\u001f\u007f-\u009f\u200b-\u200f\u202a-\u202e\u2066-\u2069]/g, ' ')
}

export function parseNames(text: string): string[] {
  const out: string[] = []
  for (const raw of text.split('\n')) {
    const n = clean(raw)
      .replace(/^\s*(?:[-*•]|\d+[.)])\s*/, '')
      .trim()
      .replace(/\.+$/, '')
      .replace(/^["'`]+|["'`]+$/g, '')
      .replace(/\.+$/, '')
      .trim()
    if (n && n.length <= 80 && !out.includes(n)) out.push(n)
  }
  return out.slice(0, 3)
}

/** Does this transcript line set a name (/rename, or --name at launch)? */
export function namesSession(line: string): boolean {
  return /"type":"(custom-title|agent-name)"/.test(line)
}

export function fit(s: string, n: number): string {
  return s.length <= n ? s : s.slice(0, Math.max(0, n - 1)) + '…'
}

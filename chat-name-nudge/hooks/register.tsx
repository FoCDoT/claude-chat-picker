import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { NudgePhase } from '../types'
import { MODEL, SUGGEST_AT, clean, conventionsFor, digest, fit, namesSession, namingPrompt, parseNames, slug } from './lib'
import type { Conventions } from './lib'

const phase = atom({ plugin: 'chat-name-nudge', key: 'phase' } as const, 'checking' as NudgePhase)
const names = atom({ plugin: 'chat-name-nudge', key: 'names' } as const, [] as string[])
const pick = atom({ plugin: 'chat-name-nudge', key: 'pick' } as const, 0)
const turns = atom({ plugin: 'chat-name-nudge', key: 'turns' } as const, 0)
const namedAt = atom({ plugin: 'chat-name-nudge', key: 'namedAt' } as const, 0)

async function configDir($: EngineInterface): Promise<string> {
  return (await $.env.get('CLAUDE_CONFIG_DIR')) ?? `${(await $.env.get('HOME')) ?? ''}/.claude`
}

/** Named by /rename (custom-title.json or a custom-title row) or by --name at launch (agent-name row). */
async function isNamed($: EngineInterface): Promise<boolean> {
  const dir = `${await configDir($)}/projects/${slug(await $.session.cwd())}`
  const id = await $.session.id()
  if (await $.fs.exists(`${dir}/${id}/custom-title.json`)) return true
  // grep, not $.fs.read: transcripts outgrow the 4 MiB read limit.
  const r = await $.process.run(['grep', '-m1', '-E', '"type":"(custom-title|agent-name)"', `${dir}/${id}.jsonl`])
  return r.exitCode === 0 && namesSession(r.stdout)
}

async function conventions($: EngineInterface): Promise<string> {
  let conf: Conventions | null = null
  try {
    conf = JSON.parse(await $.fs.read(`${(await $.env.get('HOME')) ?? ''}/.claude/chat-naming.json`)) as Conventions
  } catch {
    conf = null
  }
  return conventionsFor(conf, await $.session.cwd())
}

/** One row in ~/.claude/chat-naming-stats.jsonl, shared with claude-chat-picker --stats. */
async function logStat($: EngineInterface, row: Record<string, unknown>): Promise<void> {
  const line = JSON.stringify({ ts: new Date(await $.clock.now()).toISOString(), source: 'mod', ...row })
  const file = `${(await $.env.get('HOME')) ?? ''}/.claude/chat-naming-stats.jsonl`
  // argv, not string interpolation: the line and path reach sh as $1/$2, never parsed as script
  await $.process.run(['sh', '-c', 'umask 077; printf "%s\\n" "$1" >> "$2"', 'sh', line, file])
}

let inFlight = false

/** Ask Sonnet for names. Never renames: the band only offers them. */
async function suggest($: EngineInterface, fresh: boolean): Promise<void> {
  if (inFlight) return
  inFlight = true
  try {
    if (await isNamed($)) {
      await update($, phase, () => 'named')
      return
    }
    const msgs = await $.session.messages()
    if (!msgs.some(m => m.role === 'user')) return
    const avoid = fresh ? await read($, names) : []
    if ((await read($, phase)) !== 'ready') await update($, phase, () => 'thinking')
    const res = await $.model.complete({
      model: MODEL,
      prompt: namingPrompt(await conventions($), digest(msgs, await $.session.cwd()), avoid),
      maxTokens: 120,
      effort: 'low',
      timeoutMs: 60_000,
    })
    if (res.isAnswered) {
      const u = res.usage
      void logStat($, { kind: 'model', model: MODEL, session: await $.session.id(), in: u.input_tokens, out: u.output_tokens, cache_read: u.cache_read_input_tokens, cache_write: u.cache_creation_input_tokens })
    }
    const got = res.isAnswered ? parseNames(res.text) : []
    if ((await read($, phase)) === 'named' || (await read($, phase)) === 'dismissed') return
    if (got.length === 0) {
      if ((await read($, names)).length === 0) await update($, phase, () => 'failed')
      else await update($, phase, () => 'ready')
      return
    }
    await update($, names, () => got)
    await update($, pick, () => 0)
    const at = await read($, turns)
    await update($, namedAt, () => at)
    await update($, phase, () => 'ready')
  } finally {
    inFlight = false
  }
}

async function useName($: EngineInterface, name: string): Promise<void> {
  const filled = await $.prompt.fill({ text: `/rename ${name}` })
  $.ui.toast(filled.isFilled ? 'Press Enter to rename this chat' : `Run: /rename ${name}`)
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'name-suggest',
      description: 'Suggest a name for this chat (Sonnet); you then press Enter on /rename',
    })
    const p = await read($, phase)
    if (p === 'checking' || p === 'idle' || p === 'thinking') {
      if (await isNamed($)) await update($, phase, () => 'named')
      else {
        await update($, phase, () => 'idle')
        // a resumed, still-unnamed chat: suggest straight away
        if ((await $.session.messages()).length > 1) void suggest($, false)
      }
    }
    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    const r = await next(e)
    await update($, turns, t => t + 1)
    const count = await read($, turns)
    const p = await read($, phase)
    if (p === 'named' || p === 'dismissed') return r
    const due = p === 'idle' || p === 'failed' || (SUGGEST_AT.includes(count) && count > (await read($, namedAt)))
    if (due) void suggest($, false)
    return r
  })

  // The person ran /rename (ours pre-filled or their own): stop nudging.
  on('command.run', { command: 'rename' }, async ($, e, next) => {
    const r = await next(e)
    await update($, phase, () => 'named')
    const title = clean(e.args).trim()
    if (title) void logStat($, { kind: 'rename', session: await $.session.id(), folder: await $.session.cwd(), title, how: 'rename-command' })
    return r
  })

  on('command.run', { command: 'name-suggest' }, async $ => {
    await update($, phase, () => 'idle')
    void suggest($, true)
    return { text: 'Asking Sonnet for a name; it will show above the prompt.' }
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const p = await read($, phase)
    if (e.props.hasSurvey || (p !== 'ready' && p !== 'thinking')) return next(e)
    const { Box, Text, Button } = $.ui.resolve(e)
    if (p === 'thinking') {
      return (
        <Box>
          <Text dimColor>✎ unnamed chat · thinking of a name…</Text>
        </Box>
      )
    }
    const list = await read($, names)
    const i = (await read($, pick)) % Math.max(1, list.length)
    const name = list[i] ?? ''
    const room = Math.max(12, (e.props.bodyColumns ?? 80) - 52)
    return (
      <Box>
        <Text dimColor>✎ unnamed chat · try </Text>
        <Text bold>{fit(name, room)}</Text>
        <Text dimColor>{list.length > 1 ? ` (${i + 1}/${list.length}) ` : ' '}</Text>
        <Button key="use" label="use" onPress={() => useName($, name)} />
        {list.length > 1 && <Button key="next" label="next" plain onPress={() => update($, pick, k => k + 1)} />}
        <Button key="more" label="more" plain onPress={() => suggest($, true)} />
        <Button key="dismiss" label="dismiss" plain dimColor onPress={() => update($, phase, () => 'dismissed')} />
      </Box>
    )
  })
}

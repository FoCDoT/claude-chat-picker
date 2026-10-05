import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { NudgePhase } from '../types'
import { DEFAULT_MODEL, SUGGEST_AT, clean, digest, fit, namesSession, namingPrompt, parseNames, rulesFor, slug } from './lib'
import type { Config } from './lib'

const phase = atom({ plugin: 'waymark-nudge', key: 'phase' } as const, 'checking' as NudgePhase)
const names = atom({ plugin: 'waymark-nudge', key: 'names' } as const, [] as string[])
const pick = atom({ plugin: 'waymark-nudge', key: 'pick' } as const, 0)
const turns = atom({ plugin: 'waymark-nudge', key: 'turns' } as const, 0)
const namedAt = atom({ plugin: 'waymark-nudge', key: 'namedAt' } as const, 0)

async function home($: EngineInterface): Promise<string> {
  return (await $.env.get('HOME')) ?? ''
}

async function claudeDir($: EngineInterface): Promise<string> {
  return (await $.env.get('CLAUDE_CONFIG_DIR')) ?? `${await home($)}/.claude`
}

async function configFile($: EngineInterface): Promise<string> {
  return `${(await $.env.get('XDG_CONFIG_HOME')) ?? `${await home($)}/.config`}/waymark/config.json`
}

async function statsFile($: EngineInterface): Promise<string> {
  return `${(await $.env.get('XDG_STATE_HOME')) ?? `${await home($)}/.local/state`}/waymark/stats.jsonl`
}

/** Named by /rename (custom-title.json or a custom-title record) or by --name at launch (agent-name record). */
async function isNamed($: EngineInterface): Promise<boolean> {
  const dir = `${await claudeDir($)}/projects/${slug(await $.session.cwd())}`
  const id = await $.session.id()
  if (await $.fs.exists(`${dir}/${id}/custom-title.json`)) return true
  // grep rather than $.fs.read: transcripts can exceed the 4 MiB read limit.
  const result = await $.process.run(['grep', '-m1', '-E', '"type":"(custom-title|agent-name)"', `${dir}/${id}.jsonl`])
  return result.exitCode === 0 && namesSession(result.stdout)
}

async function loadConfig($: EngineInterface): Promise<Config | null> {
  try {
    return JSON.parse(await $.fs.read(await configFile($))) as Config
  } catch {
    return null
  }
}

/** Append one event to the usage log shared with `waymark stats`. */
async function record($: EngineInterface, event: Record<string, unknown>): Promise<void> {
  const line = JSON.stringify({ ts: new Date(await $.clock.now()).toISOString(), source: 'mod', ...event })
  // Values reach sh as positional arguments, never as script text.
  await $.process.run([
    'sh',
    '-c',
    'umask 077; mkdir -p "$(dirname "$2")" && printf "%s\\n" "$1" >> "$2"',
    'sh',
    line,
    await statsFile($),
  ])
}

let inFlight = false

/** Request title suggestions. This never renames: the band only offers them. */
async function suggest($: EngineInterface, fresh: boolean): Promise<void> {
  if (inFlight) return
  inFlight = true
  try {
    if (await isNamed($)) {
      await update($, phase, () => 'named')
      return
    }
    const messages = await $.session.messages()
    if (!messages.some(m => m.role === 'user')) return

    const config = await loadConfig($)
    const model = config?.model || DEFAULT_MODEL
    const cwd = await $.session.cwd()
    const avoid = fresh ? await read($, names) : []
    if ((await read($, phase)) !== 'ready') await update($, phase, () => 'thinking')

    const result = await $.model.complete({
      model,
      prompt: namingPrompt(rulesFor(config, cwd), digest(messages, cwd), avoid),
      maxTokens: 120,
      effort: 'low',
      timeoutMs: 60_000,
    })
    if (result.isAnswered) {
      const u = result.usage
      void record($, {
        kind: 'model',
        model,
        session: await $.session.id(),
        in: u.input_tokens,
        out: u.output_tokens,
        cache_read: u.cache_read_input_tokens,
        cache_write: u.cache_creation_input_tokens,
      })
    }

    const suggested = result.isAnswered ? parseNames(result.text) : []
    const current = await read($, phase)
    if (current === 'named' || current === 'dismissed') return
    if (suggested.length === 0) {
      const hasEarlier = (await read($, names)).length > 0
      await update($, phase, () => (hasEarlier ? 'ready' : 'failed'))
      return
    }
    await update($, names, () => suggested)
    await update($, pick, () => 0)
    const turnCount = await read($, turns)
    await update($, namedAt, () => turnCount)
    await update($, phase, () => 'ready')
  } finally {
    inFlight = false
  }
}

async function useName($: EngineInterface, name: string): Promise<void> {
  const filled = await $.prompt.fill({ text: `/rename ${name}` })
  $.ui.toast(filled.isFilled ? 'Press Enter to rename this session' : `Run: /rename ${name}`)
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'name-suggest',
      description: 'Suggest a title for this session; you confirm it with /rename',
    })
    const current = await read($, phase)
    if (current === 'checking' || current === 'idle' || current === 'thinking') {
      if (await isNamed($)) {
        await update($, phase, () => 'named')
      } else {
        await update($, phase, () => 'idle')
        // A resumed session that is still unnamed gets a suggestion straight away.
        if ((await $.session.messages()).length > 1) void suggest($, false)
      }
    }
    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    const result = await next(e)
    await update($, turns, t => t + 1)
    const count = await read($, turns)
    const current = await read($, phase)
    if (current === 'named' || current === 'dismissed') return result
    const due =
      current === 'idle' || current === 'failed' || (SUGGEST_AT.includes(count) && count > (await read($, namedAt)))
    if (due) void suggest($, false)
    return result
  })

  // Any /rename, whether pre-filled by the band or typed, ends the nudge.
  on('command.run', { command: 'rename' }, async ($, e, next) => {
    const result = await next(e)
    await update($, phase, () => 'named')
    const title = clean(e.args).trim()
    if (title) {
      void record($, {
        kind: 'rename',
        session: await $.session.id(),
        folder: await $.session.cwd(),
        title,
        how: 'rename-command',
      })
    }
    return result
  })

  on('command.run', { command: 'name-suggest' }, async $ => {
    await update($, phase, () => 'idle')
    void suggest($, true)
    return { text: 'Requesting title suggestions; they will appear above the prompt.' }
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const current = await read($, phase)
    if (e.props.hasSurvey || (current !== 'ready' && current !== 'thinking')) return next(e)
    const { Box, Text, Button } = $.ui.resolve(e)
    if (current === 'thinking') {
      return (
        <Box>
          <Text dimColor>Unnamed session · finding a title…</Text>
        </Box>
      )
    }
    const list = await read($, names)
    const index = (await read($, pick)) % Math.max(1, list.length)
    const name = list[index] ?? ''
    const room = Math.max(12, (e.props.bodyColumns ?? 80) - 52)
    return (
      <Box>
        <Text dimColor>Unnamed session · suggested title </Text>
        <Text bold>{fit(name, room)}</Text>
        <Text dimColor>{list.length > 1 ? ` (${index + 1}/${list.length}) ` : ' '}</Text>
        <Button key="use" label="use" onPress={() => useName($, name)} />
        {list.length > 1 && <Button key="next" label="next" plain onPress={() => update($, pick, k => k + 1)} />}
        <Button key="more" label="more" plain onPress={() => suggest($, true)} />
        <Button key="dismiss" label="dismiss" plain dimColor onPress={() => update($, phase, () => 'dismissed')} />
      </Box>
    )
  })
}

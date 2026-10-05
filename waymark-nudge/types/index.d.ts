export type NudgePhase = 'checking' | 'idle' | 'thinking' | 'ready' | 'named' | 'dismissed' | 'failed'

declare module 'claude-code' {
  interface PluginState {
    'waymark-nudge': {
      phase: NudgePhase
      /** Suggested titles, most accurate first. */
      names: string[]
      /** Which candidate the band shows. */
      pick: number
      /** Completed turns this session, to pace refreshes. */
      turns: number
      /** The turn count the current names were computed at. */
      namedAt: number
    }
  }
}

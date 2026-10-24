// REQ-133 AC-2: a Playwright spec that plays the strategy live socket itself answers like the real server, which echoes on
// every push the `seq` (version) of the follow message it was computed for (backend live_push.py -> echo_seq). The page drops
// a push without the version it sent. This is the one place the e2e specs copy the seq.
export function followSeq(message: unknown): number | null {
  try {
    const seq = JSON.parse(String(message))?.seq
    return Number.isInteger(seq) ? seq : null
  } catch {
    return null
  }
}

// One per socket: `remember(message)` on each follow message, `stamp(push)` on each push answering it.
// A push that names its own seq (an older-body push on purpose) keeps it; no remembered seq means no seq is added.
export function echoSeq() {
  let seq: number | null = null
  return {
    remember(message: unknown) {
      seq = followSeq(message)
    },
    stamp<T extends object>(push: T): T & { seq?: number } {
      return seq === null || 'seq' in push ? push : { ...push, seq }
    },
  }
}

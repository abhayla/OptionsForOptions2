// REQ-133 AC-2: the test fake sockets answer like the real server, which echoes on every push the `seq` (version) of the
// follow message it was computed for (backend live_push.py -> echo_seq). A pushed object that names its own seq (a test of
// an older-version push) and a raw string are sent as given; a socket that sent no versioned body gets no seq.
export function echoSeq(socket, obj) {
  if (typeof obj !== 'object' || obj === null || 'seq' in obj) return obj
  let seq
  try {
    seq = JSON.parse(socket.sent?.at(-1) ?? 'null')?.seq
  } catch {
    return obj
  }
  return Number.isInteger(seq) ? { ...obj, seq } : obj
}

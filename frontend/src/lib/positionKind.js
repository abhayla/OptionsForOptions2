// ADR-330 (64): a real position's row carries the server's one line and no Exit / Stops. The tag is the server's `position_kind`
// (the stored fact: position_kind.kind_of). Only exactly 'paper' offers Exit and Stops; anything else, a missing field included,
// offers neither (fail closed).
export const KIND_UNREAD_LINE = 'Cannot tell whether this is a real or a paper position, so Exit and Stops are not shown. Check it in Kite.' // pending owner read; used only when the server sent no line
export const isPaperKind = (row) => row?.position_kind === 'paper'

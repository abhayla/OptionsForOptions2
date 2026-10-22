// The underlyings the screens offer, in display order. ONE home on the screen side; the server's home is
// ofo.instruments.catalogue.SUPPORTED_UNDERLYINGS (name -> exchange segment), and every API route refuses any other
// name with gate_underlying_unsupported (REQ-001 AC-1/AC-4). BANKNIFTY and FINNIFTY join at builder row 46 (REQ-090).
export const UNDERLYINGS = ['NIFTY', 'SENSEX']

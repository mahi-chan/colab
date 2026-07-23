/** Intel HEX parsing into an AVR program image (Uint16Array of flash words). */

/** Load Intel HEX text into a flash byte buffer (little-endian words). */
export function loadHexInto(source: string, target: Uint8Array): void {
  for (const raw of source.split("\n")) {
    const line = raw.trim();
    if (line[0] !== ":") continue;
    const type = line.substr(7, 2);
    if (type !== "00") continue; // only data records
    const nbytes = parseInt(line.substr(1, 2), 16);
    const addr = parseInt(line.substr(3, 4), 16);
    for (let i = 0; i < nbytes; i++) {
      target[addr + i] = parseInt(line.substr(9 + i * 2, 2), 16);
    }
  }
}

/** Build a program image (flash) sized `words` from Intel HEX text. */
export function hexToProgram(source: string, words = 0x8000): Uint16Array {
  const program = new Uint16Array(words);
  loadHexInto(source, new Uint8Array(program.buffer));
  return program;
}

/** Basic sanity check that a string looks like Intel HEX. */
export function isIntelHex(text: string): boolean {
  const t = text.trim();
  return t.startsWith(":") && /:[0-9A-Fa-f]{2}/.test(t);
}

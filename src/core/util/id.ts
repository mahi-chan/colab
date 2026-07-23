/** Small id helpers — no external deps so `core` stays platform-agnostic. */

let counter = 0;

/** Generate a reasonably-unique id with an optional prefix. */
export function uid(prefix = "id"): string {
  counter = (counter + 1) % 1_000_000;
  const rand = Math.random().toString(36).slice(2, 8);
  return `${prefix}_${Date.now().toString(36)}${counter.toString(36)}${rand}`;
}

/**
 * Produce the next reference designator (e.g. R1, R2, U1) for a given prefix,
 * scanning the designators already in use.
 */
export function nextRef(prefix: string, used: Iterable<string>): string {
  let max = 0;
  for (const ref of used) {
    const m = ref.match(new RegExp(`^${prefix}(\\d+)$`));
    if (m) max = Math.max(max, parseInt(m[1], 10));
  }
  return `${prefix}${max + 1}`;
}

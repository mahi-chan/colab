/**
 * Modified Nodal Analysis (MNA) DC solver.
 *
 * Nodes are numbered 1..numNodes; node 0 is ground and is omitted from the
 * matrix. Resistors and current sources stamp the conductance matrix directly;
 * ideal voltage sources add an extra branch-current unknown. The assembled
 * system A·x = z is solved by Gaussian elimination with partial pivoting.
 */

export interface ResistorStamp {
  a: number;
  b: number;
  /** Ohms. Must be > 0. */
  r: number;
}

export interface CurrentStamp {
  /** Current (A) injected into `pos` and drawn from `neg`. */
  pos: number;
  neg: number;
  i: number;
}

export interface VoltageStamp {
  pos: number;
  neg: number;
  /** Volts (V(pos) - V(neg)). */
  v: number;
}

export interface MnaResult {
  /** Node voltage; node 0 is always 0. */
  voltage(node: number): number;
  /** Current through the k-th voltage source (order added). */
  sourceCurrent(k: number): number;
  ok: boolean;
}

export function solveMNA(
  numNodes: number,
  resistors: ResistorStamp[],
  currents: CurrentStamp[],
  voltages: VoltageStamp[],
): MnaResult {
  const m = voltages.length;
  const N = numNodes + m;

  if (N === 0) {
    return { voltage: () => 0, sourceCurrent: () => 0, ok: true };
  }

  const A: number[][] = Array.from({ length: N }, () => new Array(N).fill(0));
  const z: number[] = new Array(N).fill(0);
  const idx = (node: number) => node - 1; // matrix index for a non-ground node

  for (const { a, b, r } of resistors) {
    if (r <= 0) continue;
    const g = 1 / r;
    if (a !== 0) A[idx(a)][idx(a)] += g;
    if (b !== 0) A[idx(b)][idx(b)] += g;
    if (a !== 0 && b !== 0) {
      A[idx(a)][idx(b)] -= g;
      A[idx(b)][idx(a)] -= g;
    }
  }

  for (const { pos, neg, i } of currents) {
    if (pos !== 0) z[idx(pos)] += i;
    if (neg !== 0) z[idx(neg)] -= i;
  }

  voltages.forEach(({ pos, neg, v }, k) => {
    const br = numNodes + k;
    if (pos !== 0) {
      A[idx(pos)][br] += 1;
      A[br][idx(pos)] += 1;
    }
    if (neg !== 0) {
      A[idx(neg)][br] -= 1;
      A[br][idx(neg)] -= 1;
    }
    z[br] += v;
  });

  const x = gaussianSolve(A, z);
  if (!x) {
    return { voltage: () => 0, sourceCurrent: () => 0, ok: false };
  }

  return {
    voltage: (node) => (node === 0 ? 0 : x[idx(node)] ?? 0),
    sourceCurrent: (k) => x[numNodes + k] ?? 0,
    ok: true,
  };
}

/** Gaussian elimination with partial pivoting. Returns null if singular. */
function gaussianSolve(A: number[][], b: number[]): number[] | null {
  const n = b.length;
  // Work on copies.
  const M = A.map((row) => row.slice());
  const y = b.slice();

  for (let col = 0; col < n; col++) {
    // Pivot: largest magnitude in this column.
    let pivot = col;
    let best = Math.abs(M[col][col]);
    for (let r = col + 1; r < n; r++) {
      const v = Math.abs(M[r][col]);
      if (v > best) {
        best = v;
        pivot = r;
      }
    }
    if (best < 1e-12) return null; // singular

    if (pivot !== col) {
      [M[col], M[pivot]] = [M[pivot], M[col]];
      [y[col], y[pivot]] = [y[pivot], y[col]];
    }

    const diag = M[col][col];
    for (let r = col + 1; r < n; r++) {
      const factor = M[r][col] / diag;
      if (factor === 0) continue;
      for (let c = col; c < n; c++) M[r][c] -= factor * M[col][c];
      y[r] -= factor * y[col];
    }
  }

  // Back-substitution.
  const x = new Array(n).fill(0);
  for (let r = n - 1; r >= 0; r--) {
    let sum = y[r];
    for (let c = r + 1; c < n; c++) sum -= M[r][c] * x[c];
    x[r] = sum / M[r][r];
  }
  return x;
}

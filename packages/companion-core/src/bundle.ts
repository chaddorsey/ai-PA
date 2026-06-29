/**
 * bundle.ts — Plan 2, Task 2
 *
 * loadBundle(legId, resolvePath): Promise<Bundle>
 *   Calls resolvePath(legId) to get raw JSON, validates it, throws on errors.
 *
 * validateBundle(raw): string[]
 *   Returns a list of human-readable problem strings.  Empty array = valid.
 *   Tolerates nullable place/theme/side fields (allowed per contract).
 */

import type { Bundle, Unit, SquibUnit, InterstitialUnit } from './types.js';

// ── Internal helpers ──────────────────────────────────────────────────────────

function isObj(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null;
}

function isFiniteNum(v: unknown): v is number {
  return typeof v === 'number' && isFinite(v);
}

function isNonEmptyString(v: unknown): v is string {
  return typeof v === 'string' && v.length > 0;
}

// ── validateBundle ────────────────────────────────────────────────────────────

/**
 * Validates a raw (unknown) value against the Bundle schema.
 * Returns an array of problem descriptions.  Empty = valid.
 *
 * Rules (per Plan 0 §B):
 * - leg: non-empty string
 * - schedule_basis.kind ∈ {trip-actual, generic-scheduled}
 * - units: non-empty array; each unit validated by kind
 * - stations: non-empty array
 * - geometry.coordinates: non-empty
 * - position_table rows: 4-number arrays
 * - eta_table rows: p10 ≤ p50 ≤ p90
 * Nullable fields (place, theme, side) are NOT flagged when null.
 */
export function validateBundle(raw: unknown): string[] {
  const problems: string[] = [];

  if (!isObj(raw)) {
    return ['bundle must be a non-null object'];
  }

  // ── leg ───────────────────────────────────────────────────────────────────
  if (!isNonEmptyString(raw['leg'])) {
    problems.push('leg must be a non-empty string');
  }

  // ── schedule_basis ────────────────────────────────────────────────────────
  const sb = raw['schedule_basis'];
  if (!isObj(sb)) {
    problems.push('schedule_basis must be an object');
  } else {
    const VALID_KINDS = new Set(['trip-actual', 'generic-scheduled']);
    if (!VALID_KINDS.has(sb['kind'] as string)) {
      problems.push(
        `schedule_basis.kind must be "trip-actual" or "generic-scheduled"; got: ${String(sb['kind'])}`,
      );
    }
    if (!Array.isArray(sb['valid_dates'])) {
      problems.push('schedule_basis.valid_dates must be an array');
    }
  }

  // ── stations ──────────────────────────────────────────────────────────────
  const stations = raw['stations'];
  if (!Array.isArray(stations)) {
    problems.push('stations must be an array');
  } else if (stations.length === 0) {
    problems.push('stations must be non-empty');
  }

  // ── geometry ──────────────────────────────────────────────────────────────
  const geo = raw['geometry'];
  if (!isObj(geo)) {
    problems.push('geometry must be an object');
  } else {
    if (!Array.isArray(geo['coordinates'])) {
      problems.push('geometry.coordinates must be an array');
    } else if ((geo['coordinates'] as unknown[]).length === 0) {
      problems.push('geometry.coordinates must be non-empty');
    }
  }

  // ── units ─────────────────────────────────────────────────────────────────
  const units = raw['units'];
  if (!Array.isArray(units)) {
    problems.push('units must be an array');
  } else if (units.length === 0) {
    problems.push('units must be non-empty');
  } else {
    for (let i = 0; i < units.length; i++) {
      problems.push(...validateUnit(units[i], i));
    }
  }

  // ── layers ────────────────────────────────────────────────────────────────
  const layers = raw['layers'];
  if (!isObj(layers)) {
    problems.push('layers must be an object');
  } else {
    for (const key of ['guide', 'lore', 'science', 'connections', 'themes'] as const) {
      if (!(key in layers)) {
        problems.push(`layers.${key} is missing`);
      }
    }
  }

  // ── position_table ────────────────────────────────────────────────────────
  const pt = raw['position_table'];
  if (!Array.isArray(pt)) {
    problems.push('position_table must be an array');
  } else {
    for (let i = 0; i < pt.length; i++) {
      const row = pt[i];
      if (!Array.isArray(row) || row.length !== 4) {
        problems.push(
          `position_table[${i}] must be a 4-element array [elapsed_min, mile, lat, lon]; got length ${Array.isArray(row) ? row.length : 'non-array'}`,
        );
      } else {
        for (let j = 0; j < 4; j++) {
          if (!isFiniteNum(row[j])) {
            problems.push(`position_table[${i}][${j}] must be a finite number`);
          }
        }
      }
    }
  }

  // ── eta_table ─────────────────────────────────────────────────────────────
  const et = raw['eta_table'];
  if (!Array.isArray(et)) {
    problems.push('eta_table must be an array');
  } else {
    for (let i = 0; i < et.length; i++) {
      const row = et[i];
      if (!isObj(row)) {
        problems.push(`eta_table[${i}] must be an object`);
        continue;
      }
      const p10 = row['p10_min'];
      const p50 = row['p50_min'];
      const p90 = row['p90_min'];
      if (!isFiniteNum(p10)) problems.push(`eta_table[${i}].p10_min must be a finite number`);
      if (!isFiniteNum(p50)) problems.push(`eta_table[${i}].p50_min must be a finite number`);
      if (!isFiniteNum(p90)) problems.push(`eta_table[${i}].p90_min must be a finite number`);
      if (isFiniteNum(p10) && isFiniteNum(p50) && p10 > p50) {
        problems.push(`eta_table[${i}]: p10_min (${p10}) must be ≤ p50_min (${p50})`);
      }
      if (isFiniteNum(p50) && isFiniteNum(p90) && p50 > p90) {
        problems.push(`eta_table[${i}]: p50_min (${p50}) must be ≤ p90_min (${p90})`);
      }
    }
  }

  return problems;
}

// ── validateUnit ──────────────────────────────────────────────────────────────

function validateUnit(raw: unknown, idx: number): string[] {
  const problems: string[] = [];
  const label = `units[${idx}]`;

  if (!isObj(raw)) {
    return [`${label} must be a non-null object`];
  }

  // Required string scalars
  if (!isNonEmptyString(raw['id'])) problems.push(`${label}.id must be a non-empty string`);
  if (!isNonEmptyString(raw['text'])) problems.push(`${label}.text must be a non-empty string`);
  if (!isNonEmptyString(raw['audio'])) problems.push(`${label}.audio must be a non-empty string`);

  // Nullable string fields — null is allowed; only flag when definitely wrong type
  const place = raw['place'];
  if (place !== null && typeof place !== 'string') {
    problems.push(`${label}.place must be a string or null`);
  }
  const theme = raw['theme'];
  if (theme !== null && typeof theme !== 'string') {
    problems.push(`${label}.theme must be a string or null`);
  }

  // Numeric scalars
  if (!isFiniteNum(raw['lat'])) problems.push(`${label}.lat must be a finite number`);
  if (!isFiniteNum(raw['lon'])) problems.push(`${label}.lon must be a finite number`);
  if (!isFiniteNum(raw['dur_s'])) problems.push(`${label}.dur_s must be a finite number`);

  // Salience: integer 1–5
  const sal = raw['salience'];
  if (
    typeof sal !== 'number' ||
    !Number.isInteger(sal) ||
    sal < 1 ||
    sal > 5
  ) {
    problems.push(`${label}.salience must be an integer 1–5; got ${String(sal)}`);
  }

  // Kind-specific fields
  const kind = raw['kind'];
  if (kind === 'squib') {
    if (!isFiniteNum(raw['mile'])) {
      problems.push(`${label}.mile must be a finite number (squib requires mile)`);
    }
  } else if (kind === 'interstitial') {
    if (!isFiniteNum(raw['from_mi'])) {
      problems.push(`${label}.from_mi must be a finite number (interstitial requires from_mi)`);
    }
    if (!isFiniteNum(raw['to_mi'])) {
      problems.push(`${label}.to_mi must be a finite number (interstitial requires to_mi)`);
    }
  } else {
    problems.push(`${label}.kind must be "squib" or "interstitial"; got ${String(kind)}`);
  }

  return problems;
}

// ── loadBundle ────────────────────────────────────────────────────────────────

/**
 * Load and validate a bundle.  The `resolvePath` adapter is injected so this
 * function works in Node (readFileSync), the browser (fetch), and Capacitor
 * (BundleStore.getPath) without modification.
 *
 * Throws an Error if validation fails, with the problem list in the message.
 */
export async function loadBundle(
  legId: string,
  resolvePath: (legId: string) => Promise<unknown>,
): Promise<Bundle> {
  const raw = await resolvePath(legId);
  const problems = validateBundle(raw);
  if (problems.length > 0) {
    throw new Error(
      `Bundle "${legId}" failed validation (${problems.length} problem${problems.length === 1 ? '' : 's'}):\n` +
        problems.map((p) => `  • ${p}`).join('\n'),
    );
  }
  // Safe cast: validateBundle verified all required fields
  return raw as Bundle;
}

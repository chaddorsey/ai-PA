/**
 * sanitize.ts — make server-derived text safe to write to a terminal.
 *
 * WHY THIS IS NOT PARANOIA. The agent behind this conversation relays third-party content: email
 * bodies, Slack messages, GitHub issues, fetched web pages. That content reaches this process as
 * ordinary delta text and is written to a TTY that interprets control sequences. It is untrusted
 * input on a trusted surface, and on a SHARED conversation one surface can introduce it and
 * another render it.
 *
 * ALLOWLIST, NOT BLOCKLIST. A blocklist written against the familiar case (CSI … m, colour) misses
 * the ones that matter here:
 *   - OSC 52 writes the user's CLIPBOARD. The sharpest primitive in the set.
 *   - OSC 8 renders a hyperlink whose visible text need not match its target.
 *   - DCS / APC / PM / SOS can leave the terminal swallowing subsequent output, so the client
 *     looks hung while the conversation continues normally on every other surface.
 *   - The 8-bit C1 forms (U+009B CSI, U+009D OSC, …) bypass any ESC-anchored pattern entirely.
 *
 * BIDI AND ZERO-WIDTH ARE STRIPPED — a judgement call worth stating rather than leaving silent.
 * Bidi overrides reorder displayed text and zero-width characters hide it. Neither is a control
 * *sequence*, so a filter keyed only on control characters would pass both, and both are spoofing
 * primitives against a surface whose origin labels are a security signal. The accepted cost is
 * that genuinely right-to-left content loses its explicit ordering marks.
 *
 * WHAT THIS DOES NOT DO: newline is ordinary content and must survive, so sanitization alone
 * cannot stop text from forging an origin label by starting a new line with "peer >". That is
 * handled separately by line discipline — see indentContinuation.
 */

/** Control characters that are legitimate content and must survive. */
const KEEP = new Set(["\n", "\t"]);

const ESC = "\u001b";
const BEL = "\u0007";
/** 8-bit string terminator. */
const ST_8BIT = "\u009c";

/**
 * String-type sequences (OSC/DCS/SOS/PM/APC) are removed by a SCANNER, not a pattern.
 *
 * A regex cannot do this job safely. A lazy body (`[\s\S]*?`) backtracks: given many introducers
 * and no terminator the engine restarts its forward scan at every one of them, which is quadratic
 * in ATTACKER-SUPPLIED text — 125KB of bare `ESC ]` measured at 3.3s of blocked event loop, during
 * which the client renders nothing and answers no approval request. Excluding the terminator
 * characters from the body stops the backtracking, but then a repetition cap is needed to keep one
 * unterminated introducer from scanning to end-of-string — and any cap is a cliff: a body one
 * character past it did not match at all, so the entire payload survived as visible text (clean at
 * 4096, through at 4097).
 *
 * A single left-to-right pass has neither problem. Every character is visited once, so cost is
 * linear with no cap, and a body of any length is removed in full.
 */
/** 7-bit introducers: ESC followed by one of these opens a string sequence. */
const SEQ_INTRODUCERS_7BIT = "]P^_X";
/** 8-bit (C1) introducers: DCS, SOS, OSC, PM, APC. */
const SEQ_INTRODUCERS_8BIT = "\u0090\u0098\u009d\u009e\u009f";

function stripStringSequences(input: string): string {
  let out = "";
  let i = 0;
  while (i < input.length) {
    const ch = input[i] as string;
    const next = input[i + 1];
    let body = -1;
    if (ch === ESC && next !== undefined && SEQ_INTRODUCERS_7BIT.includes(next)) body = i + 2;
    else if (SEQ_INTRODUCERS_8BIT.includes(ch)) body = i + 1;
    if (body === -1) {
      out += ch;
      i += 1;
      continue;
    }
    // Consume to the string terminator. An UNTERMINATED sequence runs to end-of-input, which is
    // the safe reading — a terminal would swallow the rest too. An ESC that is not `ESC \` ends
    // the scan WITHOUT being consumed, so whatever it introduces is still seen by the next pass.
    let j = body;
    while (j < input.length) {
      const c = input[j];
      if (c === BEL || c === ST_8BIT) {
        j += 1;
        break;
      }
      if (c === ESC) {
        if (input[j + 1] === "\\") j += 2;
        break;
      }
      j += 1;
    }
    i = j;
  }
  return out;
}

/**
 * Escape sequences removed by pattern. Only bounded grammars are left here: a CSI sequence is
 * parameters, then intermediates, then exactly one final byte, with nothing to backtrack over.
 */
const SEQUENCES: RegExp[] = [
  // CSI — parameters, intermediates, final byte.
  new RegExp(`${ESC}\\[[0-?]*[ -/]*[@-~]`, "g"),
  /\u009b[0-?]*[ -\/]*[@-~]/g,
  // Any remaining two-character escape (charset selection, cursor save, …).
  new RegExp(`${ESC}[@-Z\\\\-_]`, "g"),
];

/**
 * Bidi controls and characters that render as nothing — see the module note.
 *
 * The earlier class named the familiar members and missed siblings that do the same job:
 * U+061C ARABIC LETTER MARK is a Bidi_Control exactly like the U+200F already listed; the
 * U+E0000-E007F TAG block is the canonical invisible-text smuggling range; soft hyphen, Hangul
 * fillers, the combining grapheme joiner and variation selectors all have no visible glyph. Text
 * copied out of this terminal and pasted into a shell or another agent prompt carries whatever
 * survives here, so "renders as nothing" is the property that matters, not "is a control code".
 */
const INVISIBLE = new RegExp(
  [
    "\\u00ad", // soft hyphen
    "\\u034f", // combining grapheme joiner (its own branch: a class would fold it into a neighbour)
    "\\u061c", // Arabic letter mark — a Bidi_Control, like the U+200F below
    "[\\u115f\\u1160\\u3164\\uffa0]", // Hangul fillers: blank glyphs
    "[\\u17b4\\u17b5]", // Khmer inherent vowels: blank
    "[\\u180b-\\u180e]", // Mongolian variation selectors + vowel separator
    "[\\u200b-\\u200f]", // zero-width space/joiners, LRM/RLM
    "[\\u202a-\\u202e]", // bidi embedding/override
    "[\\u2060-\\u2064]", // word joiner + invisible operators
    "[\\u2066-\\u2069]", // bidi isolates
    "[\\ufe00-\\ufe0f]", // variation selectors
    "[\\ufff9-\\ufffb]", // interlinear annotation: hides the annotated run
    "\\ufeff", // BOM / zero-width no-break space
    "[\\u{e0000}-\\u{e007f}]", // TAG block: the canonical invisible-text smuggling range
    "[\\u{e0100}-\\u{e01ef}]", // variation selectors supplement — the other 240 of them
  ].join("|"),
  "gu",
);

export interface SanitizeOptions {
  /** Truncate beyond this many characters. One huge delta can lock a terminal on its own. */
  maxLength?: number;
}

const DEFAULT_MAX_LENGTH = 8192;
const TRUNCATION_MARKER = "… [truncated]";

/**
 * Strip everything a terminal would act on, from any string this process did not author.
 *
 * Apply BEFORE the client adds its own colouring, so the client's escapes survive and the
 * server's do not.
 */
export function sanitize(text: string, options: SanitizeOptions = {}): string {
  const max = options.maxLength ?? DEFAULT_MAX_LENGTH;

  // Bound the input BEFORE any pass, not just the output after them. Every stage below is linear
  // in its input, but the per-codepoint filter allocates an array the size of that input — so
  // truncating at the end still pays full price on the way there. 2x leaves room for sequences
  // that sanitize away to nothing without changing what a legitimate delta renders as.
  let truncated = text.length > max * 2;
  let out = truncated ? text.slice(0, max * 2) : text;

  out = stripStringSequences(out);
  for (const pattern of SEQUENCES) out = out.replace(pattern, "");
  out = out.replace(INVISIBLE, "");

  // Anything that survived — a truncated sequence, a bare introducer — is dropped here with every
  // other control code, so nothing actionable is left.
  out = [...out]
    .filter((ch) => {
      if (KEEP.has(ch)) return true;
      const code = ch.codePointAt(0) ?? 0;
      if (code < 0x20 || code === 0x7f) return false; // C0 + DEL
      if (code >= 0x80 && code <= 0x9f) return false; // C1
      return true;
    })
    .join("");

  if (out.length > max) {
    out = out.slice(0, max);
    truncated = true;
  }
  return truncated ? out + TRUNCATION_MARKER : out;
}

/**
 * Indent continuation lines so server text can never occupy the label column.
 *
 * Newline legitimately survives sanitization, so a delta containing a line break followed by
 * "peer >" would otherwise print something indistinguishable from a real origin label — and on a
 * shared conversation that label is how the operator tells their own turn from another surface's.
 */
export function indentContinuation(text: string, indent = "  "): string {
  return text.replace(/\n/g, `\n${indent}`);
}

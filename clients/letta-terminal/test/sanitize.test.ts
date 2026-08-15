/**
 * Sanitizer table tests.
 *
 * These use \u escapes rather than literal control characters so the payloads are readable in a
 * diff and cannot be mangled by an editor or a copy-paste.
 */

import { describe, expect, it } from "vitest";
import { indentContinuation, sanitize } from "../src/sanitize.js";

const ESC = "\u001b";
const BEL = "\u0007";

describe("sanitize", () => {
  it("leaves ordinary text, newlines and tabs untouched", () => {
    expect(sanitize("hello\nworld\tok")).toBe("hello\nworld\tok");
  });

  it("strips CSI sequences, including screen-clear and cursor movement", () => {
    expect(sanitize(`${ESC}[2Kerased`)).toBe("erased");
    expect(sanitize(`${ESC}[1Aup`)).toBe("up");
    expect(sanitize(`${ESC}[3J${ESC}[Hwiped`)).toBe("wiped");
    // Colour is a CSI sequence too: the SERVER does not get to colour our output.
    expect(sanitize(`${ESC}[31mred${ESC}[0m`)).toBe("red");
  });

  it("strips OSC 52 — the clipboard write", () => {
    expect(sanitize(`${ESC}]52;c;aGVsbG8=${BEL}after`)).toBe("after");
    expect(sanitize(`${ESC}]52;c;aGVsbG8=${ESC}\\after`)).toBe("after");
  });

  it("strips OSC 8 hyperlinks so visible text cannot disguise a target", () => {
    expect(sanitize(`${ESC}]8;;https://evil.example${BEL}click me${ESC}]8;;${BEL}`)).toBe(
      "click me",
    );
  });

  it("strips the window-title OSC", () => {
    expect(sanitize(`${ESC}]0;pwned${BEL}text`)).toBe("text");
  });

  it("strips DCS/APC/PM payloads entirely", () => {
    expect(sanitize(`${ESC}Pq#0;2;0;0;0${ESC}\\after`)).toBe("after");
    expect(sanitize(`${ESC}_G a=T${ESC}\\after`)).toBe("after");
    expect(sanitize(`${ESC}^privmsg${ESC}\\after`)).toBe("after");
  });

  it("strips 8-BIT C1 forms, which bypass any ESC-anchored pattern", () => {
    expect(sanitize("\u009b2Kerased")).toBe("erased"); // 8-bit CSI
    expect(sanitize(`\u009d52;c;aGk=${BEL}after`)).toBe("after"); // 8-bit OSC
  });

  it("strips a bare ESC and any stray control characters", () => {
    expect(sanitize(`a${ESC}b\u0000c\u007fd`)).toBe("abcd");
  });

  it("strips bidi overrides and zero-width characters", () => {
    expect(sanitize("safe\u202etxet desrever")).toBe("safetxet desrever");
    expect(sanitize("in\u200bvisible")).toBe("invisible");
    expect(sanitize("\ufeffbom")).toBe("bom");
  });

  it("strips invisible characters that are not bidi or zero-width SPACE", () => {
    // The original class named the familiar members and missed siblings doing the same job.
    // Everything here renders as nothing, so it survives a copy out of the terminal and into a
    // shell or another agent's prompt without the user ever seeing it.
    expect(sanitize("a\u061cb")).toBe("ab"); // Arabic letter mark — a Bidi_Control
    expect(sanitize("a\u{e0041}\u{e0042}b")).toBe("ab"); // TAG block: invisible text smuggling
    expect(sanitize("a\u00adb")).toBe("ab"); // soft hyphen
    expect(sanitize("a\u3164b")).toBe("ab"); // Hangul filler: a blank glyph
    expect(sanitize("a\ufe0fb")).toBe("ab"); // variation selector
    expect(sanitize("a\u{e0100}b")).toBe("ab"); // variation selectors SUPPLEMENT: 240 more
    expect(sanitize("a\ufff9b\ufffac\ufffbd")).toBe("abcd"); // interlinear annotation hides a run
  });

  // The bound below is a SECURITY property, not a nicety. The agent relays third-party content,
  // so a mail body full of unterminated introducers is attacker-reachable. Cost must not depend on
  // how many introducers the attacker packs in: with an unbounded lazy payload the engine restarts
  // its forward scan at every one of them, and 125KB measured at 3.3 SECONDS of blocked event loop
  // — during which the client reads no frames and answers no approval request.
  // `maxLength` is passed explicitly and large on purpose. With the default the input is
  // truncated to 16KB before the first pass, so the hostile payload never reaches the code under
  // test and the timing assertion passes whatever that code does — which is how the quadratic
  // body survived a test written to catch it.
  const UNBOUNDED = { maxLength: 4_000_000 };

  it("bounds cost on unterminated OSC introducers", () => {
    const t0 = performance.now();
    sanitize(`${ESC}]`.repeat(64_000), UNBOUNDED);
    expect(performance.now() - t0).toBeLessThan(100);
  });

  it("bounds cost on unterminated DCS introducers", () => {
    const t0 = performance.now();
    sanitize(`${ESC}P`.repeat(32_000), UNBOUNDED);
    expect(performance.now() - t0).toBeLessThan(100);
  });

  it("bounds cost on unterminated 8-BIT introducers too", () => {
    // The C1 forms bypass every ESC-anchored pattern, so they need their own measurement.
    const t0 = performance.now();
    sanitize("\u009d".repeat(64_000), UNBOUNDED);
    expect(performance.now() - t0).toBeLessThan(100);
  });

  it("removes a string-sequence payload of ANY length, not just a short one", () => {
    // Every bounded-body implementation has a cliff: one character past the cap the sequence did
    // not match at all, so its entire payload survived as visible text. Measured clean at 4096
    // and through at 4097 — a clipboard write is no less dangerous for being long.
    for (const bodyLength of [10, 4_096, 4_097, 40_000]) {
      const payload = "A".repeat(bodyLength);
      const out = sanitize(`${ESC}]52;c;${payload}${BEL}after`, UNBOUNDED);
      expect(out).toBe("after");
    }
  });

  it("bounds cost on a huge plain-text delta", () => {
    // The per-codepoint filter allocates an array the size of its INPUT, so truncating only at the
    // end still pays full price on the way there.
    const t0 = performance.now();
    sanitize("a".repeat(4_000_000));
    expect(performance.now() - t0).toBeLessThan(50);
  });

  it("bounds length so one delta cannot lock the terminal", () => {
    const out = sanitize("x".repeat(20_000), { maxLength: 100 });
    expect(out).toHaveLength(100 + "… [truncated]".length);
    expect(out.endsWith("… [truncated]")).toBe(true);
  });

  it("leaves nothing a terminal would act on, for a mixed hostile payload", () => {
    const hostile = `${ESC}[2K${ESC}]52;c;cHduZWQ=${BEL}\u009b1A\u202etext${ESC}Pdcs${ESC}\\`;
    const out = sanitize(hostile);
    expect(out).toBe("text");
    // Belt and braces: no C0, DEL or C1 byte survived anywhere.
    const anyControl = [...out].some((ch) => {
      const c = ch.codePointAt(0) ?? 0;
      return (c < 0x20 && ch !== "\n" && ch !== "\t") || c === 0x7f || (c >= 0x80 && c <= 0x9f);
    });
    expect(anyControl).toBe(false);
  });
});

/**
 * Per-member coverage of the three classes the sanitizer is built from.
 *
 * The suite above tests each CLASS through one representative member, which is how the coverage
 * came to be thinner than 47/47 made it look: dropping four of the five 8-bit introducers, or all
 * but one branch of the invisible set, left it green. The code is sound — this closes the gap
 * between what it does and what is ASSERTED, so a future edit to any one member fails here rather
 * than in a terminal.
 *
 * Table-driven on purpose: adding an introducer or an invisible range to the source without adding
 * it here leaves an obvious hole in a list, rather than a silent one in a regex.
 */
describe("sanitize — every member of every class", () => {
  const PAYLOAD = "payload";
  const ST = `${ESC}\\`;

  // ── string-sequence introducers (the SCANNER, sanitize.ts SEQ_INTRODUCERS_*) ──
  const SEVEN_BIT: Array<[string, string]> = [
    ["OSC (]) — clipboard, hyperlinks, window title", "]"],
    ["DCS (P)", "P"],
    ["PM (^)", "^"],
    ["APC (_)", "_"],
    ["SOS (X)", "X"],
  ];
  for (const [name, introducer] of SEVEN_BIT) {
    it(`strips the 7-bit ${name} sequence`, () => {
      // Terminated by BEL and by the 7-bit ST: a scanner that handles one and not the other
      // leaves the payload visible for the other half of real inputs.
      expect(sanitize(`before${ESC}${introducer}${PAYLOAD}${BEL}after`)).toBe("beforeafter");
      expect(sanitize(`before${ESC}${introducer}${PAYLOAD}${ST}after`)).toBe("beforeafter");
      // Unterminated runs to end-of-input, which is what a terminal would do too.
      expect(sanitize(`before${ESC}${introducer}${PAYLOAD}`)).toBe("before");
    });
  }

  const EIGHT_BIT: Array<[string, string]> = [
    ["DCS (U+0090)", ""],
    ["SOS (U+0098)", ""],
    ["OSC (U+009D)", ""],
    ["PM (U+009E)", ""],
    ["APC (U+009F)", ""],
  ];
  for (const [name, introducer] of EIGHT_BIT) {
    it(`strips the 8-bit ${name} sequence, which no ESC-anchored pattern can see`, () => {
      expect(sanitize(`before${introducer}${PAYLOAD}${BEL}after`)).toBe("beforeafter");
      // U+009C is the 8-bit string terminator, the form that pairs with these introducers.
      expect(sanitize(`before${introducer}${PAYLOAD}after`)).toBe("beforeafter");
      expect(sanitize(`before${introducer}${PAYLOAD}`)).toBe("before");
    });
  }

  // ── the invisible/bidi class (sanitize.ts INVISIBLE) ──
  //
  // One representative per BRANCH of the alternation, so deleting any single branch fails here.
  const INVISIBLE_MEMBERS: Array<[string, string]> = [
    ["soft hyphen U+00AD", "­"],
    ["combining grapheme joiner U+034F", "͏"],
    ["Arabic letter mark U+061C", "؜"],
    ["Hangul filler U+3164", "ㅤ"],
    ["Khmer inherent vowel U+17B4", "឴"],
    ["Mongolian vowel separator U+180E", "᠎"],
    ["zero-width space U+200B", "​"],
    ["right-to-left override U+202E", "‮"],
    ["word joiner U+2060", "⁠"],
    ["left-to-right isolate U+2066", "⁦"],
    ["variation selector U+FE0F", "️"],
    ["interlinear annotation anchor U+FFF9", "￹"],
    ["BOM U+FEFF", "﻿"],
    ["TAG block U+E0001", "\u{e0001}"],
    ["variation selectors supplement U+E0100", "\u{e0100}"],
  ];
  for (const [name, ch] of INVISIBLE_MEMBERS) {
    it(`strips ${name}`, () => {
      // Between two visible characters, so a failure cannot be masked by trimming.
      expect(sanitize(`a${ch}b`)).toBe("ab");
    });
  }

  // ── the final per-codepoint backstop (sanitize.ts, the C0/DEL and C1 filters) ──
  //
  // This runs LAST and catches whatever survived the passes above — a truncated sequence, a bare
  // introducer, a lone C1 byte that never introduced anything. It is the layer that makes
  // "nothing actionable is left" true rather than merely intended, and it was unbound.
  it("leaves no C1 code point renderable — every one is consumed or dropped", () => {
    // The C1 block splits three ways, and saying so is the point: a flat "all become ab" would be
    // FALSE for six of the 32 and would have to be weakened until it asserted almost nothing.
    //
    //   · the five string introducers swallow to end-of-input when unterminated (a terminal does
    //     the same), so the trailing "b" goes with them;
    //   · U+009B is the 8-bit CSI and consumes its final byte, which here is the "b";
    //   · the other 26 introduce nothing and are dropped by the final per-codepoint backstop —
    //     that backstop is what this test exists for, and it was previously unbound.
    const SWALLOWS_REST = new Set([0x90, 0x98, 0x9d, 0x9e, 0x9f]);
    const CSI_8BIT = 0x9b;

    for (let code = 0x80; code <= 0x9f; code += 1) {
      const ch = String.fromCodePoint(code);
      const label = `U+00${code.toString(16).toUpperCase()}`;
      const expected = SWALLOWS_REST.has(code) || code === CSI_8BIT ? "a" : "ab";
      expect(sanitize(`a${ch}b`), `${label} rendered unexpectedly`).toBe(expected);
      // Whatever the disposal route, the byte itself must never reach the terminal.
      expect(sanitize(`a${ch}b`), `${label} survived`).not.toContain(ch);
    }
  });

  it("drops every C0 code point and DEL, keeping only newline and tab", () => {
    for (let code = 0x00; code <= 0x1f; code += 1) {
      const ch = String.fromCodePoint(code);
      const expected = ch === "\n" || ch === "\t" ? `a${ch}b` : "ab";
      expect(sanitize(`a${ch}b`), `U+00${code.toString(16).toUpperCase()} mishandled`).toBe(
        expected,
      );
    }
    expect(sanitize("ab")).toBe("ab");
  });
});

describe("indentContinuation", () => {
  it("indents continuation lines so content cannot occupy the label column", () => {
    // Newline is legitimate content and survives sanitization, so this is the second half of the
    // label-forgery defence.
    expect(indentContinuation("first\npeer > forged")).toBe("first\n  peer > forged");
  });

  it("leaves single-line text alone", () => {
    expect(indentContinuation("just one line")).toBe("just one line");
  });
});

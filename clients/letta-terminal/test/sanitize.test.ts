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
  });

  // The bound below is a SECURITY property, not a nicety. The agent relays third-party content,
  // so a mail body full of unterminated introducers is attacker-reachable. Cost must not depend on
  // how many introducers the attacker packs in: with an unbounded lazy payload the engine restarts
  // its forward scan at every one of them, and 125KB measured at 3.3 SECONDS of blocked event loop
  // — during which the client reads no frames and answers no approval request.
  it("bounds cost on unterminated OSC introducers", () => {
    const t0 = performance.now();
    sanitize(`${ESC}]`.repeat(64_000));
    expect(performance.now() - t0).toBeLessThan(100);
  });

  it("bounds cost on unterminated DCS introducers", () => {
    const t0 = performance.now();
    sanitize(`${ESC}P`.repeat(32_000));
    expect(performance.now() - t0).toBeLessThan(100);
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

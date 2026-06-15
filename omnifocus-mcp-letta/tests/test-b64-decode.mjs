// Regression test for the bridge's base64 param decoder (B64_DECODE_JS).
// Bug (2026-06-15): the decoder built a per-byte Latin-1 string and never
// UTF-8-decoded it, so •/smart-quotes/em-dashes became mojibake in OF notes.
// Run: node omnifocus-mcp-letta/tests/test-b64-decode.mjs
import assert from "node:assert";

const C = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

// Mirrors the FIXED B64_DECODE_JS logic (loop + UTF-8 reassembly).
function decodeFixed(s) {
  let r = "";
  for (let i = 0; i < s.length;) {
    const a = C.indexOf(s[i++]), b = C.indexOf(s[i++]),
          c = C.indexOf(s[i++]), d = C.indexOf(s[i++]);
    r += String.fromCharCode((a << 2) | (b >> 4));
    if (c >= 0) r += String.fromCharCode(((b & 15) << 4) | (c >> 2));
    if (d >= 0) r += String.fromCharCode(((c & 3) << 6) | d);
  }
  return decodeURIComponent(escape(r));
}

for (const original of [
  JSON.stringify({ note: "café • “smart” — em‑dash ✓ ✗ ↳ 🚀" }),
  JSON.stringify({ name: "Review Kiley’s audit", body: "• one\n• twö" }),
  JSON.stringify({ plain: "ascii only, no surprises" }),
]) {
  const b64 = Buffer.from(original, "utf8").toString("base64");
  const out = decodeFixed(b64);
  assert.strictEqual(out, original, `round-trip failed for: ${original}`);
}
console.log("ok - base64 decoder round-trips UTF-8 (3 cases)");

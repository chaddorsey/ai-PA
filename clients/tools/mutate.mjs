#!/usr/bin/env node
/**
 * Mutation harness for the two continuity client packages.
 *
 * WHY THIS EXISTS. Three remediation rounds shipped a comparable defect set with a green suite.
 * The cause was measured: thirteen single-component reverts of load-bearing fixes left every test
 * passing — including one that restores a hang on every approval. Tests had been written from the
 * fix rather than from the property, and "verified" by reverting whole COMMITS, which proves the
 * commit is load-bearing and nothing at all about the component.
 *
 * So: every fix in these packages carries an entry in `mutations.mjs` that reverts exactly that
 * component, plus the test that must fail when it does. A fix whose mutation leaves the suite
 * green is not done — it is either untested or unnecessary, and both are findings.
 *
 *   node tools/mutate.mjs             # run every mutation
 *   node tools/mutate.mjs 1 5 12      # run these ids
 *   node tools/mutate.mjs --list      # show the table without running anything
 *
 * Exit code 0 only when every mutation ran and every one of them FAILED its stated test.
 */

import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { MUTATIONS } from "./mutations.mjs";

const CLIENTS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), "..");

const args = process.argv.slice(2);
const listOnly = args.includes("--list");
const wanted = args.filter((a) => /^\d+[a-z]?$/.test(a));
const selected = wanted.length
  ? MUTATIONS.filter((m) => wanted.includes(String(m.id)))
  : MUTATIONS;

if (wanted.length && selected.length !== wanted.length) {
  const missing = wanted.filter((w) => !MUTATIONS.some((m) => String(m.id) === w));
  console.error(`no such mutation id(s): ${missing.join(", ")}`);
  process.exit(2);
}

if (listOnly) {
  for (const m of selected) {
    const where = m.retired ? "(retired)" : `${m.pkg}/${m.file}`;
    console.log(`${String(m.id).padStart(3)}  ${where}\n     ${m.label}`);
  }
  process.exit(0);
}

/** Run the owning package's tests. Returns {failed, output}. */
function runTests(mutation) {
  const cwd = join(CLIENTS_DIR, mutation.pkg);
  const testArgs = ["vitest", "run", ...(mutation.tests ?? [])];
  try {
    const output = execFileSync("npx", testArgs, {
      cwd,
      encoding: "utf-8",
      stdio: ["ignore", "pipe", "pipe"],
      timeout: 300_000,
    });
    return { failed: false, output };
  } catch (err) {
    // A non-zero exit is the expected outcome here; capture whatever was printed either way.
    const output = `${err.stdout ?? ""}${err.stderr ?? ""}`;
    return { failed: true, output };
  }
}

function applyMutation(mutation) {
  const path = join(CLIENTS_DIR, mutation.pkg, mutation.file);
  const original = readFileSync(path, "utf-8");
  const occurrences = original.split(mutation.find).length - 1;
  if (occurrences !== 1) {
    throw new Error(
      `mutation ${mutation.id}: its \`find\` text matched ${occurrences} times in ${mutation.file} (expected exactly 1). The code moved — update the mutation, do not delete it.`,
    );
  }
  writeFileSync(path, original.replace(mutation.find, mutation.replace), "utf-8");
  return () => writeFileSync(path, original, "utf-8");
}

const results = [];
const retired = [];
for (const mutation of selected) {
  // A retired entry is kept, not deleted. It records that a fix was REMOVED because no mutation
  // of it could ever fail — which is a finding about the fix, and the one thing that must not
  // quietly vanish from the table.
  if (mutation.retired) {
    retired.push(mutation);
    console.log(`mutation ${String(mutation.id).padStart(3)}  ${mutation.label} … retired`);
    continue;
  }
  process.stdout.write(`mutation ${String(mutation.id).padStart(3)}  ${mutation.label} … `);
  let restore = null;
  try {
    restore = applyMutation(mutation);
    const { failed, output } = runTests(mutation);
    const expected = Array.isArray(mutation.expect) ? mutation.expect : [mutation.expect];
    const matched = expected.some((re) => re.test(output));
    const ok = failed && matched;
    results.push({ mutation, ok, failed, matched, output });
    console.log(ok ? "caught" : failed ? "FAILED FOR THE WRONG REASON" : "SURVIVED");
  } catch (err) {
    results.push({ mutation, ok: false, error: err.message });
    console.log(`ERROR — ${err.message}`);
  } finally {
    // Restoring is not optional: a mutation left applied poisons every later run and the tree.
    if (restore) restore();
  }
}

const escaped = results.filter((r) => !r.ok);
console.log(
  `\n${results.length - escaped.length}/${results.length} mutations caught` +
    (retired.length ? `, ${retired.length} retired` : ""),
);
for (const m of retired) {
  console.log(`\n─── ${m.id} RETIRED: ${m.label}`);
  console.log(
    m.retired
      .split("\n")
      .map((line) => `    ${line.trim()}`)
      .join("\n"),
  );
}
for (const r of escaped) {
  console.log(`\n─── ${r.mutation.id}: ${r.mutation.label}`);
  if (r.error) {
    console.log(`    harness error: ${r.error}`);
    continue;
  }
  console.log(
    r.failed
      ? `    the suite failed, but not with ${r.mutation.expect} — the failure is incidental, so the property is still unasserted`
      : "    the suite stayed GREEN. The property this fix exists for is not asserted by any test.",
  );
}
process.exit(escaped.length === 0 ? 0 : 1);

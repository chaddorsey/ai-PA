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
 *
 * ── WHAT ROUND 4 FOUND WRONG WITH THIS TOOL, AND WHAT CHANGED ──────────────────────────────
 *
 * 1. **`expect` was matched against the WHOLE vitest output.** Any failure anywhere in the same
 *    file could satisfy it, so four entries (8, 13, 22, 42) were "caught" by failures unrelated to
 *    the property they name — the precise "load-bearing ≠ property-bound" conflation this tool was
 *    built to eliminate, committed by the tool. It now runs vitest with `--reporter=json` and
 *    matches each `expect` against the NAMES OF THE TESTS THAT ACTUALLY FAILED. A mutation is
 *    caught only when a test whose name matches the regex is among them.
 * 2. **It mutated tracked source in place and restored only in a `finally`.** A Ctrl-C or a crash
 *    mid-run left reverted load-bearing source in the working tree, looking like a deliberate
 *    edit. Restore now also runs on SIGINT/SIGTERM/uncaught exception.
 * 3. **It did not check the tree was clean first.** Starting dirty means "restore" writes back
 *    whatever was there, silently merging the operator's uncommitted work into a mutation run. It
 *    now refuses to start unless the client packages are clean (`--allow-dirty` to override, which
 *    is for reading the table, not for trusting the result).
 */

import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { MUTATIONS } from "./mutations.mjs";

const CLIENTS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), "..");

const args = process.argv.slice(2);
const listOnly = args.includes("--list");
const allowDirty = args.includes("--allow-dirty");
/**
 * Also run mutations marked `live: true`, which need a real App Server on :4577.
 *
 * They are off by default so `node tools/mutate.mjs` stays deterministic and offline — but they
 * are REPORTED as deferred rather than silently omitted, because "not run" and "passed" must
 * never look the same in this tool of all tools.
 */
const runLive = args.includes("--live");
// Ids address entries, so two entries sharing one id makes `mutate.mjs 42` ambiguous and — worse
// — makes a whole entry unreachable by id while still being counted in the totals. Caught in
// practice: two new entries were appended as 42/43 when those ids already existed, and the only
// symptom was a selection error naming no ids at all.
const duplicateIds = [
  ...new Set(
    MUTATIONS.map((m) => String(m.id)).filter((id, i, all) => all.indexOf(id) !== i),
  ),
];
if (duplicateIds.length) {
  console.error(
    `mutations.mjs has duplicate id(s): ${duplicateIds.join(", ")}. Ids address entries; two entries cannot share one.`,
  );
  process.exit(2);
}

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

/**
 * Refuse to run against uncommitted work in the client packages.
 *
 * The tool edits tracked source and restores it from an in-memory copy. If the tree was already
 * dirty, "restored" means "back to your uncommitted state" for the file it touched and nothing at
 * all for the others — and if it dies mid-run, the operator cannot tell their own edits from a
 * mutation left behind. Scoped to `clients/` on purpose: this repo's tree is full of unrelated
 * untracked files and refusing on those would just teach everyone to pass --allow-dirty.
 */
function assertCleanTree() {
  let status;
  try {
    status = execFileSync("git", ["status", "--porcelain", "--", CLIENTS_DIR], {
      cwd: CLIENTS_DIR,
      encoding: "utf-8",
    }).trim();
  } catch (err) {
    console.error(`could not check the git tree: ${err.message}`);
    process.exit(2);
  }
  if (!status) return;
  console.error(
    `refusing to start: the client packages have uncommitted changes.\n\n${status}\n\n` +
      `This tool rewrites tracked source and restores it afterwards; starting dirty means a crash\n` +
      `leaves your edits and a mutation indistinguishable. Commit or stash first, or pass\n` +
      `--allow-dirty if you accept that the result cannot be trusted.`,
  );
  process.exit(2);
}

if (!allowDirty) assertCleanTree();

// ── restore safety net ───────────────────────────────────────────────────────
/** Set while a mutation is applied, so every exit path can put the file back. */
let pendingRestore = null;

function restoreNow() {
  if (!pendingRestore) return;
  const restore = pendingRestore;
  pendingRestore = null;
  restore();
}

for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) {
  process.on(signal, () => {
    restoreNow();
    console.error(`\n${signal} — mutated source restored.`);
    process.exit(130);
  });
}
process.on("uncaughtException", (err) => {
  restoreNow();
  console.error(`\nuncaught exception — mutated source restored.\n${err.stack ?? err}`);
  process.exit(1);
});

/**
 * Run the owning package's tests and report WHICH tests failed.
 *
 * Returns `{failed, failedTests, output}`. `failedTests` is the list of full test names that
 * actually failed — the thing an `expect` is matched against. Matching against `output` is what
 * let an unrelated failure in the same file satisfy an unrelated mutation.
 */
function runTests(mutation) {
  const cwd = join(CLIENTS_DIR, mutation.pkg);
  const reportDir = mkdtempSync(join(tmpdir(), "mutate-report-"));
  const reportPath = join(reportDir, "vitest.json");
  const testArgs = [
    "vitest",
    "run",
    "--reporter=json",
    `--outputFile=${reportPath}`,
    ...(mutation.tests ?? []),
  ];

  let output = "";
  let threw = false;
  try {
    output = execFileSync("npx", testArgs, {
      cwd,
      encoding: "utf-8",
      stdio: ["ignore", "pipe", "pipe"],
      timeout: 600_000,
      // `env` carries the opt-in switches a gate needs (LETTA_LIVE_WS=1 and friends).
      env: { ...process.env, ...(mutation.env ?? {}) },
    });
  } catch (err) {
    // A non-zero exit is the EXPECTED outcome here; capture whatever was printed either way.
    threw = true;
    output = `${err.stdout ?? ""}${err.stderr ?? ""}`;
  }

  let report = null;
  try {
    report = JSON.parse(readFileSync(reportPath, "utf-8"));
  } catch {
    // vitest died before writing a report (a syntax error from the mutation, a crashed worker).
    // That is a real outcome, not a caught mutation — `failedTests` stays empty and the entry is
    // reported as failing for the wrong reason rather than silently counted as a success.
    report = null;
  }
  rmSync(reportDir, { recursive: true, force: true });

  const failedTests = [];
  for (const file of report?.testResults ?? []) {
    for (const assertion of file.assertionResults ?? []) {
      if (assertion.status !== "failed") continue;
      const ancestry = (assertion.ancestorTitles ?? []).join(" > ");
      failedTests.push(assertion.fullName ?? `${ancestry} > ${assertion.title ?? ""}`);
    }
  }

  return { failed: threw, failedTests, sawReport: report !== null, output };
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
const deferred = [];
for (const mutation of selected) {
  if (mutation.live && !runLive) {
    deferred.push(mutation);
    console.log(
      `mutation ${String(mutation.id).padStart(3)}  ${mutation.label} … deferred (needs --live)`,
    );
    continue;
  }
  // A retired entry is kept, not deleted. It records that a fix was REMOVED because no mutation
  // of it could ever fail — which is a finding about the fix, and the one thing that must not
  // quietly vanish from the table.
  if (mutation.retired) {
    retired.push(mutation);
    console.log(`mutation ${String(mutation.id).padStart(3)}  ${mutation.label} … retired`);
    continue;
  }
  process.stdout.write(`mutation ${String(mutation.id).padStart(3)}  ${mutation.label} … `);
  try {
    pendingRestore = applyMutation(mutation);
    const { failed, failedTests, sawReport, output } = runTests(mutation);
    const expected = Array.isArray(mutation.expect) ? mutation.expect : [mutation.expect];
    // The whole correction: a named test that failed, not a substring of the console.
    const matchedBy = expected.flatMap((re) => failedTests.filter((name) => re.test(name)));
    const ok = failed && matchedBy.length > 0;
    results.push({ mutation, ok, failed, failedTests, matchedBy, sawReport, output });
    console.log(ok ? "caught" : failed ? "FAILED FOR THE WRONG REASON" : "SURVIVED");
  } catch (err) {
    results.push({ mutation, ok: false, error: err.message });
    console.log(`ERROR — ${err.message}`);
  } finally {
    // Restoring is not optional: a mutation left applied poisons every later run and the tree.
    restoreNow();
  }
}

const escaped = results.filter((r) => !r.ok);
console.log(
  `\n${results.length - escaped.length}/${results.length} mutations caught` +
    (retired.length ? `, ${retired.length} retired` : "") +
    (deferred.length ? `, ${deferred.length} deferred (--live)` : ""),
);
for (const m of deferred) {
  console.log(
    `\n─── ${m.id} DEFERRED: ${m.label}\n    Needs a real App Server. Re-run with --live once one is up:` +
      `\n      node tools/mutate.mjs --live ${m.id}`,
  );
}
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
  if (!r.failed) {
    console.log("    the suite stayed GREEN. The property this fix exists for is not asserted by any test.");
    continue;
  }
  if (!r.sawReport) {
    console.log(
      "    vitest produced no JSON report — it died before running tests (a syntax error from the",
    );
    console.log("    mutation, or a crashed worker). Nothing was proven; fix the mutation.");
    continue;
  }
  console.log(`    the suite failed, but NOT in the test this mutation names (${r.mutation.expect}).`);
  console.log("    The failure is incidental, so the property is still unasserted. What did fail:");
  for (const name of r.failedTests.slice(0, 10)) console.log(`      · ${name}`);
  if (r.failedTests.length > 10) console.log(`      … and ${r.failedTests.length - 10} more`);
  if (r.failedTests.length === 0) console.log("      (nothing — the run failed outside any test)");
}
process.exit(escaped.length === 0 ? 0 : 1);

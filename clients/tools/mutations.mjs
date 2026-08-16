/**
 * The mutation table.
 *
 * Each entry reverts ONE component of a landed fix and names the test that must fail when it
 * does. Ids 1-13 are the set recorded in docs/followups/2026-08-13-continuity-final-review-
 * findings.md §Round 3, every one of which used to leave the suite green. Ids 14+ cover the fixes
 * this round added, under the same rule: a fix without a failing mutation is not done.
 *
 * `find` must match its file EXACTLY ONCE. When a refactor moves the code, update the mutation —
 * deleting it is how a property quietly stops being asserted.
 */

const CORE = "letta-continuity-core";
const TERMINAL = "letta-terminal";
const CONTROLLER = "continuity-controller";

export const MUTATIONS = [
  // ── 1-13: the set that used to survive ─────────────────────────────────
  {
    id: 1,
    pkg: CORE,
    file: "src/index.ts",
    label: "approval deny: record the answer BEFORE the send (the pre-fix hang)",
    tests: ["test/core.properties.test.ts"],
    find: `          evictOldest(this.sentApprovalResponses, MAX_ANSWERED_APPROVALS);
          this.ws.send(buildApprovalDeny(responseId, this.runtime, id, APPROVAL_DENY_MESSAGE));`,
    replace: `          evictOldest(this.sentApprovalResponses, MAX_ANSWERED_APPROVALS);
          this.answeredApprovals.add(id);
          this.ws.send(buildApprovalDeny(responseId, this.runtime, id, APPROVAL_DENY_MESSAGE));`,
    expect: /a deny whose WRITE FAILED is answered again/,
  },
  {
    id: 2,
    pkg: CORE,
    file: "src/ownership.ts",
    label: "claim → run binding: FIFO becomes LIFO",
    tests: ["test/ownership.test.ts"],
    find: `    const index = this.claims.findIndex((c) => c.state === "armed");`,
    replace: `    const index = this.claims.map((c) => c.state).lastIndexOf("armed");`,
    expect: /claims bind to runs in SUBMISSION order/,
  },
  {
    id: "3a",
    pkg: CORE,
    file: "src/stream.ts",
    label: "fan-out: render listeners run in a bare loop",
    tests: ["test/core.properties.test.ts"],
    find: `    fanOut(this.listeners, [event]);`,
    replace: `    for (const l of this.listeners) l(event);`,
    expect: [/onRender survives a throwing listener/, /EPIPE from the render sink/],
  },
  {
    id: "3b",
    pkg: CORE,
    file: "src/connection.ts",
    label: "fan-out: connection-state listeners run in a bare loop",
    tests: ["test/core.properties.test.ts"],
    find: `    fanOut(this.listeners, [next, prev]);`,
    replace: `    for (const l of this.listeners) l(next, prev);`,
    expect: [/onConnectionState survives a throwing listener/, /EPIPE from the status sink/],
  },
  {
    id: "3c",
    pkg: CORE,
    file: "src/index.ts",
    label: "fan-out: error listeners run in a bare loop",
    tests: ["test/core.properties.test.ts"],
    find: `    fanOut(this.errorListeners, [err], (e) =>
      this.config.onWarn?.(\`error listener threw: \${e.message}\`),
    );`,
    replace: `    for (const l of this.errorListeners) l(err);`,
    expect: [/onError survives a throwing listener/, /EPIPE from the error sink/],
  },
  {
    id: "3d",
    pkg: CORE,
    file: "src/index.ts",
    label: "fan-out: approval listeners run in a bare loop",
    tests: ["test/core.properties.test.ts"],
    find: `    fanOut(this.approvalListeners, [event], (e) =>
      this.config.onWarn?.(\`approval listener threw: \${e.message}\`),
    );`,
    replace: `    for (const l of this.approvalListeners) l(event);`,
    expect: [/onApproval survives a throwing listener/, /EPIPE from the approval sink/],
  },
  {
    id: "3e",
    pkg: CORE,
    file: "src/index.ts",
    label: "fan-out: fatal listeners run in a bare loop",
    tests: ["test/core.properties.test.ts"],
    find: `    fanOut(this.fatalListeners, [err], (e) =>
      this.config.onWarn?.(\`fatal listener threw: \${e.message}\`),
    );`,
    replace: `    for (const l of this.fatalListeners) l(err);`,
    expect: [/onFatal survives a throwing listener/, /EPIPE from the fatal sink/],
  },
  {
    id: "3f",
    pkg: CORE,
    file: "src/ws.ts",
    label: "fan-out: WS frame listeners run in a bare loop",
    tests: ["test/ws.listeners.test.ts"],
    find: `    fanOut(this.frameListeners, [frame], (e) =>
      this.opts.onWarn(\`frame listener threw: \${e.message}\`),
    );`,
    replace: `    for (const l of this.frameListeners) l(frame);`,
    expect: [/a throwing frame listener/, /EPIPE from a frame listener/],
  },
  {
    id: "3g",
    pkg: CORE,
    file: "src/ws.ts",
    label: "fan-out: WS close listeners run in a bare loop",
    tests: ["test/ws.listeners.test.ts"],
    find: `    fanOut(this.closeListeners, [code, reason], (e) =>
      this.opts.onWarn(\`close listener threw: \${e.message}\`),
    );`,
    replace: `    for (const l of this.closeListeners) l(code, reason);`,
    expect: [/a throwing close listener/, /EPIPE from a close listener/],
  },
  {
    id: 4,
    pkg: CORE,
    file: "src/ownership.ts",
    label: "unknown queue disposition: park becomes drop-the-claim",
    tests: ["test/ownership.test.ts"],
    find: `        this.degraded = true;
        onAnomaly?.(
          \`unknown queue disposition`,
    replace: `        this.degraded = true;
        this.drop(claim);
        onAnomaly?.(
          \`unknown queue disposition`,
    expect: /an unrecognised queue disposition HOLDS the claim/,
  },
  {
    id: 5,
    pkg: CORE,
    file: "src/index.ts",
    label: "handleClose: identity guard reverts to reading the CURRENT connection",
    tests: ["test/core.properties.test.ts"],
    find: `    if (this.stopped || source !== this.ws || source.isClosedByUs) return;`,
    replace: `    if (this.stopped || this.ws?.isClosedByUs) return;`,
    expect: /a superseded connection's LATE close/,
  },
  {
    id: 6,
    pkg: CORE,
    file: "src/index.ts",
    label: "reconnect(): the superseded connection is leaked instead of closed",
    retired: `The guarded line is gone. reconnect() is reached only from handleClose (which fires
      for a socket that already went away) or from its own catch (which now closes the attempt it
      failed on), so \`previous\` was ALWAYS an already-closed connection: the extra close() could
      not be reached by any sequence, and this mutation duly survived. It was removed rather than
      kept as a guard no test can hold honest. The property it appeared to provide — a connection
      we have finished with stops delivering to consumers that moved on — is provided by
      WsConnection.close() detaching its listeners, which IS reachable and is mutation 22.`,
  },
  {
    id: 7,
    pkg: CORE,
    file: "src/index.ts",
    label: "openConnection(): the failed attempt's socket is not closed",
    tests: ["test/core.properties.test.ts"],
    find: `      ws.close();
      this.ws = null;`,
    replace: `      this.ws = null;`,
    expect: /a REJECTED start\(\) leaves no socket/,
  },
  {
    id: 8,
    pkg: TERMINAL,
    file: "src/session.ts",
    label: "session diagnostics go to the transcript sink instead of stderr",
    tests: ["test/session.test.ts"],
    find: `    this.writeErr = options.writeErr ?? options.write;`,
    replace: `    this.writeErr = options.write;`,
    expect: /diagnostics|stderr|transcript/,
  },
  {
    id: 9,
    pkg: CORE,
    file: "src/ownership.ts",
    label: "ownsAnyMessage ignores the origin it was asked about",
    tests: ["test/ownership.test.ts"],
    find: `        (c) => c.clientMessageId === id && (origin === undefined || c.origin === origin),`,
    replace: `        (c) => c.clientMessageId === id,`,
    expect: /ownsAnyMessage answers for the ASKING origin/,
  },
  {
    id: 10,
    pkg: CORE,
    file: "src/index.ts",
    label: "send(): the per-origin correlation nonce reverts to one per instance",
    tests: ["test/core.properties.test.ts"],
    find: `    const nonce = opts.origin ? \`\${this.clientNonce}-\${opts.origin}\` : this.clientNonce;`,
    replace: `    const nonce = this.clientNonce;`,
    expect: /the WIRE ids name the origin/,
  },
  {
    id: 11,
    pkg: CORE,
    file: "src/index.ts",
    label: "reconnect(): the already-answered approval set survives the seam",
    tests: ["test/core.integration.test.ts"],
    // REDIRECTED from `sentApprovalResponses` to `answeredApprovals`, deliberately. The original
    // mutation survived and always would have: `sentApprovalResponses` holds ids we minted, which
    // are unique for the life of the process, so a stale entry can never match a later ack —
    // clearing it on reconnect only bounded memory, and it is now bounded where it is written.
    // `answeredApprovals` is the one with a behavioural signature, and a sharp one: keeping it
    // across the seam suppresses the server's redelivery of a still-pending request, after which
    // nobody answers and the turn parks on every attached surface.
    find: `      this.answeredApprovals = new Set();`,
    replace: `      void 0;`,
    expect: /redelivered AFTER A RECONNECT is answered again/,
  },
  {
    id: 12,
    pkg: TERMINAL,
    file: "src/sanitize.ts",
    label: "sanitizer: the linear scanner reverts to a lazy-wildcard regex (quadratic)",
    tests: ["test/sanitize.test.ts"],
    find: `  out = stripStringSequences(out);`,
    replace: `  out = out.replace(
    new RegExp(\`\${ESC}[\\\\]P^_X][\\\\s\\\\S]*?(?:\${ESC}\\\\\\\\|\\\\u0007|\\\\u009c)\`, "g"),
    "",
  );`,
    expect: /bounds cost on unterminated/,
  },
  {
    id: 13,
    pkg: CORE,
    file: "src/connection.ts",
    label: "connected(): the budget is restored the instant a hello completes",
    tests: ["test/core.properties.test.ts", "test/connection.test.ts"],
    find: `    this.armStability();
    this.transition("connected");`,
    replace: `    this.attempts = 0;
    this.transition("connected");`,
    expect: /cannot rearm the reconnect budget|proven itself|stability window/,
  },

  // ── 14+: this round's fixes ─────────────────────────────────────────────
  {
    id: 14,
    pkg: CORE,
    file: "src/ownership.ts",
    label: "continuation runs are no longer inherited (the tool-using reply loses its origin)",
    tests: ["test/ownership.test.ts", "test/core.properties.test.ts"],
    find: `    const continued = this.soleActiveTurn();
    if (continued) {`,
    replace: `    const continued = null;
    if (continued) {`,
    expect: /inherits our attribution and origin|TOOL-USING reply is routed back/,
  },
  {
    id: 15,
    pkg: CORE,
    file: "src/ownership.ts",
    label: "onIdle no longer releases owned runs (inheritance runs away after a lost finish)",
    tests: ["test/ownership.test.ts"],
    find: `    for (const [id, run] of [...this.owned]) {
      if (!run.parked) this.owned.delete(id);
    }`,
    replace: `    void 0;`,
    expect: /a new run is a peer's and not a continuation/,
  },
  {
    id: 16,
    pkg: CORE,
    file: "src/ownership.ts",
    label: "turn_finished releases only the finishing run, not the whole turn",
    tests: ["test/ownership.test.ts"],
    find: `      for (const [id, run] of [...this.owned]) {
        if (run.requestId === entry.requestId) this.owned.delete(id);
      }`,
    replace: `      this.owned.delete(runId);`,
    expect: /releases the orphaned parent too/,
  },
  {
    id: 17,
    pkg: CORE,
    file: "src/ownership.ts",
    label: "the idle sweep ages claims from a shared clock again, so peer traffic shields them",
    tests: ["test/ownership.test.ts"],
    // Restores the single global `lastActivity` by having ANY run sighting — a peer's included —
    // count as progress for every outstanding claim of ours. That is what the shared field did,
    // and on a shared conversation it meant the reaper could never fire.
    find: `    if (this.seenRuns.has(runId)) return;
    this.remember(runId);`,
    replace: `    if (this.seenRuns.has(runId)) return;
    for (const c of this.claims) c.lastActivity = now;
    this.remember(runId);`,
    expect: /reaped even while PEER traffic|stranded claim is reaped/,
  },
  {
    id: 18,
    pkg: CORE,
    file: "src/ownership.ts",
    label: "a reconnect-demoted claim is terminal again (a later dequeue is refused)",
    tests: ["test/ownership.test.ts"],
    find: `      if (claim.state !== "queued" && claim.state !== "lost") {`,
    replace: `      if (claim.state !== "queued") {`,
    expect: /demoted by a reconnect is still resolvable/,
  },
  // ── 19a-19d: one entry per `start()` reset ─────────────────────────────
  //
  // This was ONE mutation reverting all four resets at once, with an `expect` bound only to the
  // watermark. So it was "caught" as long as the watermark test failed, and the other three
  // resets — including `answeredApprovals`, whose loss reproduces the nobody-answers hang on a
  // third path — were asserted by nothing at all. A mutation that reverts four components proves
  // one of them is load-bearing and says nothing about the rest.
  {
    id: "19a",
    pkg: CORE,
    file: "src/index.ts",
    label: "start() no longer resets the per-connection ordering watermark",
    tests: ["test/core.properties.test.ts"],
    find: `    this.assembler.reset();
    this.liveDedup = null;`,
    replace: `    this.liveDedup = null;`,
    expect: /stopped and started again renders the new session's stream/,
  },
  {
    id: "19b",
    pkg: CORE,
    file: "src/index.ts",
    label: "start() no longer drops the previous session's catch-up watermark",
    tests: ["test/core.properties.test.ts"],
    find: `    this.liveDedup = null;
    this.answeredApprovals = new Set();`,
    replace: `    this.answeredApprovals = new Set();`,
    expect: /does not filter live frames through the OLD snapshot/,
  },
  {
    id: "19c",
    pkg: CORE,
    file: "src/index.ts",
    label: "start() no longer forgets which approvals it answered (nobody-answers hang, 3rd path)",
    tests: ["test/core.properties.test.ts"],
    find: `    this.answeredApprovals = new Set();
    this.sentApprovalResponses = new Set();`,
    replace: `    this.sentApprovalResponses = new Set();`,
    expect: /ANSWERS an approval it already answered/,
  },
  {
    id: "19d",
    pkg: CORE,
    file: "src/index.ts",
    label: "start() no longer clears the ids of approval responses it minted",
    retired: `No mutation of this line can fail, by the codebase's own stated rule — and the rule is
      applied here rather than quietly excepted.

      \`reconnect()\` deliberately does NOT clear \`sentApprovalResponses\`, and says why at
      src/index.ts:700: the entries are request ids this process minted, unique for the life of
      the process, so a stale one can never match a later ack. Clearing it would only bound
      memory, and memory is bounded where the set is WRITTEN (evictOldest / MAX_ANSWERED_APPROVALS).

      Exactly the same argument applies to the copy in \`start()\`: a restart does not reset the
      id counter or the client nonce, so no id from the dead session can ever collide with one
      from the new session. The line is therefore unobservable, and a test written to catch its
      removal could only be a test of the line's existence.

      Kept rather than deleted because it costs nothing and reads as intentional alongside its
      three load-bearing neighbours; recorded here so that "19d has no test" is a decision on the
      record rather than a gap someone finds again in round 6. Same treatment as ids 6 and 21.`,
  },
  {
    id: 20,
    pkg: CORE,
    file: "src/index.ts",
    label: "a rejected start() leaves its queued reconnect running",
    tests: ["test/core.properties.test.ts"],
    find: `      if (this.reconnectTimer) {
        clearTimeout(this.reconnectTimer);
        this.reconnectTimer = null;
      }
      this.connectionState.disconnected();
      throw err;`,
    replace: `      this.connectionState.disconnected();
      throw err;`,
    expect: /DIES mid-hello does not leave a reconnect loop/,
  },
  {
    id: 21,
    pkg: CORE,
    file: "src/index.ts",
    label: "routeFrame accepts frames from a superseded connection",
    retired: `The guard is gone. It and mutation 22 (close() detaching its listeners) were two
      answers to one question — a superseded connection must not reach a consumer that moved on —
      and each masked the other: reverting either left the suite green because the survivor still
      covered the hazard. Two guards neither of which can be held honest are worse than one that
      can, so the consumer-side filter was removed and the lifecycle-side detach kept, since it
      protects every consumer (M1 Unit 6's web client included) rather than only this one.`,
  },
  {
    id: 22,
    pkg: CORE,
    file: "src/ws.ts",
    label: "close() leaves the frame listeners attached to a closing socket",
    tests: ["test/core.properties.test.ts", "test/ws.listeners.test.ts"],
    find: `    this.frameListeners.clear();
    this.errorListeners.clear();`,
    replace: `    void 0;`,
    expect: /SUPERSEDED|detaches|closing socket/,
  },
  {
    id: 23,
    pkg: CORE,
    file: "src/protocol.ts",
    label: "unrecognised frame types take part in the ordered stream again",
    tests: ["test/core.properties.test.ts"],
    find: `  if (!ORDERED_BROADCAST_TYPES.has(f.type)) return undefined;`,
    replace: `  void ORDERED_BROADCAST_TYPES;`,
    expect: /poisoned event_seq cannot latch the watermark/,
  },
  {
    id: 24,
    pkg: CORE,
    file: "src/ownership.ts",
    label: "the idle sweep also releases a run parked on an approval",
    tests: ["test/ownership.test.ts"],
    find: `      if (!run.parked) this.owned.delete(id);`,
    replace: `      this.owned.delete(id);`,
    expect: /parked on an approval survives the idle sweep/,
  },
  {
    id: 25,
    pkg: CORE,
    file: "src/index.ts",
    label: "a rejected input no longer names the send or the origin behind it",
    tests: ["test/core.properties.test.ts"],
    find: `            { requestId: frame.request_id, origin },`,
    replace: `            {},`,
    expect: /REJECTED input names the send and the origin/,
  },
  {
    id: 26,
    pkg: CORE,
    file: "src/index.ts",
    label: "conversation_create trusts the response shape again",
    tests: ["test/core.properties.test.ts"],
    find: `    if (typeof id !== "string" || id === "") {`,
    replace: `    if (false) {`,
    expect: /no usable id fails loudly/,
  },
  {
    id: 27,
    pkg: CORE,
    file: "src/index.ts",
    label: "conversation_list returns entries the wire never promised",
    tests: ["test/core.properties.test.ts"],
    find: `    return resp.conversations.filter((c): c is ConversationSummary => {`,
    replace: `    return resp.conversations.filter((_c): _c is ConversationSummary => {
      if (true) return true;`,
    expect: /entry with no id is dropped/,
  },

  // ── the terminal surface ────────────────────────────────────────────────
  {
    id: 28,
    pkg: TERMINAL,
    file: "src/main.ts",
    label: "--allow-remote is parsed and then not forwarded to the core",
    tests: ["test/main.test.ts"],
    find: `    allowRemote: options.allowRemote,`,
    replace: `    allowRemote: false,`,
    expect: /--allow-remote reaches the CORE/,
  },
  {
    id: 29,
    pkg: TERMINAL,
    file: "src/main.ts",
    label: "--json one-shot echoes the human `you ›` line onto the NDJSON stream",
    tests: ["test/main.test.ts"],
    find: `      if (!options.json) return session.handleInput(oneShotMessage);`,
    replace: `      return session.handleInput(oneShotMessage);`,
    expect: /NOTHING but parseable NDJSON/,
  },
  {
    id: 30,
    pkg: TERMINAL,
    file: "src/main.ts",
    label: "NDJSON drops the loop status a consumer needs to see the turn end",
    tests: ["test/main.test.ts"],
    find: `          status: e.status,`,
    replace: `          status: undefined,`,
    expect: /loop status a machine consumer needs/,
  },
  {
    id: 31,
    pkg: TERMINAL,
    file: "src/main.ts",
    label: "NDJSON emits raw C1 and DEL into the stream",
    tests: ["test/main.test.ts"],
    find: `  return \`\${JSON.stringify(value).replace(
    /[\\u007f-\\u009f]/g,
    (c) => \`\\\\u\${c.charCodeAt(0).toString(16).padStart(4, "0")}\`,
  )}\\n\`;`,
    replace: `  return \`\${JSON.stringify(value)}\\n\`;`,
    expect: /escapes C1 and DEL/,
  },
  {
    id: 32,
    pkg: TERMINAL,
    file: "src/main.ts",
    label: "the one-shot waits for ITS OWN run to finish (the pre-fix hang on tool use)",
    tests: ["test/main.test.ts"],
    find: `      if (
        sawOurTurn &&
        e.type === "loop_status" &&
        e.status === protocol.LoopStatuses.waitingOnInput
      ) {
        finish(0);
      }`,
    replace: `      if (sawOurTurn && e.type === "turn_finished" && core.ownsRun(e.runId)) {
        finish(0);
      }`,
    expect: /terminates on a TOOL-USING reply/,
  },
  {
    id: 33,
    pkg: TERMINAL,
    file: "src/main.ts",
    label: "a one-shot interrupted by a reconnect insists on a run it can still prove is ours",
    tests: ["test/main.test.ts"],
    find: `          core.ownsRun(e.runId) || (attributionLost && core.attributeRun(e.runId) !== "foreign");`,
    replace: `          core.ownsRun(e.runId);`,
    expect: /terminates when a reconnect lands in the middle/,
  },
  {
    id: 34,
    pkg: TERMINAL,
    file: "src/main.ts",
    label: "--write-pointer overwrites an existing pointer without keeping a copy",
    tests: ["test/main.test.ts"],
    find: `      await copyFile(options.writePointer, \`\${options.writePointer}.bak\`);`,
    replace: `      void 0;`,
    expect: /preserves what it replaced/,
  },
  {
    id: 35,
    pkg: TERMINAL,
    file: "src/cli.ts",
    label: "--timeout accepts a value that overflows the timer",
    tests: ["test/cli.test.ts"],
    find: `        if (parsed > MAX_TIMEOUT_SECONDS) {`,
    replace: `        if (false) {`,
    expect: /OVERFLOW the timer/,
  },
  {
    id: 36,
    pkg: TERMINAL,
    file: "src/render.ts",
    label: "a delta for a run we never saw start is labelled as our own",
    tests: ["test/session.test.ts"],
    find: `    const origin = (event.runId ? this.originByRun.get(event.runId) : undefined) ?? "unknown";`,
    replace: `    const origin = (event.runId ? this.originByRun.get(event.runId) : undefined) ?? "self";`,
    expect: /never saw START is hedged/,
  },
  {
    // ── 37a-37j: ONE introducer at a time ───────────────────────────────
    //
    // This was a single entry that emptied the whole 8-bit set, so it was satisfied as long as ANY
    // one of the five was covered — and only one was. Four of the five 8-bit introducers and
    // `ESC X` were individually unbound: dropping any of them left the suite green while a real
    // OSC-52 clipboard write or an APC payload went straight to the terminal.
    //
    // The sanitizer CODE is sound (fuzzed live, 200k control-heavy inputs, zero escapes). What was
    // wrong was the coverage, which is why these mutations remove members rather than rewriting
    // logic.
    id: "37a",
    pkg: TERMINAL,
    file: "src/sanitize.ts",
    label: "the scanner forgets the 8-bit DCS introducer (U+0090)",
    tests: ["test/sanitize.test.ts"],
    find: `const SEQ_INTRODUCERS_8BIT = "\\u0090\\u0098\\u009d\\u009e\\u009f";`,
    replace: `const SEQ_INTRODUCERS_8BIT = "\\u0098\\u009d\\u009e\\u009f";`,
    expect: /strips the 8-bit DCS \(U\+0090\)/,
  },
  {
    id: "37b",
    pkg: TERMINAL,
    file: "src/sanitize.ts",
    label: "the scanner forgets the 8-bit SOS introducer (U+0098)",
    tests: ["test/sanitize.test.ts"],
    find: `const SEQ_INTRODUCERS_8BIT = "\\u0090\\u0098\\u009d\\u009e\\u009f";`,
    replace: `const SEQ_INTRODUCERS_8BIT = "\\u0090\\u009d\\u009e\\u009f";`,
    expect: /strips the 8-bit SOS \(U\+0098\)/,
  },
  {
    id: "37c",
    pkg: TERMINAL,
    file: "src/sanitize.ts",
    label: "the scanner forgets the 8-bit OSC introducer (U+009D) — the clipboard one",
    tests: ["test/sanitize.test.ts"],
    find: `const SEQ_INTRODUCERS_8BIT = "\\u0090\\u0098\\u009d\\u009e\\u009f";`,
    replace: `const SEQ_INTRODUCERS_8BIT = "\\u0090\\u0098\\u009e\\u009f";`,
    expect: /strips the 8-bit OSC \(U\+009D\)/,
  },
  {
    id: "37d",
    pkg: TERMINAL,
    file: "src/sanitize.ts",
    label: "the scanner forgets the 8-bit PM introducer (U+009E)",
    tests: ["test/sanitize.test.ts"],
    find: `const SEQ_INTRODUCERS_8BIT = "\\u0090\\u0098\\u009d\\u009e\\u009f";`,
    replace: `const SEQ_INTRODUCERS_8BIT = "\\u0090\\u0098\\u009d\\u009f";`,
    expect: /strips the 8-bit PM \(U\+009E\)/,
  },
  {
    id: "37e",
    pkg: TERMINAL,
    file: "src/sanitize.ts",
    label: "the scanner forgets the 8-bit APC introducer (U+009F)",
    tests: ["test/sanitize.test.ts"],
    find: `const SEQ_INTRODUCERS_8BIT = "\\u0090\\u0098\\u009d\\u009e\\u009f";`,
    replace: `const SEQ_INTRODUCERS_8BIT = "\\u0090\\u0098\\u009d\\u009e";`,
    expect: /strips the 8-bit APC \(U\+009F\)/,
  },
  {
    id: "37f",
    pkg: TERMINAL,
    file: "src/sanitize.ts",
    label: "the scanner forgets the 7-bit OSC introducer (ESC ]) — clipboard and hyperlinks",
    tests: ["test/sanitize.test.ts"],
    find: `const SEQ_INTRODUCERS_7BIT = "]P^_X";`,
    replace: `const SEQ_INTRODUCERS_7BIT = "P^_X";`,
    expect: /strips the 7-bit OSC \(\]\)/,
  },
  {
    id: "37g",
    pkg: TERMINAL,
    file: "src/sanitize.ts",
    label: "the scanner forgets the 7-bit DCS introducer (ESC P)",
    tests: ["test/sanitize.test.ts"],
    find: `const SEQ_INTRODUCERS_7BIT = "]P^_X";`,
    replace: `const SEQ_INTRODUCERS_7BIT = "]^_X";`,
    expect: /strips the 7-bit DCS \(P\)/,
  },
  {
    id: "37h",
    pkg: TERMINAL,
    file: "src/sanitize.ts",
    label: "the scanner forgets the 7-bit PM introducer (ESC ^)",
    tests: ["test/sanitize.test.ts"],
    find: `const SEQ_INTRODUCERS_7BIT = "]P^_X";`,
    replace: `const SEQ_INTRODUCERS_7BIT = "]P_X";`,
    expect: /strips the 7-bit PM \(\^\)/,
  },
  {
    id: "37i",
    pkg: TERMINAL,
    file: "src/sanitize.ts",
    label: "the scanner forgets the 7-bit APC introducer (ESC _)",
    tests: ["test/sanitize.test.ts"],
    find: `const SEQ_INTRODUCERS_7BIT = "]P^_X";`,
    replace: `const SEQ_INTRODUCERS_7BIT = "]P^X";`,
    expect: /strips the 7-bit APC \(_\)/,
  },
  {
    id: "37j",
    pkg: TERMINAL,
    file: "src/sanitize.ts",
    label: "the scanner forgets the 7-bit SOS introducer (ESC X)",
    tests: ["test/sanitize.test.ts"],
    find: `const SEQ_INTRODUCERS_7BIT = "]P^_X";`,
    replace: `const SEQ_INTRODUCERS_7BIT = "]P^_";`,
    expect: /strips the 7-bit SOS \(X\)/,
  },
  {
    id: 38,
    pkg: TERMINAL,
    file: "src/sanitize.ts",
    label: "the invisible class loses the interlinear-annotation range",
    tests: ["test/sanitize.test.ts"],
    find: `    "[\\\\ufff9-\\\\ufffb]", // interlinear annotation: hides the annotated run`,
    replace: `    "[\\\\ufff9-\\\\ufff9]", // narrowed`,
    expect: /invisible characters that are not bidi/,
  },
  {
    id: 42,
    pkg: TERMINAL,
    file: "src/main.ts",
    label: "stdout/stderr writes are unguarded, so a closed pipe kills the process",
    tests: ["test/main.test.ts"],
    // Found LIVE, not offline: `--json | head -3` died with an unhandled EPIPE. The failure is
    // ASYNCHRONOUS — an `error` event on the socket after write() returned — so the listener
    // isolation that was supposed to cover this could not, and an array-backed test sink never
    // closes, never fills and never errors.
    // `find` updated when B3/B5 reshaped the onGone callback — the code moved, so the mutation
    // moved with it. Deleting it instead would have quietly retired the property.
    find: `    stdout: guardedWriter(process.stdout, (err) => {
      // EPIPE is \`head\`/\`less\` saying "enough" — not a failure, so it does not create one. Any
      // other error means the transcript genuinely could not be written, which does.
      if (err.code !== "EPIPE") process.exitCode = 1;
      process.exit(process.exitCode ?? 0);
    }),`,
    replace: `    stdout: (text: string) => {
      process.stdout.write(text);
    },`,
    expect: /consumer closing the pipe|EPIPE/,
  },
  {
    id: 43,
    pkg: TERMINAL,
    file: "src/main.ts",
    label: "the entry point exits outright instead of letting stdout flush",
    tests: ["test/main.test.ts"],
    find: `      process.exitCode = code;
      const bail = setTimeout(() => process.exit(code), 2000);`,
    replace: `      process.exit(code);
      const bail = setTimeout(() => process.exit(code), 2000);`,
    expect: /large stdout to a pipe rather than truncating/,
  },
  {
    id: 40,
    pkg: TERMINAL,
    file: "src/session.ts",
    label: "render-time notices are written into the transcript instead of to stderr",
    tests: ["test/session.test.ts"],
    // Found LIVE: `— subagents idle` sat between the echo and the reply on a piped one-shot's
    // stdout, after the offline suite had gone green. The routing existed for connection state and
    // errors but not for anything the RENDERER produced.
    find: `    if (out.transcript) this.write(out.transcript);
    if (out.notice) this.writeErr(out.notice);`,
    replace: `    if (out.transcript) this.write(out.transcript);
    if (out.notice) this.write(out.notice);`,
    expect: /subagent activity is chatter|queue indicator and an abnormal turn ending|peer's turn announcement is chatter/,
  },
  {
    id: 41,
    pkg: TERMINAL,
    file: "src/render.ts",
    label: "the newline closing an open transcript line is emitted as a notice",
    tests: ["test/session.test.ts"],
    find: `    return { transcript: this.closeStream(), notice: \`\${this.paint(\`— \${safe}\`, ...codes)}\\n\` };`,
    replace: `    return { transcript: "", notice: \`\${this.closeStream()}\${this.paint(\`— \${safe}\`, ...codes)}\\n\` };`,
    expect: /closes the transcript's line ON THE TRANSCRIPT|status line never lands mid-stream/,
  },
  {
    id: 39,
    pkg: TERMINAL,
    file: "src/sanitize.ts",
    label: "the invisible class loses the variation-selectors supplement",
    tests: ["test/sanitize.test.ts"],
    find: `    "[\\\\u{e0100}-\\\\u{e01ef}]",`,
    replace: `    "[\\\\u{e0200}-\\\\u{e0200}]",`,
    expect: /invisible characters that are not bidi/,
  },

  // ── 44-45: the DOUBLE is now under mutation too ────────────────────────
  //
  // `mockServer.ts` had no mutation of any kind, and it is a second transcription of the wire
  // vocabulary — so drifting the double's `tool_call_message` left the suite green (measured).
  // The double is test infrastructure, but it is the infrastructure every other assertion in
  // both packages is made against, so an unfalsifiable double makes 200 green tests worth less
  // than they look.
  //
  // The chain that makes the double trustworthy has TWO links, and they need separate mutations:
  //   45  the double agrees with protocol.ts   (offline, always runs)
  //   44  protocol.ts agrees with the SERVER   (live, needs a real App Server)
  // Neither alone is sufficient and neither can stand in for the other.
  {
    id: 44,
    pkg: CORE,
    file: "src/protocol.ts",
    label: "protocol.ts drifts a wire string away from the real server (live gate)",
    // The live contract test does NOT import the double — it speaks to a real App Server through
    // protocol.ts's builders. That is exactly why the mutation belongs HERE and not on
    // mockServer.ts: a mockServer mutation bound to `check:live` could never fail, because the
    // live test never loads the file. Drifting protocol.ts is what the live gate can actually see.
    tests: ["test/live.contract.test.ts"],
    live: true,
    env: { LETTA_LIVE_WS: "1" },
    find: `  conversationMessagesList: "conversation_messages_list",`,
    replace: `  conversationMessagesList: "conversation_messages_list_DRIFTED",`,
    expect: /round-trip the pinned frames/,
  },
  {
    id: 45,
    pkg: CORE,
    file: "test/helpers/mockServer.ts",
    label: "the double invents its own copy of a wire string again",
    tests: ["test/double-fidelity.test.ts"],
    find: `          message_type: DeltaMessageTypes.toolCall,`,
    replace: `          message_type: "tool_call_message",`,
    // Note the mutation restores a string that is still CORRECT today. That is the point: the
    // defect was never a wrong value, it was a value with no single home, so the next rename
    // could silently disagree. The gate fires on the un-sourced literal, not on its contents —
    // which is why the binding is the "sources the three strings it used to invent" assertion
    // and NOT "invents no wire vocabulary of its own": the latter compares against protocol.ts's
    // VALUES, and this value is still one of them. (The harness's new failing-test-id matching is
    // what surfaced the difference; against whole-output matching the two were indistinguishable.)
    expect: /sources the three strings it used to invent from protocol\.ts/,
  },

  // ── 46-51: the round-4 S1 set (root cause B) ───────────────────────────
  //
  // Every one of these was found by RUNNING THE BINARY, and none by the 287 in-process tests —
  // so four of the six are bound to tests that spawn the CLI. An array sink never closes, never
  // fills and never ends a process, so it cannot observe a hang, an exit code, or a closed pipe
  // no matter how the assertion is written.
  {
    id: 46,
    pkg: TERMINAL,
    file: "src/render.ts",
    label: "B1: the renderer drops error_message/loop_error again (the silent blackout)",
    tests: ["test/main.test.ts"],
    find: `        if (event.messageType && ERROR_DELTA_TYPES.has(event.messageType)) {
          return this.renderTurnError(event);
        }`,
    replace: `        if (false) {
          return this.renderTurnError(event);
        }`,
    expect: /is shown and exits nonzero/,
  },
  {
    id: 47,
    pkg: TERMINAL,
    file: "src/main.ts",
    label: "B1: a failed turn no longer reaches the EXIT CODE",
    tests: ["test/main.test.ts"],
    find: `    if (e.type === "delta" && e.messageType && protocol.ERROR_DELTA_TYPES.has(e.messageType)) {
      exitCode = 1;
    }`,
    replace: `    void e;`,
    expect: /is shown and exits nonzero/,
  },
  {
    id: 48,
    pkg: TERMINAL,
    file: "src/main.ts",
    label: "B2: headless attach hangs forever on an ended stdin",
    // Bound to a test that SPAWNS the CLI. In-process, a promise that never settles is
    // indistinguishable from a slow test, which is exactly how this shipped.
    tests: ["test/process.test.ts"],
    find: `        if (process.stdin.readableEnded) return resolve();`,
    replace: `        if (false) return resolve();`,
    expect: /exits instead of hanging when stdin is \/dev\/null/,
  },
  {
    id: 49,
    pkg: TERMINAL,
    file: "src/main.ts",
    label: "B3: a closed stdout launders a failing run into exit 0",
    tests: ["test/process.test.ts"],
    find: `      if (err.code !== "EPIPE") process.exitCode = 1;
      process.exit(process.exitCode ?? 0);`,
    replace: `      void err;
      process.exit(0);`,
    expect: /does not launder a failing run into exit 0/,
  },
  {
    id: 50,
    pkg: TERMINAL,
    file: "src/main.ts",
    label: "B4: the one-shot waits out its full timeout on a turn that ended in error",
    tests: ["test/main.test.ts"],
    find: `      if (sawOurTurn && e.type === "turn_finished" && e.stopReason === protocol.StopReasons.error) {
        finish(1);
        return;
      }`,
    replace: ``,
    expect: /exits promptly when it ends on turn_finished\{error\}/,
  },
  {
    id: 51,
    pkg: TERMINAL,
    file: "src/main.ts",
    label: "B5: guardedWriter rethrows a non-EPIPE fault out of an error listener",
    tests: ["test/main.test.ts"],
    find: `    gone = true;
    onGone(err);`,
    replace: `    if (err.code !== "EPIPE") throw err;
    gone = true;
    onGone(err);`,
    expect: /does not throw out of the error listener on a NON-EPIPE fault/,
  },

  // ── 52-55: the instrument-adjacent fixes (root cause C) ────────────────
  {
    id: 52,
    pkg: CORE,
    file: "src/connection.ts",
    label: "C2: the crash-loop guard is disabled by its own default",
    tests: ["test/core.properties.test.ts"],
    // The mutation the round-4 review ran by hand and watched survive. It survived because the
    // ONLY tests exercising the guard passed `connectionStabilityMs` explicitly; nothing ran the
    // shipped default, so a default of 0 — restore the budget the instant a hello completes — was
    // indistinguishable from a correct one.
    find: `    this.stabilityMs = opts.stabilityMs ?? DEFAULT_STABILITY_MS;`,
    replace: `    this.stabilityMs = opts.stabilityMs ?? 0;`,
    expect: /the crash-loop bound holds on the DEFAULT stability window/,
  },
  {
    id: 53,
    pkg: CORE,
    file: "src/connection.ts",
    label: "C2: stabilityMs is coupled back to the retry delay",
    tests: ["test/core.properties.test.ts"],
    // The original defect, not just its symptom: defaulting to maxDelayMs means a consumer tuning
    // `reconnectDelayMs` silently shrinks the crash-loop guard. Every test here sets it to 20ms.
    find: `    this.stabilityMs = opts.stabilityMs ?? DEFAULT_STABILITY_MS;`,
    replace: `    this.stabilityMs = opts.stabilityMs ?? this.maxDelayMs;`,
    expect: /the crash-loop bound holds on the DEFAULT stability window/,
  },
  {
    id: 54,
    pkg: CORE,
    file: "src/connection.ts",
    label: "C3: disconnected() no longer returns the budget",
    tests: ["test/core.properties.test.ts"],
    find: `  disconnected(): void {
    this.cancelStability();
    this.attempts = 0;`,
    replace: `  disconnected(): void {
    this.cancelStability();`,
    expect: /restarted after exhausting its budget gets a FRESH one/,
  },
  {
    id: 55,
    pkg: CORE,
    file: "src/index.ts",
    label: "C3: openConnection() orphans the incumbent socket instead of closing it",
    tests: ["test/core.properties.test.ts"],
    find: `    if (this.ws) {
      const previous = this.ws;
      this.ws = null;
      previous.close();
    }
    const ws = this.newConnection();`,
    replace: `    const ws = this.newConnection();`,
    expect: /does not leave the old socket wired/,
  },
  {
    id: 56,
    pkg: CORE,
    file: "src/protocol.ts",
    label: "C8: frameEventSeq lets a non-counter latch the ordering watermark",
    tests: ["test/protocol.contract.test.ts"],
    // C8 called this an equivalent mutant, and through the PIPELINE it is — validateInboundFrame
    // has already range-checked the same six types. It is bound rather than retired because
    // `frameEventSeq` is EXPORTED: its contract is owed to every caller, and the coupling that
    // makes it redundant today is invisible and one allowlist entry away from breaking.
    find: `  return isEventSeq(s) ? s : undefined;`,
    replace: `  return typeof s === "number" ? s : undefined;`,
    expect: /refuses a counter that is not a counter/,
  },
  {
    id: 57,
    pkg: CORE,
    file: "src/protocol.ts",
    label: "C8: frameEventSeq lets an UNORDERED frame type latch the watermark",
    tests: ["test/protocol.contract.test.ts"],
    find: `  if (!ORDERED_BROADCAST_TYPES.has(f.type)) return undefined;`,
    replace: ``,
    expect: /excludes frames that take no part in the ordered stream/,
  },

  // ── 58-63: injection paths and the Unit-6 seam (root causes D and E) ───
  {
    id: 58,
    pkg: TERMINAL,
    file: "src/main.ts",
    label: "D1: the arg-parse error path echoes argv to the terminal unsanitized",
    // A SPAWN test: argv only really is argv once it has crossed a shell.
    tests: ["test/process.test.ts"],
    find: `    io.stderr(
      \`\${sanitize(err instanceof CliError ? err.message : String(err), { maxLength: 512 })}\\n\`,
    );`,
    replace: `    io.stderr(\`\${err instanceof CliError ? err.message : String(err)}\\n\`);`,
    expect: /never echoes a control sequence back to the terminal from the arg-parse error path/,
  },
  {
    id: 59,
    pkg: TERMINAL,
    file: "src/main.ts",
    label: "D2: `conversations list` lets server text supply its own delimiters",
    tests: ["test/main.test.ts"],
    find: `  return sanitize(value, { maxLength }).replace(/[\\t\\n]+/g, " ");`,
    replace: `  return sanitize(value, { maxLength });`,
    expect: /emits ONE record per conversation even when the server supplies the delimiters/,
  },
  {
    id: 60,
    pkg: CORE,
    file: "src/index.ts",
    label: "E2: the loopback boundary is left to the transport the caller can replace",
    tests: ["test/trust.test.ts"],
    find: `    assertLoopbackUrl(url, this.config.allowRemote ?? false);`,
    replace: ``,
    expect: /refuses a non-loopback URL before the transport factory is called/,
  },
  {
    id: 61,
    pkg: CORE,
    file: "src/index.ts",
    label: "E3: the ConversationSummary predicate asserts six fields on the evidence of one",
    tests: ["test/core.properties.test.ts"],
    find: `  for (const field of ["id", "agent_id", "created_at", "updated_at"] as const) {`,
    replace: `  for (const field of ["id"] as const) {`,
    expect: /drops a NON-id field is caught and the field is named/,
  },
  {
    id: 62,
    pkg: TERMINAL,
    file: "src/main.ts",
    label: "E4: the --json bridge's origin map grows without bound again",
    tests: ["test/main.test.ts"],
    find: `      evictOldest(originByRun, MAX_TRACKED_ORIGINS);`,
    replace: ``,
    expect: /bounds its origin map, which a tool-using reply grows forever/,
  },
  {
    id: 63,
    pkg: TERMINAL,
    file: "src/main.ts",
    label: "E4: the --json send path re-implements what a line MEANS, and diverges",
    tests: ["test/main.test.ts"],
    find: `      const intent = classifyInput(oneShotMessage);
      if (intent.kind !== "send") return intent.kind;
      try {
        const handle = core.send(intent.text);
        io.stdout(ndjson({ kind: "sent", requestId: handle.requestId, text: intent.text }));`,
    replace: `      try {
        const handle = core.send(oneShotMessage);
        io.stdout(ndjson({ kind: "sent", requestId: handle.requestId, text: oneShotMessage }));`,
    expect: /reads a line the same way the human path does/,
  },
  // ── 64-72: Unit C3 — controller skeleton (plan 2026-08-15-006) ─────────────
  {
    id: 64,
    pkg: CORE,
    file: "src/ws.ts",
    label: "C3: connectBare skips the version gate (a bare socket attaches to a drifted server)",
    tests: ["test/ws.bare.test.ts"],
    find: `    this.lastIdentity = await this.assertIdentity();`,
    replace: `    this.lastIdentity = null;`,
    expect: /drifted server is REFUSED before any runtime exists/,
  },
  {
    id: 65,
    pkg: CORE,
    file: "test/helpers/mockServer.ts",
    label: "C3: the double regresses to one-runtime-per-socket (latest hello re-homes the connection)",
    tests: ["test/ws.bare.test.ts"],
    find: `    return [...this.conns].filter((c) =>
      c.runtimes.has(\`\${runtime.agent_id}:\${runtime.conversation_id}\`),
    );`,
    replace: `    return [...this.conns].filter(
      (c) =>
        c.runtime?.agent_id === runtime.agent_id &&
        c.runtime?.conversation_id === runtime.conversation_id,
    );`,
    expect: /receives broadcasts for the FIRST after a second hello/,
  },
  {
    id: 66,
    pkg: CONTROLLER,
    file: "src/hotset.ts",
    label: "C3: the worker's subscription stops being replay-complete (wait_for_replay dropped)",
    tests: ["test/hotset.test.ts"],
    find: `          if (options.waitForReplay) startOptions.waitForReplay = true;`,
    replace: ``,
    expect: /wait_for_replay for the worker/,
  },
  {
    id: 67,
    pkg: CONTROLLER,
    file: "src/worker.ts",
    label: "C3: a failed liveness probe still writes a fresh liveness file (watchdog blinded)",
    tests: ["test/worker.test.ts"],
    find: `      const detail = e instanceof Error ? e.message : String(e);
      this.opts.journal.append("liveness_probe_failed", { detail });
      this.loop.bounce(\`liveness probe failed: \${detail}\`);`,
    replace: `      void e;
      this.writeLiveness(this.opts.registry.hotRows().length);`,
    expect: /liveness probe MISS bounces the connection/,
  },
  {
    id: 68,
    pkg: CONTROLLER,
    file: "src/state/db.ts",
    label: "C3: a corrupt authority is rebuilt SILENTLY (degraded report suppressed)",
    tests: ["test/registry.test.ts"],
    find: `      degraded = \`\${degraded}; damaged db preserved at \${aside}; starting with a REBUILT (empty) authority\`;`,
    replace: `      degraded = null;`,
    expect: /corrupt db DEGRADES VISIBLY/,
  },
  {
    id: 69,
    pkg: CONTROLLER,
    file: "src/anchor.ts",
    label: "C3: the anchor sees the hotset_version bump and does nothing",
    tests: ["test/anchor.test.ts"],
    find: `    if (version === this.seenHotsetVersion) return;
    await this.subscribePass(conn);`,
    replace: `    if (version === this.seenHotsetVersion) return;`,
    expect: /follows a hotset_version bump within one poll/,
  },
  {
    id: 70,
    pkg: CONTROLLER,
    file: "src/registry.ts",
    label: "C3: the created-conversations-only rule vanishes (a `default` row severs reconciliation)",
    tests: ["test/registry.test.ts"],
    find: `    if (input.conversation_id === "default") {
      throw new RegistryError(
        "registry rows must reference CREATED conversations — the \`default\` alias is " +
          "unresolvable by conversation_messages_list (C1 S3), which would sever this thread " +
          "from transcript reconciliation",
      );
    }`,
    replace: ``,
    expect: /REFUSES a .default. conversation row/,
  },
  {
    id: 71,
    pkg: CONTROLLER,
    file: "src/connection-loop.ts",
    label: "C3: budget exhaustion becomes a silent unbounded retry (onExhausted never fires)",
    tests: ["test/connection-loop.test.ts"],
    find: `    if (!this.sm.dropped()) {
      this.opts.onExhausted();
      return;
    }`,
    replace: `    this.sm.dropped();`,
    expect: /reports exhaustion after the bounded budget/,
  },
  {
    id: 72,
    pkg: CONTROLLER,
    file: "src/worker.ts",
    label: "C3: a refused registry row is skipped without being marked or journaled",
    tests: ["test/worker.test.ts"],
    find: `          this.opts.registry.markBroken(b.runtime, b.reason);
          this.opts.journal.append("registry_row_broken", {
            runtime: b.runtime,
            reason: b.reason,
          });`,
    replace: ``,
    expect: /marked broken in the REGISTRY and journaled/,
  },
  // ── 73-81: Unit C4 — turn pipeline (plan 2026-08-15-006) ───────────────────
  {
    id: 73,
    pkg: CONTROLLER,
    file: "src/turns.ts",
    label: "C4: the durable `submitting` state vanishes (crash window becomes unreconcilable)",
    tests: ["test/turns.test.ts"],
    find: `    this.setState(row.client_message_id, "submitting", null);`,
    replace: ``,
    expect: /durably .submitting. BEFORE the ack returns/,
  },
  {
    id: 74,
    pkg: CONTROLLER,
    file: "src/journal.ts",
    label: "C4: journal dedup becomes best-effort (INSERT without OR IGNORE)",
    tests: ["test/journal.test.ts"],
    find: `        \`INSERT OR IGNORE INTO turn_events`,
    replace: `        \`INSERT INTO turn_events`,
    expect: /journals exactly once/,
  },
  {
    id: 75,
    pkg: CONTROLLER,
    file: "src/turns.ts",
    label: "C4: the wall-clock backstop stops sending abort (local skip instead of server kill)",
    tests: ["test/turns.test.ts"],
    find: `      if (!conn) throw new Error("no connection to abort on");
      await conn.request(
        (rid) => buildAbortMessage(rid, runtime),
        Outbound.abortMessage,
        this.opts.abortConfirmMs,
      );`,
    replace: `      if (!conn) throw new Error("no connection to abort on");`,
    expect: /timeout .*abort.*FAILED-VISIBLE.*NEXT queued message actually runs/,
  },
  {
    id: 76,
    pkg: CONTROLLER,
    file: "src/turns.ts",
    label: "C4: an UNCONFIRMED abort releases the queue anyway (server may still be running the turn)",
    tests: ["test/turns.test.ts"],
    find: `      this.opts.onWedged?.(runtime, detail);
      return;`,
    replace: `      this.opts.onWedged?.(runtime, detail);`,
    expect: /UNCONFIRMED abort holds the queue/,
  },
  {
    id: 77,
    pkg: CONTROLLER,
    file: "src/terminality.ts",
    label: "C4: requires_approval terminates the turn (every tool step would end it)",
    tests: ["test/terminality.test.ts"],
    find: `        if (delta.stop_reason === "requires_approval") return null; // continuation, not terminality`,
    replace: ``,
    expect: /requires_approval is a CONTINUATION/,
  },
  {
    id: 78,
    pkg: CONTROLLER,
    file: "src/terminality.ts",
    label: "C4: subagent deltas terminate the parent turn",
    tests: ["test/terminality.test.ts"],
    find: `      if (typeof frame.subagent_id === "string") return null; // subagent activity never terminates the parent`,
    replace: ``,
    expect: /subagent deltas never terminate/,
  },
  {
    id: 79,
    pkg: CONTROLLER,
    file: "src/terminality.ts",
    label: "C4: a run terminalizes twice (the late turn_finished latches the NEXT turn)",
    tests: ["test/terminality.test.ts"],
    find: `    if (this.terminalized.has(key)) return false;`,
    replace: ``,
    expect: /terminalizes AT MOST once/,
  },
  {
    id: 80,
    pkg: CONTROLLER,
    file: "src/turns.ts",
    label: "C4: journal generations become process-local again (restart reuses labels)",
    tests: ["test/turns.test.ts"],
    find: `    this.opts.db
      .prepare(
        \`INSERT INTO meta (key, value) VALUES ('journal_generation', '1')
         ON CONFLICT (key) DO UPDATE SET value = CAST(CAST(value AS INTEGER) + 1 AS TEXT)\`,
      )
      .run();
    const generationRow = this.opts.db
      .prepare("SELECT value FROM meta WHERE key = 'journal_generation'")
      .get() as { value: string };
    this.generation = Number.parseInt(generationRow.value, 10);`,
    replace: `    this.generation += 1;`,
    expect: /generations PERSIST across worker restarts/,
  },
  {
    id: 81,
    pkg: CONTROLLER,
    file: "src/turns.ts",
    label: "C4: a reconnect leaves the previous turn's wall-clock timer armed",
    tests: ["test/turns.test.ts"],
    find: `    // Stale actives die WITH their timers: a leftover wall-clock timer would fire against a
    // turn the coming recovery is about to reconcile, aborting or failing a row it no longer
    // owns.
    for (const [, turn] of this.active) if (turn.timer) clearTimeout(turn.timer);
    this.active.clear();`,
    replace: `    this.active.clear();`,
    expect: /KILLS the previous turn's wall-clock timer/,
  },
  // ── 82-87: Unit C5 — surface protocol + approvals (plan 2026-08-15-006) ─────
  {
    id: 82,
    pkg: CONTROLLER,
    file: "src/surface/auth.ts",
    label: "C5: the surface token check accepts anything",
    tests: ["test/surface.protocol.test.ts"],
    find: `  const a = Buffer.from(expected);
  const b = Buffer.from(presented);
  if (a.length !== b.length) return false;
  return timingSafeEqual(a, b);`,
    replace: `  void expected;
  void presented;
  return true;`,
    expect: /bad token .* clean denial/,
  },
  {
    id: 83,
    pkg: CONTROLLER,
    file: "src/journal.ts",
    label: "C5: replay ignores the cursor (every attach replays everything = duplicates)",
    tests: ["test/surface.protocol.test.ts"],
    find: `      .all(runtime.agent_id, runtime.conversation_id, cursor ?? 0, limit) as Array<`,
    replace: `      .all(runtime.agent_id, runtime.conversation_id, 0, limit) as Array<`,
    expect: /replay from a stale cursor is gapless and duplicate-free/,
  },
  {
    id: 84,
    pkg: CONTROLLER,
    file: "src/approvals.ts",
    label: "C5: an answered approval's unseen marker leaks forever",
    tests: ["test/approvals.test.ts"],
    find: `    this.opts.db.prepare("DELETE FROM unseen WHERE kind = 'approval' AND ref = ?").run(approvalId);`,
    replace: ``,
    expect: /delivered on the next capable attach/,
  },
  {
    id: 85,
    pkg: CONTROLLER,
    file: "src/surface/server.ts",
    label: "C5: approval requests fan out to EVERY surface, capability or not",
    tests: ["test/approvals.test.ts"],
    find: `    let reached = 0;
    for (const [, s] of this.sessions) {
      if (!s.capabilities.has("approvals")) continue;
      this.sendTo(s, {
        type: "approval_request",`,
    replace: `    let reached = 0;
    for (const [, s] of this.sessions) {
      this.sendTo(s, {
        type: "approval_request",`,
    expect: /first answer wins, second sees resolution, server acked ONCE/,
  },
  {
    id: 86,
    pkg: CONTROLLER,
    file: "src/approvals.ts",
    label: "C5: nobody-capable stops being held-pending (the approval quietly vanishes)",
    tests: ["test/approvals.test.ts"],
    find: `      this.opts.db
        .prepare(
          \`INSERT OR IGNORE INTO unseen (agent_id, conversation_id, kind, ref, created_at)
           VALUES (?, ?, 'approval', ?, ?)\`,
        )
        .run(runtime.agent_id, runtime.conversation_id, requestId, new Date().toISOString());`,
    replace: ``,
    expect: /HELD pending \+ unseen marker/,
  },
  {
    id: 87,
    pkg: CONTROLLER,
    file: "src/surface/server.ts",
    label: "C5: the surface protocol version gate vanishes (any client version attaches)",
    tests: ["test/surface.protocol.test.ts"],
    find: `        if (command.protocol_version !== SURFACE_PROTOCOL_VERSION) {
          socket.send(
            JSON.stringify({
              type: "attach_denied",
              reason: \`protocol_version \${command.protocol_version} unsupported (controller speaks \${SURFACE_PROTOCOL_VERSION})\`,
            }),
          );
          socket.close();
          return;
        }`,
    replace: ``,
    expect: /wrong protocol version .* denial naming both versions/,
  },
  // ── 88-91: Unit C6 — terminal on the controller (plan 2026-08-15-006) ───────
  {
    id: 88,
    pkg: TERMINAL,
    file: "src/cli.ts",
    label: "C6: a --url flag stops implying --direct (typed URL silently ignored)",
    tests: ["test/cli.test.ts"],
    find: `  if (urlFromFlag && opts.transport === "controller") opts.transport = "direct";`,
    replace: ``,
    expect: /implies the direct break-glass path/,
  },
  {
    id: 89,
    pkg: TERMINAL,
    file: "src/main.ts",
    label: "C6: the controller one-shot settles on ANY outcome, not its own receipt's",
    tests: ["test/controller.test.ts"],
    find: `        if (cm !== null && cm === myCm) {`,
    replace: `        if (cm !== null) {`,
    expect: /settles ONLY on its own receipt/,
  },
  {
    id: 90,
    pkg: TERMINAL,
    file: "src/main.ts",
    label: "C6: a FAILED-VISIBLE outcome exits 0 from the controller one-shot",
    tests: ["test/controller.test.ts"],
    find: `          finish(outcome.startsWith("FAILED") || outcome.startsWith("failed") ? 1 : 0);`,
    replace: `          finish(0);`,
    expect: /FAILED-VISIBLE turn renders as failure and exits nonzero/,
  },
  {
    id: 91,
    pkg: TERMINAL,
    file: "src/controller-core.ts",
    label: "C6: /deny quietly answers ALLOW (the operator's decision is rewritten)",
    tests: ["test/controller.test.ts"],
    find: `      JSON.stringify({ type: "approval_answer", approval_id: approvalId, decision: { behavior } }),`,
    replace: `      JSON.stringify({ type: "approval_answer", approval_id: approvalId, decision: { behavior: "allow" } }),`,
    expect: /answers a pending approval with DENY/,
  },
  {
    id: 92,
    pkg: TERMINAL,
    file: "src/main.ts",
    label: "C6: replayed HISTORICAL failures poison every future interactive exit",
    tests: ["test/controller.test.ts"],
    find: `      if (live && (outcome.startsWith("FAILED") || outcome.startsWith("failed"))) exitCode = 1;`,
    replace: `      if (outcome.startsWith("FAILED") || outcome.startsWith("failed")) exitCode = 1;`,
    expect: /REPLAYED historical failure does not/,
  },
  // ── 93-100: Unit C7 — agent-initiated delivery (plan 2026-08-15-006) ────────
  {
    id: 93,
    pkg: CONTROLLER,
    file: "src/routing/landing.ts",
    label: "C7: a missed tag silently falls through to the default thread",
    tests: ["test/routing.landing.test.ts"],
    find: `    // An explicit tag that matches nothing is a MISS, not a shrug: falling through to the
    // default thread would land the message somewhere the sender did not name.
    return null;`,
    replace: ``,
    expect: /tag that matches nothing is a MISS/,
  },
  {
    id: 94,
    pkg: CONTROLLER,
    file: "src/ingress/scheduler.ts",
    label: "C7: the ingress secret check accepts anything",
    tests: ["test/ingress.scheduler.test.ts"],
    find: `  const a = Buffer.from(expected);
  const b = Buffer.from(presented);
  if (a.length !== b.length) return false;
  return timingSafeEqual(a, b);`,
    replace: `  void expected;
  void presented;
  return true;`,
    expect: /wrong secret .* 401/,
  },
  {
    id: 95,
    pkg: CONTROLLER,
    file: "src/ingress/scheduler.ts",
    label: "C7: rejected ingress stops being journaled (invisible 401s)",
    tests: ["test/ingress.scheduler.test.ts"],
    find: `      this.opts.journal.record({
        runtime: { agent_id: agentId ?? "unknown", conversation_id: "ingress" },
        kind: "ingress_rejected",
        payload: { status, reason, path: req.url ?? "", method: req.method ?? "" },
      });`,
    replace: ``,
    expect: /401, JOURNALED/,
  },
  {
    id: 96,
    pkg: CONTROLLER,
    file: "src/routing/awareness.ts",
    label: "C7: nobody-attached arrivals leave no unseen marker (the 10:55 bug reborn)",
    tests: ["test/routing.awareness.test.ts"],
    find: `      this.opts.db
        .prepare(
          \`INSERT OR IGNORE INTO unseen (agent_id, conversation_id, kind, ref, created_at)
           VALUES (?, ?, 'turn', ?, ?)\`,
        )
        .run(runtime.agent_id, runtime.conversation_id, ref, new Date().toISOString());`,
    replace: ``,
    expect: /10:55 TEST/,
  },
  {
    id: 97,
    pkg: CONTROLLER,
    file: "src/surface/server.ts",
    label: "C7: attach presents unseen markers but never consumes them (badge forever)",
    tests: ["test/routing.awareness.test.ts"],
    find: `        if (unseen.length > 0) this.opts.awareness?.markSeen(command.runtime);`,
    replace: ``,
    expect: /10:55 TEST/,
  },
  {
    id: 98,
    pkg: CONTROLLER,
    file: "src/worker.ts",
    label: "C7: notify_operator stops riding the worker's hellos (no re-registration)",
    tests: ["test/routing.awareness.test.ts"],
    find: `          externalTools: [{ tools: [NOTIFY_OPERATOR_TOOL] }],`,
    replace: ``,
    expect: /hellos REGISTER notify_operator/,
  },
  {
    id: 99,
    pkg: CONTROLLER,
    file: "src/routing/awareness.ts",
    label: "C7: muted stops meaning muted (still broadcasts)",
    tests: ["test/routing.awareness.test.ts"],
    find: `    if (level === "muted") return;`,
    replace: ``,
    expect: /muted silences/,
  },
  {
    id: 100,
    pkg: CONTROLLER,
    file: "src/surface/server.ts",
    label: "C7: awareness frames fan out to every surface, notify capability or not",
    tests: ["test/routing.awareness.test.ts"],
    find: `      if (!s.capabilities.has("notify")) continue;
      if (s.presence === "gone") continue;`,
    replace: `      if (s.presence === "gone") continue;`,
    expect: /core-only surface gets nothing/,
  },
  // ── 101-107: Unit C8 — direct lane (plan 2026-08-15-006) ────────────────────
  {
    id: 101,
    pkg: CONTROLLER,
    file: "src/routing/routes.ts",
    label: "C8: a routing miss silently becomes a Kinara model call",
    tests: ["test/routing.routes.test.ts"],
    find: `      if (!route) throw new RouteMissError(\`no route named @\${alias}\`);`,
    replace: `      if (!route) return null;`,
    expect: /VISIBLE error and nothing is submitted/,
  },
  {
    id: 102,
    pkg: CONTROLLER,
    file: "src/routing/routes.ts",
    label: "C8: bind mutations stop being journaled (the R25 audit goes dark)",
    tests: ["test/routing.routes.test.ts"],
    find: `    this.journal.record({
      runtime: source,
      kind: "route_mutation",
      payload: { op: "bind", alias, author },
    });`,
    replace: ``,
    expect: /bind routes plain messages until unbind/,
  },
  {
    id: 103,
    pkg: CONTROLLER,
    file: "src/routing/routes.ts",
    label: "C8: an active binding starts beating an explicit @address",
    tests: ["test/routing.routes.test.ts"],
    find: `    const address = ADDRESS.exec(line);
    if (address) {`,
    replace: `    const bindingFirst = this.getBinding(source);
    if (bindingFirst) {
      return {
        target: {
          agent_id: bindingFirst.target_agent_id,
          conversation_id: bindingFirst.target_conversation_id,
        },
        text: line,
        via: "binding",
        alias: null,
      };
    }
    const address = ADDRESS.exec(line);
    if (address) {`,
    expect: /@address BEATS an active binding/,
  },
  {
    id: 104,
    pkg: CONTROLLER,
    file: "src/routing/digest.ts",
    label: "C8: digests jump ahead of pending operator messages",
    tests: ["test/routing.digest.test.ts"],
    find: `      if (pending.length > 0) continue;`,
    replace: ``,
    expect: /OPERATOR MESSAGES PREEMPT/,
  },
  {
    id: 105,
    pkg: CONTROLLER,
    file: "src/routing/digest.ts",
    label: "C8: delivered digests never marked — redelivered every sweep forever",
    tests: ["test/routing.digest.test.ts"],
    find: `        const mark = this.opts.db.prepare("UPDATE digests SET delivered_at = ? WHERE id = ?");
        for (const r of rows) mark.run(now, r.id);`,
    replace: ``,
    expect: /ROUTE-ORIGIN thread as ONE batched muted turn/,
  },
  {
    id: 106,
    pkg: CONTROLLER,
    file: "src/surface/server.ts",
    label: "C8: foreign-thread events fan out to every surface, capability or not",
    tests: ["test/routing.routes.test.ts"],
    find: `      if (key(s.runtime) !== key(origin.origin_runtime)) continue;
      if (!s.capabilities.has("direct")) continue;`,
    replace: `      if (key(s.runtime) !== key(origin.origin_runtime)) continue;`,
    expect: /ZERO Kinara turns, inline attributed reply/,
  },
  {
    id: 107,
    pkg: CONTROLLER,
    file: "src/turns.ts",
    label: "C8: the pump submits to runtimes the worker has not subscribed",
    tests: ["test/routing.routes.test.ts"],
    find: `      if (this.opts.isSubscribed && !this.opts.isSubscribed(runtime)) continue;`,
    replace: ``,
    expect: /ZERO Kinara turns, inline attributed reply/,
  },
];

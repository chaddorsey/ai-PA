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
    find: `    stdout: guardedWriter(process.stdout, () => process.exit(0)),`,
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
];

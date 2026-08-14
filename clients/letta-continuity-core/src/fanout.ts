/**
 * fanout.ts — one place for "call the consumer, survive the consumer".
 */
/**
 * Invoke consumer callbacks without letting one of them take the process down.
 *
 * Every fan-out below runs synchronously inside the ws socket's `message` handler, so a throw
 * escapes into an EventEmitter and becomes an uncaughtException — which Node's default policy
 * turns into exit. The terminal's listeners all end in `process.stdout.write`, so
 * `letta-continuity | head -40` killed the client on EPIPE instead of degrading. A misbehaving
 * consumer is a consumer problem; it must not be a connection problem.
 */
export function fanOut<A extends unknown[]>(
  listeners: Iterable<(...args: A) => void>,
  args: A,
  onListenerError?: (err: Error) => void,
): void {
  for (const l of listeners) {
    try {
      l(...args);
    } catch (err) {
      onListenerError?.(err instanceof Error ? err : new Error(String(err)));
    }
  }
}

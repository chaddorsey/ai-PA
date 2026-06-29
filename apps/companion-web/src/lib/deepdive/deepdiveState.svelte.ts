/**
 * deepdiveState.svelte.ts
 *
 * Reactive singleton tracking per-deep-dive read/listened/seen state.
 * Follows the AppState getter/setter rune pattern.
 */

function createDeepdiveState() {
  let seenIds = $state<Set<string>>(new Set());
  let readIds = $state<Set<string>>(new Set());
  let listenedIds = $state<Set<string>>(new Set());

  return {
    markSeen(id: string)     { seenIds = new Set([...seenIds, id]); },
    markRead(id: string)     { readIds = new Set([...readIds, id]); markSeen(id); },
    markListened(id: string) { listenedIds = new Set([...listenedIds, id]); markSeen(id); },

    isSeen(id: string)     { return seenIds.has(id); },
    isRead(id: string)     { return readIds.has(id); },
    isListened(id: string) { return listenedIds.has(id); },

    get seenIds()    { return seenIds; },
    get readIds()    { return readIds; },
    get listenedIds(){ return listenedIds; },

    // Reset (used in tests)
    reset() {
      seenIds    = new Set();
      readIds    = new Set();
      listenedIds = new Set();
    },
  };
}

export const deepdiveState = createDeepdiveState();

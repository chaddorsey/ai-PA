<script lang="ts">
  import { goto } from '$app/navigation';
  import type { DeepDive } from 'companion-core';
  import { appState } from '$lib/core/AppState.svelte';
  import { getOrchestrator } from '$lib/core/PlaybackOrchestrator';
  import { deepdiveState } from './deepdiveState.svelte';

  // ── Props ─────────────────────────────────────────────────────────────────────

  interface Props {
    deepdive: DeepDive;
    onDismiss: () => void;
  }

  let { deepdive, onDismiss }: Props = $props();

  // ── Auto-dismiss when train passes mile + 5 ────────────────────────────────

  $effect(() => {
    const pos = appState.position;
    if (pos && pos.mile > deepdive.mile + 5) {
      onDismiss();
    }
  });

  // ── Actions ────────────────────────────────────────────────────────────────

  async function handleListen() {
    if (!deepdive.audio) return;
    const orch = getOrchestrator();
    if (orch) {
      orch.silence(deepdive.mile + 5);
    }
    const { AudioSession } = await import('$lib/native/plugins');
    await AudioSession.play(deepdive.audio);
    deepdiveState.markListened(deepdive.id);
    onDismiss();
  }

  function handleRead() {
    deepdiveState.markRead(deepdive.id);
    // Navigate to Stories tab — the page will open the card automatically
    // via the pendingDeepDive in appState (or just navigate to stories for now).
    void goto('/stories');
    onDismiss();
  }

  function handleLater() {
    onDismiss();
  }
</script>

<!-- Slim banner that appears below the NowBar when a deep-dive is offered -->
<div class="dd-offer" role="alert" aria-live="polite" aria-label="Featured story offer">
  <div class="dd-offer__content">
    <span class="dd-offer__chip">{deepdive.theme}</span>
    <div class="dd-offer__text">
      <strong class="dd-offer__title">{deepdive.title}</strong>
      <span class="dd-offer__hook">{deepdive.hook}</span>
    </div>
  </div>
  <div class="dd-offer__actions">
    {#if deepdive.audio}
      <button
        class="dd-offer__btn dd-offer__btn--listen"
        onclick={handleListen}
        aria-label="Listen to {deepdive.title}"
      >
        🎧 Listen
      </button>
    {/if}
    <button
      class="dd-offer__btn dd-offer__btn--read"
      onclick={handleRead}
      aria-label="Read {deepdive.title}"
    >
      Read
    </button>
    <button
      class="dd-offer__btn dd-offer__btn--later"
      onclick={handleLater}
      aria-label="Dismiss story offer"
    >
      Later
    </button>
  </div>
</div>

<style>
  .dd-offer {
    background: #1a1a2e;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
    padding: 10px 14px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    flex-shrink: 0;
    animation: dd-offer-slide-in 0.2s ease-out;
  }

  @keyframes dd-offer-slide-in {
    from { transform: translateY(-100%); opacity: 0; }
    to   { transform: translateY(0);    opacity: 1; }
  }

  .dd-offer__content {
    display: flex;
    align-items: flex-start;
    gap: 10px;
  }

  .dd-offer__chip {
    font-size: 0.625rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #93c5fd;
    background: rgba(37, 99, 235, 0.25);
    border-radius: 8px;
    padding: 3px 8px;
    white-space: nowrap;
    flex-shrink: 0;
    margin-top: 2px;
  }

  .dd-offer__text {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .dd-offer__title {
    font-size: 0.9375rem;
    font-weight: 800;
    color: #fff;
    line-height: 1.2;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .dd-offer__hook {
    font-size: 0.75rem;
    color: #9ca3af;
    line-height: 1.4;
    /* 2-line clamp */
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    overflow: hidden;
  }

  .dd-offer__actions {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }

  .dd-offer__btn {
    border: none;
    border-radius: 8px;
    font-size: 0.875rem;
    font-weight: 700;
    font-family: inherit;
    cursor: pointer;
    padding: 7px 14px;
    transition: opacity 0.12s;
  }

  .dd-offer__btn:active { opacity: 0.8; }

  .dd-offer__btn--listen {
    background: #2563eb;
    color: #fff;
  }

  .dd-offer__btn--read {
    background: rgba(255, 255, 255, 0.12);
    color: #fff;
  }

  .dd-offer__btn--later {
    background: transparent;
    color: #9ca3af;
  }
</style>

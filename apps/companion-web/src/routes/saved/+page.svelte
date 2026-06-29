<script lang="ts">
  import { onMount } from 'svelte';
  import SavedList from '$lib/pillar3/SavedList.svelte';
  import { appState } from '$lib/core/AppState.svelte';
  import type { Favorite } from 'companion-core';

  let favorites = $state<Favorite[]>([]);

  // Load favorites from the in-memory adapter on mount,
  // and re-load whenever the user navigates back to this tab.
  onMount(async () => {
    favorites = await appState.favorites.list();
  });

  // Refresh when appState.favorites could have changed
  // (e.g., user captured a new item from NowBar or CompanionView)
  async function refreshFavorites() {
    favorites = await appState.favorites.list();
  }
</script>

<!--
  Saved tab — Browse ★ and Tell-me-more captures.
-->
<div class="saved-page">
  <SavedList {favorites} />
</div>

<style>
  .saved-page {
    height: 100%;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
</style>

<script lang="ts">
  import CompanionView from '$lib/pillar3/CompanionView.svelte';
</script>

<!--
  Companion tab — Pillar 3.
  Mounts the CompanionView which shows now-playing unit, playback controls,
  fill slider, theme filter, highlight toggle, and capture buttons.
-->
<div class="companion-page">
  <CompanionView />
</div>

<style>
  .companion-page {
    height: 100%;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
</style>

<script lang="ts">
  import SettingsView from '$lib/settings/SettingsView.svelte';
</script>

<!--
  Settings tab — voice rate, fill, themes, highlight-only, download manager, audio mode.
-->
<div class="settings-page">
  <SettingsView />
</div>

<style>
  .settings-page {
    height: 100%;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
</style>

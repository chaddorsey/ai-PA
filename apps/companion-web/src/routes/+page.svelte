<script lang="ts">
  import { onMount } from 'svelte';
  import { initBundle } from '$lib/core/bundleInit';

  let status = $state<string>('Loading...');

  onMount(async () => {
    const result = await initBundle('58');
    status = result.status === 'first-run' ? result.message : 'Bundle loaded';
  });
</script>

<h1>Amtrak Companion</h1>
<p>{status}</p>

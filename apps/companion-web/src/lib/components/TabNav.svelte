<script lang="ts">
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';

  const TABS = [
    { label: 'Trip', icon: '🗺', href: '/' },
    { label: 'Companion', icon: '🎧', href: '/companion' },
    { label: 'Saved', icon: '★', href: '/saved' },
    { label: 'Stories', icon: '📖', href: '/stories' },
    { label: 'Settings', icon: '⚙', href: '/settings' },
  ] as const;

  $: currentPath = $page.url.pathname;

  function isActive(href: string): boolean {
    if (href === '/') return currentPath === '/';
    return currentPath.startsWith(href);
  }

  function navigate(href: string) {
    void goto(href);
  }
</script>

<nav class="tab-nav" aria-label="Main navigation">
  {#each TABS as tab}
    <button
      class="tab-nav__item"
      class:tab-nav__item--active={isActive(tab.href)}
      on:click={() => navigate(tab.href)}
      aria-current={isActive(tab.href) ? 'page' : undefined}
      aria-label={tab.label}
    >
      <span class="tab-nav__icon" aria-hidden="true">{tab.icon}</span>
      <span class="tab-nav__label">{tab.label}</span>
    </button>
  {/each}
</nav>

<style>
  .tab-nav {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    display: flex;
    justify-content: space-around;
    align-items: center;
    background: #fff;
    border-top: 1px solid #e5e7eb;
    padding: 8px 0 max(8px, env(safe-area-inset-bottom));
    z-index: 100;
  }

  .tab-nav__item {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    flex: 1;
    background: none;
    border: none;
    cursor: pointer;
    padding: 6px 4px;
    color: #9ca3af;
    transition: color 0.15s;
  }

  .tab-nav__item--active {
    color: #2563eb;
  }

  .tab-nav__icon {
    font-size: 1.375rem;
    line-height: 1;
  }

  .tab-nav__label {
    font-size: 0.6875rem;
    font-weight: 600;
    letter-spacing: 0.02em;
  }
</style>

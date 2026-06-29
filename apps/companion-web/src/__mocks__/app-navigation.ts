import { vi } from 'vitest';

export const goto = vi.fn().mockResolvedValue(undefined);
export const beforeNavigate = vi.fn();
export const afterNavigate = vi.fn();

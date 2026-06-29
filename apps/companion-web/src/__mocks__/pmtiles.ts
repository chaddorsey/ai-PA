import { vi } from 'vitest';

export class Protocol {
  tile = vi.fn();
  add = vi.fn();
  remove = vi.fn();
}

export class PMTiles {
  constructor(_source: string) {}
}

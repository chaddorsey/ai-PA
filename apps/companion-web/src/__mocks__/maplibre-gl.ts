import { vi } from 'vitest';

// ── Marker mock ───────────────────────────────────────────────────────────────

export class Marker {
  _lngLat: [number, number] = [0, 0];
  _element: HTMLElement | undefined;
  _map: MapMock | null = null;
  private _clickHandler: (() => void) | null = null;

  constructor(opts?: { element?: HTMLElement }) {
    this._element = opts?.element;
    // Capture click handler if the element was provided
    if (this._element) {
      const orig = this._element.addEventListener.bind(this._element);
      this._element.addEventListener = (event: string, handler: EventListenerOrEventListenerObject) => {
        if (event === 'click') {
          this._clickHandler = handler as () => void;
        }
        orig(event, handler);
      };
    }
  }

  setLngLat(lngLat: [number, number]) {
    this._lngLat = lngLat;
    return this;
  }

  addTo(map: MapMock) {
    this._map = map;
    map._markers.push(this);
    return this;
  }

  remove() {
    if (this._map) {
      const idx = this._map._markers.indexOf(this);
      if (idx !== -1) this._map._markers.splice(idx, 1);
    }
    return this;
  }

  getLngLat() {
    return { lng: this._lngLat[0], lat: this._lngLat[1] };
  }

  /** For testing: simulate a click on this marker's element. */
  simulateClick() {
    if (this._element) {
      this._element.dispatchEvent(new Event('click'));
    }
  }
}

// ── Source mock ───────────────────────────────────────────────────────────────

class GeoJSONSourceMock {
  _data: unknown;
  constructor(data: unknown) { this._data = data; }
  setData(data: unknown) { this._data = data; }
}

// ── Map mock ──────────────────────────────────────────────────────────────────

export class MapMock {
  _sources: Map<string, unknown> = new Map();
  _layers: Map<string, unknown> = new Map();
  _bounds: unknown = null;
  _markers: Marker[] = [];
  _eventHandlers: Map<string, (() => void)[]> = new Map();
  _context: Map<string, unknown> = new Map();

  on(event: string, handler: () => void) {
    const handlers = this._eventHandlers.get(event) ?? [];
    handlers.push(handler);
    this._eventHandlers.set(event, handlers);
    // Auto-fire 'load' synchronously so tests don't need to trigger it
    if (event === 'load') handler();
    return this;
  }

  getSource(id: string) {
    return this._sources.get(id) ?? null;
  }

  addSource(id: string, spec: unknown) {
    const src = new GeoJSONSourceMock((spec as { data: unknown }).data);
    this._sources.set(id, src);
    return this;
  }

  addLayer(spec: { id: string } & Record<string, unknown>) {
    this._layers.set(spec.id, spec);
    return this;
  }

  getLayer(id: string) {
    return this._layers.get(id) ?? null;
  }

  removeLayer(id: string) {
    this._layers.delete(id);
    return this;
  }

  removeSource(id: string) {
    this._sources.delete(id);
    return this;
  }

  fitBounds(bounds: unknown) {
    this._bounds = bounds;
    return this;
  }

  easeTo(_opts: unknown) { return this; }

  remove() {}
}

// ── Protocol mock ─────────────────────────────────────────────────────────────

export const addProtocol = vi.fn();
export const removeProtocol = vi.fn();

// ── Default export (Map) ──────────────────────────────────────────────────────

const MaplibreGL = {
  Map: MapMock,
  Marker,
  addProtocol,
  removeProtocol,
};

export { MapMock as Map };
export default MaplibreGL;

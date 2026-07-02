export interface LegInfo { id: string; name: string; route: string; depDate: string; hasFeatures: boolean; }
export const AVAILABLE_LEGS: LegInfo[] = [
  { id: '3',  name: 'Southwest Chief',    route: 'Chicago → Los Angeles', depDate: '2026-07-06', hasFeatures: false },
  { id: '58', name: 'City of New Orleans', route: 'New Orleans → Chicago', depDate: '2026-07-11', hasFeatures: true  },
];
export const DEFAULT_LEG = '3';

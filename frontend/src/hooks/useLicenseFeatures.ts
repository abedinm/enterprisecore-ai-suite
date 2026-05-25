import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';

export type LicensePlan = 'evaluation' | 'core' | 'edu' | 'verticals' | string;

export type LicenseFeatures = {
  plan: LicensePlan;
  features: string[];
};

/** Fetches the active license plan + the feature set it unlocks. Cached for
 * the session via TanStack Query (5min staleTime). Used to gate nav items
 * and module pages. Treats absence of a feature as "hide" rather than an
 * error condition. */
export function useLicenseFeatures() {
  return useQuery<LicenseFeatures>({
    queryKey: ['license', 'features'],
    queryFn: () => api.get<LicenseFeatures>('/license/features').then((r) => r.data),
    staleTime: 5 * 60 * 1000,
  });
}

/** Convenience: returns true when the named feature is enabled by the active
 * license. Returns false while the query is still loading so we don't flash
 * gated UI before the plan has been resolved. */
export function useHasFeature(feature: string): boolean {
  const { data } = useLicenseFeatures();
  return data?.features.includes(feature) ?? false;
}

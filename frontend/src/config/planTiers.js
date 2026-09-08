// T043: Client-side plan tier configuration

// NOTE: values must match backend COMPLEXITY_TIER_VALUES exactly
// (backend/src/schemas.py): "simple" | "moderate" | "complex" | "frontier".
// "basic" is not a valid tier and previously caused every model to be
// filtered out of the Free tier (and Premium never included "frontier").
export const PLAN_TIERS = {
  free: {
    label: 'Free Tier',
    allowedComplexityTiers: ['simple']
  },
  standard: {
    label: 'Standard Tier',
    allowedComplexityTiers: ['simple', 'moderate']
  },
  premium: {
    label: 'Premium Tier',
    allowedComplexityTiers: ['simple', 'moderate', 'complex', 'frontier']
  }
};

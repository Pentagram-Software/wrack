// Base unit: 8px (MUI default)
// Usage: spacing[2] === 16px, spacing[4] === 32px
const BASE = 8;

export const spacing = Object.fromEntries(
  Array.from({ length: 25 }, (_, i) => [i, `${i * BASE}px`])
) as Record<number, string>;

// Named aliases for common values
export const spacingAliases = {
  none:   spacing[0],   // 0px
  xs:     spacing[1],   // 8px
  sm:     spacing[2],   // 16px
  md:     spacing[3],   // 24px
  lg:     spacing[4],   // 32px
  xl:     spacing[6],   // 48px
  xxl:    spacing[8],   // 64px
  xxxl:   spacing[12],  // 96px
} as const;

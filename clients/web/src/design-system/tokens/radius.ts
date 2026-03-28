// MD3 shape scale — border-radius values
export const radius = {
  none:   '0px',
  xs:     '4px',    // extra-small
  sm:     '8px',    // small
  md:     '12px',   // medium
  lg:     '16px',   // large
  xl:     '28px',   // extra-large
  full:   '9999px', // full / pill
} as const;

export type RadiusKey = keyof typeof radius;

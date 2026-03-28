// MD3 motion tokens — duration and easing functions
export const motion = {
  duration: {
    short1:  '50ms',
    short2:  '100ms',
    short3:  '150ms',
    short4:  '200ms',
    medium1: '250ms',
    medium2: '300ms',
    medium3: '350ms',
    medium4: '400ms',
    long1:   '450ms',
    long2:   '500ms',
    long3:   '550ms',
    long4:   '600ms',
    extraLong1: '700ms',
    extraLong2: '800ms',
    extraLong3: '900ms',
    extraLong4: '1000ms',
  },
  easing: {
    // MD3 standard easing curves
    standard:            'cubic-bezier(0.2, 0, 0, 1)',
    standardDecelerate:  'cubic-bezier(0, 0, 0, 1)',
    standardAccelerate:  'cubic-bezier(0.3, 0, 1, 1)',
    emphasized:          'cubic-bezier(0.2, 0, 0, 1)',
    emphasizedDecelerate:'cubic-bezier(0.05, 0.7, 0.1, 1)',
    emphasizedAccelerate:'cubic-bezier(0.3, 0, 0.8, 0.15)',
    legacy:              'cubic-bezier(0.4, 0, 0.2, 1)',
    legacyDecelerate:    'cubic-bezier(0, 0, 0.2, 1)',
    legacyAccelerate:    'cubic-bezier(0.4, 0, 1, 1)',
    linear:              'cubic-bezier(0, 0, 1, 1)',
  },
} as const;

export type MotionDuration = keyof typeof motion.duration;
export type MotionEasing = keyof typeof motion.easing;

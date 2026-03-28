#!/usr/bin/env tsx
/**
 * Token transformation script (PEN-104)
 * Reads Material Theme Builder JSON → generates TypeScript color token file.
 *
 * Usage: npm run tokens:transform
 */

import { readFileSync, writeFileSync, mkdirSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, '..');

const INPUT  = resolve(ROOT, 'src/design-system/tokens/exported/material-theme.json');
const OUTPUT = resolve(ROOT, 'src/design-system/tokens/colors.generated.ts');

interface MaterialTheme {
  description: string;
  seed: string;
  coreColors: Record<string, string>;
  schemes: Record<string, Record<string, string>>;
  palettes: Record<string, Record<string, string>>;
}

function toCamelCase(str: string): string {
  return str.replace(/-([a-z])/g, (_, c) => c.toUpperCase());
}

function schemeToTs(scheme: Record<string, string>): string {
  const entries = Object.entries(scheme)
    .map(([k, v]) => `  ${k}: '${v}',`)
    .join('\n');
  return `{\n${entries}\n}`;
}

function palettesToTs(palettes: Record<string, Record<string, string>>): string {
  const entries = Object.entries(palettes).map(([name, tones]) => {
    // Quote keys that contain hyphens or other non-identifier characters
    const key = /[^a-zA-Z0-9_$]/.test(name) ? `'${name}'` : name;
    const toneEntries = Object.entries(tones)
      .map(([t, v]) => `    '${t}': '${v}',`)
      .join('\n');
    return `  ${key}: {\n${toneEntries}\n  },`;
  });
  return `{\n${entries.join('\n')}\n}`;
}

const raw = readFileSync(INPUT, 'utf-8');
const theme: MaterialTheme = JSON.parse(raw);

const light = theme.schemes['light'];
const dark  = theme.schemes['dark'];

if (!light || !dark) {
  throw new Error('Missing light or dark scheme in material-theme.json');
}

const output = `// AUTO-GENERATED — do not edit by hand.
// Re-generate with: npm run tokens:transform
// Source: src/design-system/tokens/exported/material-theme.json

import type { ColorScheme, Palettes } from './types';

export const lightScheme: ColorScheme = ${schemeToTs(light)};

export const darkScheme: ColorScheme = ${schemeToTs(dark)};

export const palettes: Palettes = ${palettesToTs(theme.palettes)};

export const coreColors = ${JSON.stringify(theme.coreColors, null, 2)} as const;
`;

mkdirSync(dirname(OUTPUT), { recursive: true });
writeFileSync(OUTPUT, output, 'utf-8');
console.log(`✅  Generated: ${OUTPUT.replace(ROOT, '.')}`);

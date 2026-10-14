/**
 * WCAG AA contrast regression tests for the dark, light and print palettes.
 *
 * Reads the real stylesheet via Vite's `?raw` import and extracts token
 * values from:
 *   - the dark `:root` block (first occurrence of each custom property),
 *   - the `[data-theme='light']` block (first ` }`-terminated slice),
 *   - the `@media print` block (slice from its at-rule).
 *
 * Asserts measured contrast ratios against the surfaces each token is
 * actually used on (grep-verified in src): panels, page, inputs, raised
 * controls and hover rows — plus the light-only `midnight-600` hover surface
 * for the two tokens that render on it (slateui-100 in .btn-secondary,
 * slateui-300 in the Settings selected tab).
 *
 * Also parses the `.input` component rule (and its light-theme override) to
 * verify form-control boundaries under WCAG 1.4.11 (3:1) in both themes.
 *
 * The light `.input` override must stay declared BEFORE the shared `.input`
 * rule so the later `.input:hover` / `.input:focus` rules (equal specificity)
 * keep winning on interaction — an order guard test enforces this.
 */
import { describe, expect, it } from 'vitest';
import css from '../styles/index.css?raw';

/* ---------- WCAG 2.x math ---------- */

function channelLuminance(c: number): number {
  const s = c / 255;
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

function relativeLuminance([r, g, b]: [number, number, number]): number {
  return 0.2126 * channelLuminance(r) + 0.7152 * channelLuminance(g) + 0.0722 * channelLuminance(b);
}

function contrast(a: [number, number, number], b: [number, number, number]): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

/** CSS `rgb(var(--x) / 0.7)` compositing over an opaque background. */
function composite(
  fg: [number, number, number],
  alpha: number,
  bg: [number, number, number],
): [number, number, number] {
  return fg.map((f, i) => Math.round(alpha * f + (1 - alpha) * bg[i])) as [number, number, number];
}

/* ---------- token extraction (dark :root block = first occurrence) ---------- */

type Rgb = [number, number, number];

function rgbToken(name: string): Rgb {
  const m = css.match(new RegExp(`--tm-${name}:\\s*(\\d+)\\s+(\\d+)\\s+(\\d+)`));
  if (!m) throw new Error(`token --tm-${name} not found`);
  return [Number(m[1]), Number(m[2]), Number(m[3])];
}

function alphaToken(name: string): number {
  const m = css.match(new RegExp(`--tm-${name}:\\s*([\\d.]+)`));
  if (!m) throw new Error(`token --tm-${name} not found`);
  return Number(m[1]);
}

/** Token values from the `@media print` block (defined after `:root`). */
function printRgbToken(name: string): Rgb {
  const printCss = css.slice(css.indexOf('@media print'));
  const m = printCss.match(new RegExp(`--tm-${name}:\\s*(\\d+)\\s+(\\d+)\\s+(\\d+)`));
  if (!m) throw new Error(`print token --tm-${name} not found`);
  return [Number(m[1]), Number(m[2]), Number(m[3])];
}

/* ---------- light theme extraction ([data-theme='light'] block) ---------- */

/** The light block slice — ` }`-terminated, no nested braces. */
function lightBlockCss(): string {
  // Must match the selector with its opening brace: an earlier source comment
  // mentions `[data-theme='light']` without one.
  const start = css.indexOf("[data-theme='light'] {");
  if (start < 0) throw new Error('light theme block not found');
  const end = css.indexOf('}', start);
  if (end < 0) throw new Error('light theme block not terminated');
  return css.slice(start, end);
}

function lightRgbToken(name: string): Rgb {
  const m = lightBlockCss().match(new RegExp(`--tm-${name}:\\s*(\\d+)\\s+(\\d+)\\s+(\\d+)`));
  if (!m) throw new Error(`light token --tm-${name} not found`);
  return [Number(m[1]), Number(m[2]), Number(m[3])];
}

function lightAlphaToken(name: string): number {
  const m = lightBlockCss().match(new RegExp(`--tm-${name}:\\s*([\\d.]+)`));
  if (!m) throw new Error(`light token --tm-${name} not found`);
  return Number(m[1]);
}

/* ---------- surfaces & text tokens ---------- */

const darkSurfaces: Record<string, Rgb> = {
  'page (midnight-950)': rgbToken('midnight-950'),
  'inputs/sidebar (midnight-900)': rgbToken('midnight-900'),
  'subtle panels (midnight-850)': rgbToken('midnight-850'),
  'panels (midnight-800)': rgbToken('midnight-800'),
  'raised controls / hover rows (midnight-700)': rgbToken('midnight-700'),
};

const textTokens: Record<string, Rgb> = {
  'slateui-100': rgbToken('slateui-100'),
  'slateui-200': rgbToken('slateui-200'),
  'slateui-300': rgbToken('slateui-300'),
  'slateui-400': rgbToken('slateui-400'),
  'slateui-500': rgbToken('slateui-500'),
};

const lightSurfaces: Record<string, Rgb> = {
  'page (midnight-950)': lightRgbToken('midnight-950'),
  'inputs / white panels (midnight-900)': lightRgbToken('midnight-900'),
  'subtle panels (midnight-850)': lightRgbToken('midnight-850'),
  'panels (midnight-800)': lightRgbToken('midnight-800'),
  'raised controls / hover rows (midnight-700)': lightRgbToken('midnight-700'),
};

/** Light-only darkest hover surface — hosts slateui-100 and slateui-300 only. */
const lightHoverSurface = lightRgbToken('midnight-600');

const lightTextTokens: Record<string, Rgb> = {
  'slateui-100': lightRgbToken('slateui-100'),
  'slateui-200': lightRgbToken('slateui-200'),
  'slateui-300': lightRgbToken('slateui-300'),
  'slateui-400': lightRgbToken('slateui-400'),
  'slateui-500': lightRgbToken('slateui-500'),
};

/* ---------- `.input` component rule extraction ---------- */

/** Shared `.input` rule body (applies in both themes) — matched via its @apply. */
const sharedInputRule = (() => {
  const idx = css.search(/\.input \{\s*@apply/);
  if (idx < 0) throw new Error('.input @apply rule not found');
  const end = css.indexOf('}', idx);
  if (end < 0) throw new Error('.input @apply rule not terminated');
  return css.slice(idx, end + 1);
})();

function borderSpec(pattern: RegExp): { tokenId: string; alpha: number } {
  const m = sharedInputRule.match(pattern);
  if (!m) throw new Error(`border spec not found: ${pattern.source}`);
  return { tokenId: m[1], alpha: m[2] === undefined ? 1 : Number(m[2]) / 100 };
}

const sharedBaseBorder = borderSpec(/border-slateui-(\d+)\/(\d+)/);
const sharedHoverBorder = borderSpec(/hover:border-slateui-(\d+)\/(\d+)/);
const sharedFocusBorder = borderSpec(/focus:border-violetui-(\d+)/);

/** Light-scoped base border override: `[data-theme='light'] .input { … }`. */
const lightBaseBorder = (() => {
  const m = css.match(
    /\[data-theme='light'\] \.input \{\s*border-color: rgb\(var\(--tm-slateui-(\d+)\) \/ ([\d.]+)\);/,
  );
  if (!m) throw new Error('light .input border override not found');
  return { tokenId: m[1], alpha: Number(m[2]) };
})();

/* ---------- dark theme tests ---------- */

describe('dark theme text tokens meet WCAG AA (4.5:1)', () => {
  for (const [tokenName, fg] of Object.entries(textTokens)) {
    for (const [surfaceName, bg] of Object.entries(darkSurfaces)) {
      it(`${tokenName} on ${surfaceName}`, () => {
        expect(contrast(fg, bg)).toBeGreaterThanOrEqual(4.5);
      });
    }
  }
});

describe('dark theme ramp keeps its lightness hierarchy', () => {
  it('slateui-100 > 200 > 300 > 400 > 500 by luminance', () => {
    const lums = Object.values(textTokens).map(relativeLuminance);
    for (let i = 0; i < lums.length - 1; i++) {
      expect(lums[i]).toBeGreaterThan(lums[i + 1]);
    }
  });
});

describe('dark theme chart axis labels (small text on panels)', () => {
  it('--tm-chart-axis meets 4.5:1 on the panel surface', () => {
    expect(contrast(rgbToken('chart-axis'), darkSurfaces['panels (midnight-800)'])).toBeGreaterThanOrEqual(4.5);
  });
});

describe('dark theme focus indicator (WCAG 1.4.11, 3:1)', () => {
  const ring = rgbToken('focus-ring');
  const alpha = alphaToken('focus-ring-alpha');

  for (const [surfaceName, bg] of Object.entries(darkSurfaces)) {
    it(`composited focus ring vs ${surfaceName}`, () => {
      expect(contrast(composite(ring, alpha, bg), bg)).toBeGreaterThanOrEqual(3);
    });
  }
});

describe('dark theme input placeholder text', () => {
  it('slateui-400 placeholder on input background meets 4.5:1', () => {
    expect(contrast(textTokens['slateui-400'], darkSurfaces['inputs/sidebar (midnight-900)'])).toBeGreaterThanOrEqual(4.5);
  });
});

/* ---------- light theme tests ---------- */

describe('light theme text tokens meet WCAG AA (4.5:1)', () => {
  // midnight-600 (darker than 700) is deliberately not in this grid: grep shows
  // slateui-400/500 never render on it — btn-ghost hovers use midnight-700.
  for (const [tokenName, fg] of Object.entries(lightTextTokens)) {
    for (const [surfaceName, bg] of Object.entries(lightSurfaces)) {
      it(`${tokenName} on ${surfaceName}`, () => {
        expect(contrast(fg, bg)).toBeGreaterThanOrEqual(4.5);
      });
    }
  }
});

describe('light theme text on the darkest hover surface (midnight-600)', () => {
  // bg-midnight-600 hosts exactly two text tokens (grep-verified):
  // slateui-100 in .btn-secondary hover, slateui-300 in the Settings
  // selected-tab hover (which also hovers to midnight-600).
  it('slateui-100 (.btn-secondary hover) meets 4.5:1', () => {
    expect(contrast(lightTextTokens['slateui-100'], lightHoverSurface)).toBeGreaterThanOrEqual(4.5);
  });

  it('slateui-300 (Settings selected-tab hover) meets 4.5:1', () => {
    expect(contrast(lightTextTokens['slateui-300'], lightHoverSurface)).toBeGreaterThanOrEqual(4.5);
  });
});

describe('light theme ramp keeps its lightness hierarchy', () => {
  // Light theme inverts value, not meaning: 100 is the strongest (darkest)
  // text, 500 the dimmest — luminance must strictly increase along the ramp.
  it('slateui-100 < 200 < 300 < 400 < 500 by luminance', () => {
    const lums = Object.values(lightTextTokens).map(relativeLuminance);
    for (let i = 0; i < lums.length - 1; i++) {
      expect(lums[i]).toBeLessThan(lums[i + 1]);
    }
  });

  // Guards against adjacent steps collapsing into each other (the failure mode
  // of near-identical candidate values like 97 107 131 vs 97 106 134).
  const ramp = ['slateui-100', 'slateui-200', 'slateui-300', 'slateui-400', 'slateui-500'];
  for (let i = 0; i < ramp.length - 1; i++) {
    it(`${ramp[i]} stays visually distinct from ${ramp[i + 1]} (≥1.15:1)`, () => {
      expect(contrast(lightTextTokens[ramp[i]], lightTextTokens[ramp[i + 1]])).toBeGreaterThanOrEqual(1.15);
    });
  }
});

describe('light theme chart axis labels (small text on panels)', () => {
  it('--tm-chart-axis stays synced with slateui-400', () => {
    expect(lightRgbToken('chart-axis')).toEqual(lightRgbToken('slateui-400'));
  });

  it('--tm-chart-axis meets 4.5:1 on the panel surface', () => {
    expect(contrast(lightRgbToken('chart-axis'), lightSurfaces['panels (midnight-800)'])).toBeGreaterThanOrEqual(4.5);
  });
});

describe('light theme focus indicator (WCAG 1.4.11, 3:1)', () => {
  const ring = lightRgbToken('focus-ring');
  const alpha = lightAlphaToken('focus-ring-alpha');

  for (const [surfaceName, bg] of Object.entries(lightSurfaces)) {
    it(`composited focus ring vs ${surfaceName}`, () => {
      expect(contrast(composite(ring, alpha, bg), bg)).toBeGreaterThanOrEqual(3);
    });
  }

  it('composited focus ring vs hover surface (midnight-600)', () => {
    expect(contrast(composite(ring, alpha, lightHoverSurface), lightHoverSurface)).toBeGreaterThanOrEqual(3);
  });
});

/* ---------- input boundaries (WCAG 1.4.11, 3:1) ---------- */

describe('dark theme input boundaries (WCAG 1.4.11, 3:1)', () => {
  const inputBg = darkSurfaces['inputs/sidebar (midnight-900)'];
  const pageBg = darkSurfaces['page (midnight-950)'];

  it('base border meets 3:1 vs input background and page', () => {
    const c = composite(rgbToken(`slateui-${sharedBaseBorder.tokenId}`), sharedBaseBorder.alpha, inputBg);
    expect(contrast(c, inputBg)).toBeGreaterThanOrEqual(3);
    expect(contrast(c, pageBg)).toBeGreaterThanOrEqual(3);
  });

  it('hover border meets 3:1 and is stronger than the base border', () => {
    const base = composite(rgbToken(`slateui-${sharedBaseBorder.tokenId}`), sharedBaseBorder.alpha, inputBg);
    const c = composite(rgbToken(`slateui-${sharedHoverBorder.tokenId}`), sharedHoverBorder.alpha, inputBg);
    expect(contrast(c, inputBg)).toBeGreaterThanOrEqual(3);
    expect(contrast(c, pageBg)).toBeGreaterThanOrEqual(3);
    // Dark theme: brighter border = stronger state.
    expect(relativeLuminance(c)).toBeGreaterThan(relativeLuminance(base));
  });

  it('focus border (violetui-500) meets 3:1 vs input background and page', () => {
    const c = rgbToken(`violetui-${sharedFocusBorder.tokenId}`);
    expect(contrast(c, inputBg)).toBeGreaterThanOrEqual(3);
    expect(contrast(c, pageBg)).toBeGreaterThanOrEqual(3);
  });
});

describe('light theme input boundaries (WCAG 1.4.11, 3:1)', () => {
  const inputBg = lightSurfaces['inputs / white panels (midnight-900)'];
  const pageBg = lightSurfaces['page (midnight-950)'];

  it('base border (light override) meets 3:1 vs input background and page', () => {
    const c = composite(
      lightRgbToken(`slateui-${lightBaseBorder.tokenId}`),
      lightBaseBorder.alpha,
      inputBg,
    );
    expect(contrast(c, inputBg)).toBeGreaterThanOrEqual(3);
    expect(contrast(c, pageBg)).toBeGreaterThanOrEqual(3);
  });

  it('hover border meets 3:1 and is stronger than the base border', () => {
    const base = composite(
      lightRgbToken(`slateui-${lightBaseBorder.tokenId}`),
      lightBaseBorder.alpha,
      inputBg,
    );
    const c = composite(
      lightRgbToken(`slateui-${sharedHoverBorder.tokenId}`),
      sharedHoverBorder.alpha,
      inputBg,
    );
    expect(contrast(c, inputBg)).toBeGreaterThanOrEqual(3);
    expect(contrast(c, pageBg)).toBeGreaterThanOrEqual(3);
    // Light theme: darker border = stronger state.
    expect(relativeLuminance(c)).toBeLessThan(relativeLuminance(base));
  });

  it('focus border (violetui-500) meets 3:1 vs input background and page', () => {
    const c = lightRgbToken(`violetui-${sharedFocusBorder.tokenId}`);
    expect(contrast(c, inputBg)).toBeGreaterThanOrEqual(3);
    expect(contrast(c, pageBg)).toBeGreaterThanOrEqual(3);
  });

  it('light override precedes the shared .input rule so :hover/:focus still win', () => {
    const overrideIndex = css.indexOf("[data-theme='light'] .input {");
    const sharedIndex = css.search(/\.input \{\s*@apply/);
    expect(overrideIndex).toBeGreaterThan(-1);
    expect(overrideIndex).toBeLessThan(sharedIndex);
  });
});

/* ---------- print palette ---------- */

describe('print palette remains legible on paper white', () => {
  const paper: Rgb = [255, 255, 255];

  it('slateui-400 meets 4.5:1 on white', () => {
    expect(contrast(printRgbToken('slateui-400'), paper)).toBeGreaterThanOrEqual(4.5);
  });

  it('slateui-500 meets 4.5:1 on white', () => {
    expect(contrast(printRgbToken('slateui-500'), paper)).toBeGreaterThanOrEqual(4.5);
  });
});

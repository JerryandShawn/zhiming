const descriptors = ['font-family', 'font-style', 'font-display', 'font-weight', 'src', 'unicode-range'];

function invalid() {
  throw new Error('Unexpected Fontsource CSS; preserve the original font coverage and review the package update');
}
function validRange(value) {
  const match = /^U\+([a-f0-9]{1,6})(?:-([a-f0-9]{1,6}))?$/i.exec(value.trim());
  if (!match) return false;
  const first = Number.parseInt(match[1], 16),
    last = Number.parseInt(match[2] ?? match[1], 16);
  return first <= last && last <= 0x10ffff;
}

/** Compact only the pinned Fontsource grammar; every ordered descriptor value stays unchanged. */
export function compactFontCss(css) {
  if (typeof css !== 'string') invalid();
  const cleaned = css.replace(/\/\*[\s\S]*?\*\//g, ' ');
  const pattern = /@font-face\s*\{([^{}]*)\}/g;
  const blocks = [...cleaned.matchAll(pattern)];
  if (!blocks.length || cleaned.replace(pattern, '').trim()) invalid();
  return blocks
    .map((match) => {
      const entries = match[1]
        .split(';')
        .map((entry) => entry.trim())
        .filter(Boolean)
        .map((entry) => {
          const separator = entry.indexOf(':');
          if (separator <= 0) invalid();
          return [entry.slice(0, separator).trim(), entry.slice(separator + 1).trim()];
        });
      if (
        entries.length !== descriptors.length ||
        new Set(entries.map(([key]) => key)).size !== descriptors.length ||
        entries.some(([key]) => !descriptors.includes(key))
      )
        invalid();
      const face = Object.fromEntries(entries);
      const family = /^'Noto (Sans|Serif) SC'$/.exec(face['font-family']);
      if (
        !family ||
        face['font-style'] !== 'normal' ||
        face['font-display'] !== 'swap' ||
        face['font-weight'] !== (family[1] === 'Sans' ? '100 900' : '200 900') ||
        !/^url\(\.\/noto-(?:sans|serif)-sc-(?:[0-9]+|[a-z-]+)-wght-normal\.woff2\) format\('woff2-variations'\)$/.test(
          face.src,
        ) ||
        !face['unicode-range'].split(',').every(validRange)
      )
        invalid();
      return '@font-face{' + entries.map(([key, value]) => key + ':' + value).join(';') + '}';
    })
    .join('');
}

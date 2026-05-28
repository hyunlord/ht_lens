# KaTeX vendor — 0.16.22

KaTeX 0.16.22 (MIT license, see `LICENSE`). Vendored so the viewer renders
LaTeX math offline; do **not** modify the files in place.

## Files

- `katex.mjs` — ESM module (`export default katex`, plus `render`,
  `renderToString`, `ParseError`, etc.). About 596 KB unminified. The
  `.min.js` build in upstream is a UMD wrapper and cannot be imported
  as ESM, so we ship the readable `.mjs` instead.
- `katex.min.css` — `@font-face` declarations + display rules. References
  files relative to itself under `fonts/`.
- `auto-render.mjs` — `contrib/auto-render` extension as ESM
  (`export default renderMathInElement`). Imports `../katex.mjs`.
- `fonts/` — KaTeX_Main / KaTeX_Math / KaTeX_AMS / KaTeX_Caligraphic /
  KaTeX_Fraktur / KaTeX_Script / KaTeX_SansSerif / KaTeX_Size1-4 /
  KaTeX_Typewriter in `.ttf`, `.woff`, and `.woff2`.
- `LICENSE` — MIT, upstream KaTeX maintainers.

## To regenerate

```bash
npm pack katex@0.16.22
tar xf katex-0.16.22.tgz -C /tmp/
BASE=/tmp/package/dist
DEST=src/ht_lens/api/static/vendor/katex
cp $BASE/katex.mjs $BASE/katex.min.css "$DEST/"
cp $BASE/contrib/auto-render.mjs "$DEST/"
cp -r $BASE/fonts "$DEST/"
cp /tmp/package/LICENSE "$DEST/"
# Patch the import: upstream auto-render.mjs lives in dist/contrib/ so it
# imports ``../katex.mjs``; we flatten the layout into one directory, so
# the path becomes ``./katex.mjs``.
sed -i "s|from '../katex.mjs'|from './katex.mjs'|" "$DEST/auto-render.mjs"
```

## Why these specific files

- `.mjs` not `.min.js`: upstream minifies only the UMD bundle. ht_lens
  modules use native browser ESM (`import katex from ...`), so the
  unminified `.mjs` is the only viable option.
- `auto-render.mjs`: the `delimiters` + `ignoredTags` configuration is
  the cleanest way to scope rendering to paired `$...$` / `$$...$$`
  inside a host element without disturbing surrounding text.
- All three font formats: KaTeX CSS lists `woff2`, `woff`, and `ttf`
  fallbacks; dropping any breaks older browsers we have no plan to
  drop yet.

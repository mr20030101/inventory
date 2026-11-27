# SAIMS — logo assets

The mark is a box with a tick on its front face: inventory that is accounted for.
Every SVG has the wordmark converted to outlines, so nothing depends on a font being installed.
Backgrounds are transparent except the icon tiles. Typeface: Plus Jakarta Sans (ExtraBold for
"SAIMS", SemiBold for the tagline), free under the SIL Open Font License.

## svg/
| File | Use |
| --- | --- |
| `logo-horizontal.svg` | Default. App sign-in screen, documents, proposal cover, email signature. |
| `logo-horizontal-inverse.svg` | The same lockup on teal or dark backgrounds. **Looks blank on white; that is correct.** |
| `logo-horizontal-mono.svg` | One colour; takes the CSS `color` of its parent (`currentColor`), so it looks black until one is set. |
| `logo-stacked.svg` | Narrow or square spaces: posters, title slides. |
| `mark.svg`, `mark-inverse.svg` | The box alone, for light and dark grounds. |
| `mark-mono.svg` | One colour, for engraving, stamps, embroidery and single-ink print. |
| `mark-small.svg` | Simplified cut with a thicker tick, for anything 44 px or smaller. |
| `wordmark*.svg` | "SAIMS" and tagline without the box. |

## icons/
PNG and SVG at every size a desktop or web app asks for (16, 32, 180, 192, 512), plus a
multi-resolution `favicon.ico`. `icon-512-accent` is an alternative tile on green.

## print/
Vector PDF and EPS: full colour, one ink (teal or black), and reverse. Send these to printers
and sign makers.

## pattern/
Seamless background tiles of the box. Use at 6–8% strength behind headers, the sign-in screen,
empty states and slide backgrounds, never behind text you need to read.

## Colours
| Role | Hex | CMYK (approx.) | Use |
| --- | --- | --- | --- |
| `ink` | #2f5d6e | 57 / 15 / 0 / 57 | Teal. Mark body, headings, the wordmark |
| `shade` | #1f4452 | 62 / 17 / 0 / 68 | Deep teal. The mark's shadow side |
| `accent` | #4fae8a | 55 / 0 / 21 / 32 | Green. The box lid and small highlights; shapes only, never text on light grounds |
| `accent_text` | #2e7d5b | 63 / 0 / 27 / 51 | Dark green. Use instead of the accent for green text and links (5.0:1 on white) |
| `sub` | #557280 | 34 / 11 / 0 / 50 | Slate. Secondary text and the tagline (4.9:1 on the light ground) |
| `light` | #f5fafc | 3 / 1 / 0 / 1 | Off-white. Page background; the mark's front face when reversed |
| `mist` | #c5dae2 | 13 / 4 / 0 / 11 | Pale teal. Borders, rules; the mark's side face when reversed |

CMYK values are straight arithmetic conversions from screen colour, not press-matched. Ask the
printer for a proof, or match against a physical swatch book, before a large print run.

`brand-tokens.css` has the same colours as CSS variables; `favicon-snippet.html` has the tags
for a website's `<head>`.

## Rules
- **Clear space:** keep empty space on all sides equal to half the box's height.
- **Minimum sizes:** box alone 24 px / 8 mm; full lockup 112 px / 30 mm wide. Smaller than that,
  use the box alone (and `mark-small` at 44 px or less).
- **Green is for shapes, not words:** on light backgrounds, green text uses the dark green
  (`accent_text`).
- **Don't** stretch, squash, rotate, recolour, add shadows or outlines, rearrange the box and
  words, or place the logo on a busy photo or low-contrast colour.

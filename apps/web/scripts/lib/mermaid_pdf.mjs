/**
 * Renders Mermaid diagrams into printable PDFs, shared by build_docs_pdf.mjs
 * and build_workflow_diagram_pdf.mjs.
 *
 * `marked` (both scripts' Markdown renderer) has no idea what a ```mermaid
 * fence is — it renders it as an escaped, monospaced code block, same as any
 * other language. Left alone that is not a fallback, it is silent data loss:
 * the HLD's own "System shape (one picture)" diagram shipped for weeks as a
 * page of raw flowchart syntax, in a PDF whose one job is to be handed to a
 * reviewer who was never going to open the source repo to find the real
 * picture.
 *
 * The fix runs in three steps across two processes:
 *   1. (Node) `extractMermaidBlocks` pulls each fenced block out of the raw
 *      Markdown *before* `marked.parse` ever sees it, replacing it with a
 *      plain-text placeholder and keeping the untouched source on the side.
 *   2. (Node) `placeMermaidTargets` swaps the placeholder's rendered
 *      paragraph for an empty target <div>, once parsing is done.
 *   3. (browser) `renderMermaidDiagrams` loads Mermaid's own bundle into the
 *      already-open Playwright page and asks it to render each source into
 *      its matching target.
 *
 * Splitting extraction from rendering like this — rather than trying to
 * coax marked into emitting valid Mermaid HTML — sidesteps HTML escaping
 * entirely. Mermaid's own syntax uses `-->`, `<br/>`, and other sequences
 * that collide with HTML the moment they pass through a DOM parser; the raw
 * source is instead carried untouched as a JS string all the way to
 * `mermaid.render()`, which is the only thing that needs to understand it.
 */

import { readFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const MERMAID_DIST = resolve(HERE, '..', '..', 'node_modules', 'mermaid', 'dist', 'mermaid.min.js')

const FENCE = /```mermaid\n([\s\S]*?)```/g

/**
 * Replaces every ```mermaid fenced block in `markdown` with a placeholder
 * paragraph, pushing each block's raw source into `sink` in the order found.
 * `sink`'s existing length is the starting index, so this is safe to call
 * once per source document while accumulating one shared array — each
 * document's diagrams land at distinct indices rather than colliding at 0.
 */
export function extractMermaidBlocks(markdown, sink) {
  return markdown.replace(FENCE, (_match, source) => {
    const id = sink.length
    sink.push(source.trim())
    // A lone, unremarkable line of text: marked wraps it in its own <p>,
    // predictably and without any Markdown syntax of its own to collide
    // with — verified against this exact marked version before relying on
    // it, since "wraps standalone text in a paragraph" is an assumption
    // about renderer behaviour, not a documented guarantee.
    return `@@MERMAID_${id}@@`
  })
}

/**
 * Swaps each placeholder's rendered `<p>` for an empty target the renderer
 * will fill in. Call once, after every document has been through both
 * `extractMermaidBlocks` and `marked.parse`.
 */
export function placeMermaidTargets(html) {
  return html.replace(/<p>@@MERMAID_(\d+)@@<\/p>/g, '<div class="mermaid-diagram" data-mmd-id="$1"></div>')
}

/** Minimal styling for the target container. The SVG mermaid produces
 * already carries its own layout; this only keeps it from overflowing the
 * printed page and centres it the way a figure should sit in running text. */
export const MERMAID_CSS = `
  .mermaid-diagram { display: flex; flex-direction: column; align-items: center;
    margin: 14pt 0; break-inside: avoid; }
  .mermaid-diagram svg { max-width: 100%; height: auto; }
  .mermaid-diagram.mermaid-error { background: #fef2f2; border: 1px solid #fca5a5;
    border-radius: 6px; padding: 10pt; }
`

/**
 * Loads Mermaid into `page` (already navigated/`setContent`-ed) and renders
 * `sources[i]` into the placeholder at `data-mmd-id="i"`, in place.
 *
 * Rendering happens inside the page rather than in Node because Mermaid's
 * layout engine measures real text with a real DOM — there is no headless,
 * DOM-free way to get the same box sizes it will actually print at.
 * Diagrams are rendered one at a time in a plain loop, not in parallel,
 * because Mermaid keeps rendering state on `window` and concurrent calls
 * are not documented as safe.
 */
export async function renderMermaidDiagrams(page, sources, { theme = 'neutral' } = {}) {
  if (sources.length === 0) return
  const mermaidJs = await readFile(MERMAID_DIST, 'utf8')
  await page.addScriptTag({ content: mermaidJs })
  await page.evaluate(
    async ({ sources, theme }) => {
      const mermaid = globalThis.mermaid
      mermaid.initialize({ startOnLoad: false, theme, securityLevel: 'loose', fontFamily: 'inherit' })
      for (let i = 0; i < sources.length; i++) {
        const target = document.querySelector(`.mermaid-diagram[data-mmd-id="${i}"]`)
        if (!target) continue
        try {
          const { svg } = await mermaid.render(`mmd-${i}`, sources[i])
          target.innerHTML = svg
        } catch (error) {
          // A diagram failing to render must be visible on the page, not
          // swallowed into an empty box a reader would mistake for "no
          // diagram here" rather than "this one is broken".
          const message = error && error.message ? error.message : String(error)
          target.classList.add('mermaid-error')
          target.innerHTML = `<pre>Mermaid diagram failed to render:\n${message}</pre>`
        }
      }
    },
    { sources, theme },
  )
}

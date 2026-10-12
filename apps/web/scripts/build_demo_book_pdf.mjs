/**
 * Prints the demo book, docs/15-DEMO-BOOK.md, to docs/Sentinel-Demo-Book.pdf —
 * the copy carried on the day. Checklists become boxes to tick by hand, and
 * each numbered section starts on its own page where it fits, so the
 * one-page card (§11) prints alone.
 *
 * Usage:
 *   npm run docs:demo-book      (from apps/web)
 *
 * Regenerate whenever the markdown changes: the PDF is the copy people act on.
 */

import { chromium } from '@playwright/test'
import { marked } from 'marked'
import { readFile } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const DOCS = resolve(HERE, '..', '..', '..', 'docs')
const SOURCE = resolve(DOCS, '15-DEMO-BOOK.md')
const OUT = resolve(DOCS, 'Sentinel-Demo-Book.pdf')

const CSS = `
  @page { size: A4; margin: 15mm 14mm 16mm; }
  body { font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
    font-size: 10pt; line-height: 1.5; color: #111417; margin: 0; }
  h1 { font-size: 21pt; margin: 0 0 2pt; }
  h1 + h3 { font-weight: 400; color: #4c5157; margin-top: 0; }
  h2 { font-size: 14pt; margin: 0 0 6pt; padding: 5pt 8pt; background: #111417; color: #fff;
    border-radius: 3pt; break-after: avoid; }
  h2.page { break-before: page; }
  h3 { font-size: 11.5pt; margin: 12pt 0 4pt; break-after: avoid; }
  p, li { orphans: 3; widows: 3; }
  code { font-family: Menlo, Consolas, monospace; font-size: 8.8pt; background: #f3f4f0;
    padding: 0 2pt; border-radius: 2pt; }
  pre { background: #f3f4f0; border: 1px solid #d5d7d2; border-radius: 3pt; padding: 6pt 8pt;
    white-space: pre-wrap; break-inside: avoid; }
  pre code { background: none; padding: 0; }
  table { border-collapse: collapse; width: 100%; margin: 6pt 0 9pt; font-size: 8.8pt;
    break-inside: auto; }
  tr { break-inside: avoid; }
  th, td { border: 1px solid #d5d7d2; padding: 3.5pt 5pt; text-align: left; vertical-align: top; }
  th { background: #edeeea; }
  blockquote { margin: 7pt 0; padding: 5pt 10pt; background: #fff4da; border-radius: 3pt;
    break-inside: avoid; }
  blockquote p { margin: 0; }
  ul.checks { list-style: none; padding-left: 4pt; }
  ul.checks li::before { content: "\\2610"; font-size: 12pt; margin-right: 6pt; }
  hr { display: none; }
  a { color: inherit; text-decoration: none; }
`

async function main() {
  const markdown = await readFile(SOURCE, 'utf8')
  let html = marked.parse(markdown)
  // GitHub task-list syntax as printable boxes.
  html = html.replace(/<li>\s*\[ \]\s*/g, '<li class="check">')
    .replace(/<ul>(\s*<li class="check">)/g, '<ul class="checks">$1')
  // Every numbered section after the first on a new page.
  html = html.replace(/<h2>(?!1\.)/g, '<h2 class="page">')

  const page = await (await chromium.launch()).newPage()
  await page.setContent(
    `<!doctype html><html><head><meta charset="utf-8"><base href="${pathToFileURL(DOCS)}/">
     <style>${CSS}</style></head><body>${html}</body></html>`,
    { waitUntil: 'load' },
  )
  await page.pdf({
    path: OUT,
    format: 'A4',
    printBackground: true,
    displayHeaderFooter: true,
    headerTemplate: '<span></span>',
    footerTemplate: `<div style="font: 8px Helvetica, Arial; color: #8a8f95; width: 100%;
      padding: 0 14mm; display: flex; justify-content: space-between;">
      <span>Sentinel · Demo Book · 13 October 2026</span>
      <span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>`,
    margin: { top: '15mm', bottom: '16mm', left: '14mm', right: '14mm' },
  })
  await page.context().browser().close()
  console.log(`wrote ${OUT}`)
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})

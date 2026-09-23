/**
 * Builds the submission PDF: the full document set as one printable file.
 *
 * The challenge asks for the HLD as a PDF. Exporting only 01-ARCHITECTURE
 * would land a reviewer in the middle of a set that cross-references itself
 * constantly, so this stitches the documents together in reading order,
 * rewrites the inter-document links into internal anchors, and prints the
 * result through Chromium.
 *
 * Usage:
 *   npm run docs:pdf            (from apps/web)
 *
 * Regenerate this whenever docs/ changes — a PDF that disagrees with the
 * repository is worse than no PDF.
 */

import { chromium } from '@playwright/test'
import { marked } from 'marked'
import { readFile, mkdir } from 'node:fs/promises'
import { dirname, resolve, basename } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const REPO = resolve(HERE, '..', '..', '..')
const DOCS = resolve(REPO, 'docs')
const OUT = resolve(REPO, 'docs', 'Sentinel-Platform-HLD.pdf')

// Reading order. The HLD proper is 01; the rest is the context a reviewer
// needs to judge whether the HLD is honest.
const DOCUMENTS = [
  '00-SOLUTION-PLAN.md',
  '01-ARCHITECTURE.md',
  '02-ANPR-PIPELINE.md',
  '03-UX-DESIGN.md',
  '04-SCALE-PLAN.md',
  '05-DELIVERY-PLAN.md',
  '06-SUBMISSION-PLAYBOOK.md',
  '07-DRIVER-SDK.md',
  '08-SECURITY-HARDENING.md',
  '09-SECONDARY-ANALYTICS.md',
]

const slug = (file) => basename(file, '.md').toLowerCase()

const CSS = `
  @page { size: A4; margin: 18mm 16mm; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    font-size: 10.5pt; line-height: 1.55; color: #16181d; margin: 0;
  }
  h1, h2, h3, h4 { line-height: 1.25; color: #0b0c0f; }
  h1 { font-size: 22pt; margin: 0 0 4pt; }
  h2 { font-size: 15pt; margin: 20pt 0 6pt; border-bottom: 1px solid #dfe3ea; padding-bottom: 4pt; }
  h3 { font-size: 12pt; margin: 14pt 0 4pt; }
  h4 { font-size: 10.5pt; margin: 12pt 0 3pt; }
  /* Keep a heading with the text it introduces. */
  h1, h2, h3, h4 { break-after: avoid; }
  table, pre, blockquote, img { break-inside: avoid; }
  code { font-family: ui-monospace, 'SF Mono', Menlo, monospace; font-size: 9pt;
         background: #f2f4f7; padding: 1px 4px; border-radius: 3px; }
  pre { background: #f7f8fa; border: 1px solid #e4e8ee; border-radius: 5px;
        padding: 9pt 11pt; overflow-x: auto; }
  pre code { background: none; padding: 0; font-size: 8.5pt; line-height: 1.45; }
  table { border-collapse: collapse; width: 100%; margin: 9pt 0; font-size: 9pt; }
  th, td { border: 1px solid #dfe3ea; padding: 5pt 7pt; text-align: left; vertical-align: top; }
  th { background: #f2f4f7; font-weight: 600; }
  blockquote { margin: 9pt 0; padding: 6pt 12pt; border-left: 3px solid #b9c2d0;
               background: #f7f8fa; color: #3c424e; }
  img { max-width: 100%; }
  a { color: #1d4ed8; text-decoration: none; }
  .doc { break-before: page; }
  .doc:first-of-type { break-before: auto; }
  .cover { text-align: center; padding-top: 55mm; break-after: page; }
  .cover h1 { font-size: 32pt; border: none; }
  .cover .sub { font-size: 13pt; color: #4a5160; margin-top: 8pt; }
  .cover .meta { margin-top: 26mm; font-size: 9.5pt; color: #6b7280; }
  .toc h2 { border: none; }
  .toc ol { padding-left: 18pt; }
  .toc li { margin: 3pt 0; }
`

async function main() {
  marked.setOptions({ gfm: true, breaks: false })

  const parts = []
  for (const file of DOCUMENTS) {
    let md = await readFile(resolve(DOCS, file), 'utf8')

    // Inter-document links become internal anchors so the PDF navigates
    // itself instead of pointing at files the reader does not have.
    for (const other of DOCUMENTS) {
      md = md.replaceAll(`./${other}`, `#${slug(other)}`).replaceAll(`(${other})`, `(#${slug(other)})`)
    }
    // Repo-relative links (../packages/..., ../evidence/...) cannot resolve
    // inside a PDF at all; keep the link text, drop the dead target.
    md = md.replace(/\[([^\]]+)\]\(\.\.\/[^)]+\)/g, '`$1`')

    parts.push(`<section class="doc" id="${slug(file)}">${marked.parse(md)}</section>`)
  }

  const toc = DOCUMENTS.map((f) => {
    const title = basename(f, '.md').replace(/^(\d+)-/, '$1 — ').replace(/-/g, ' ')
    return `<li><a href="#${slug(f)}">${title}</a></li>`
  }).join('\n')

  const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Sentinel Platform — HLD</title>
<base href="${pathToFileURL(DOCS + '/').href}">
<style>${CSS}</style></head><body>
<div class="cover">
  <h1>Sentinel Platform</h1>
  <p class="sub">Unified CCTV Integration &amp; AI Video Analytics<br>High-Level Design and supporting documents</p>
  <p class="meta">Gujarat Police Innovation Challenge 2026<br>Generated ${new Date().toISOString().slice(0, 10)}</p>
</div>
<section class="toc"><h2>Contents</h2><ol>${toc}</ol></section>
${parts.join('\n')}
</body></html>`

  const browser = await chromium.launch()
  const page = await browser.newPage()
  // <base> above resolves the relative <img> paths in docs/; setContent alone
  // would leave them pointing at about:blank.
  await page.setContent(html, { waitUntil: 'load' })
  await page.waitForTimeout(1500)
  await mkdir(dirname(OUT), { recursive: true })
  await page.pdf({
    path: OUT,
    format: 'A4',
    printBackground: true,
    displayHeaderFooter: true,
    headerTemplate: '<div></div>',
    footerTemplate:
      '<div style="width:100%;font-size:7.5pt;color:#8b93a1;padding:0 16mm;' +
      'display:flex;justify-content:space-between;">' +
      '<span>Sentinel Platform — High-Level Design</span>' +
      '<span class="pageNumber"></span></div>',
    margin: { top: '18mm', bottom: '16mm', left: '16mm', right: '16mm' },
  })
  await browser.close()
  console.log(`wrote ${OUT}`)
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})

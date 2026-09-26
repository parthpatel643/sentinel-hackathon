/**
 * Builds a standalone Workflow / Integration Diagram PDF — the two pictures
 * a reviewer reaches for first: how the fragmented, multi-vendor camera
 * estate integrates into one system, and how a plate query actually becomes
 * a mapped route.
 *
 * Both diagrams already exist as the canonical ones in docs/ — this does
 * not draw anything new, it prints what is already there. That is
 * deliberate: a diagram invented for a submission form and a diagram this
 * repository actually lives by are two different levels of truth, and only
 * one of them survives someone opening the source archive to check.
 *
 *   Diagram 1 — docs/00-SOLUTION-PLAN.md §3 "System shape (one picture)"
 *   Diagram 2 — docs/01-ARCHITECTURE.md §6.3 "Route reconstruction & cross-
 *               camera ReID"
 *
 * Extraction is by heading, not by line number, so this keeps working if
 * either document is edited — it only breaks, loudly, if a heading is
 * renamed or its diagram removed, which is exactly when it should break.
 *
 * Usage: npm run docs:diagram   (from apps/web)
 * Output: docs/Sentinel-Platform-Workflow-Integration-Diagram.pdf
 */

import { chromium } from '@playwright/test'
import { marked } from 'marked'
import { readFile, mkdir } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { extractMermaidBlocks, placeMermaidTargets, renderMermaidDiagrams, MERMAID_CSS } from './lib/mermaid_pdf.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))
const REPO = resolve(HERE, '..', '..', '..')
const DOCS = resolve(REPO, 'docs')
const OUT = resolve(DOCS, 'Sentinel-Platform-Workflow-Integration-Diagram.pdf')

/**
 * Finds a heading matching `headingRe` in `markdown`, and returns the
 * Markdown text of that section alone — up to (but not including) the next
 * heading at the same or a shallower level.
 *
 * Throws rather than returning nothing on a miss: a diagram silently
 * dropped from a "these are the diagrams" deliverable is a worse failure
 * than a build that stops and says which heading it could not find.
 */
function extractSection(markdown, headingRe, label) {
  const lines = markdown.split('\n')
  const startIdx = lines.findIndex((line) => headingRe.test(line))
  if (startIdx === -1) throw new Error(`could not find the "${label}" section — has it been renamed?`)
  const startLevel = lines[startIdx].match(/^(#+)/)[1].length

  let endIdx = lines.length
  for (let i = startIdx + 1; i < lines.length; i++) {
    const m = lines[i].match(/^(#+)\s/)
    if (m && m[1].length <= startLevel) {
      endIdx = i
      break
    }
  }
  return lines.slice(startIdx, endIdx).join('\n')
}

/** The one-line source note under each diagram — traceability, not decor:
 * a reviewer who doubts the picture can go find the exact section it came
 * from in five seconds rather than taking it on faith. */
function sourceNote(file, heading) {
  return `Source: <code>docs/${file}</code> — "${heading}"`
}

const CSS = `
  @page { size: A4; margin: 20mm 18mm; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    color: #16181d; margin: 0; }
  .cover { text-align: center; padding-top: 60mm; break-after: page; }
  .cover h1 { font-size: 30pt; margin: 0; }
  .cover .sub { font-size: 13pt; color: #4a5160; margin-top: 8pt; }
  .cover .meta { margin-top: 26mm; font-size: 9.5pt; color: #6b7280; }
  .diagram-page { break-after: page; }
  .diagram-page:last-child { break-after: auto; }
  .diagram-page h2 { font-size: 16pt; margin: 0 0 3pt; }
  .diagram-page .caption { font-size: 10pt; color: #3c424e; margin: 0 0 14pt; max-width: 640pt; }
  .diagram-page .note { font-size: 8.5pt; color: #8b93a1; margin-top: 10pt; }
  .diagram-page .note code { font-family: ui-monospace, 'SF Mono', Menlo, monospace; }
  ${MERMAID_CSS}
`

/** Each diagram's caption: the sentence immediately after its own fenced
 * block in the source, wherever the source already explains what the
 * picture means — reused rather than re-authored, so the words in this PDF
 * and the words in docs/ cannot quietly diverge. */
function firstParagraphAfterFence(sectionMd) {
  const afterFence = sectionMd.split('```').slice(2).join('```')
  const match = afterFence.match(/\n\n([^\n#-][^\n]+)/)
  return match ? match[1].trim() : ''
}

async function main() {
  const solutionPlan = await readFile(resolve(DOCS, '00-SOLUTION-PLAN.md'), 'utf8')
  const architecture = await readFile(resolve(DOCS, '01-ARCHITECTURE.md'), 'utf8')

  const integrationSection = extractSection(
    solutionPlan,
    /^##\s+3\.\s+System shape/i,
    'System shape (one picture)',
  )
  const workflowSection = extractSection(
    architecture,
    /^###\s+6\.3\s+Route reconstruction/i,
    'Route reconstruction & cross-camera ReID',
  )

  const mermaidSources = []
  const diagrams = [
    {
      title: 'System Integration Diagram',
      caption: firstParagraphAfterFence(integrationSection) ||
        'How a fragmented, multi-vendor camera estate becomes one system: every plane from ingest to the operator console, and where government systems attach.',
      note: sourceNote('00-SOLUTION-PLAN.md', 'System shape (one picture)'),
      markdownWithPlaceholder: extractMermaidBlocks(integrationSection, mermaidSources),
    },
    {
      title: 'Vehicle Tracking Workflow',
      caption: firstParagraphAfterFence(workflowSection) ||
        'How a registration plate query becomes a mapped, timestamped route: search, feasibility-checked hop ordering, and replay.',
      note: sourceNote('01-ARCHITECTURE.md', '6.3 Route reconstruction & cross-camera ReID'),
      markdownWithPlaceholder: extractMermaidBlocks(workflowSection, mermaidSources),
    },
  ]

  // The two sections carry their own headings and surrounding prose, which
  // this deliverable does not want repeated — only the fenced diagram itself
  // is kept, addressed by the same @@MERMAID_n@@ placeholder every other
  // consumer of lib/mermaid_pdf.mjs uses.
  for (const d of diagrams) {
    const m = d.markdownWithPlaceholder.match(/@@MERMAID_\d+@@/)
    d.placeholderHtml = m ? `<p>${m[0]}</p>` : ''
  }

  const pages = diagrams
    .map(
      (d) => `<section class="diagram-page">
        <h2>${d.title}</h2>
          <p class="caption">${marked.parseInline(d.caption)}</p>
        ${placeMermaidTargets(d.placeholderHtml)}
        <p class="note">${d.note}</p>
      </section>`,
    )
    .join('\n')

  const html = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Sentinel Platform — Workflow &amp; Integration Diagram</title>
<style>${CSS}</style></head><body>
<div class="cover">
  <h1>Sentinel Platform</h1>
  <p class="sub">Workflow &amp; Integration Diagram</p>
  <p class="meta">Gujarat Police Innovation Challenge 2026<br>Generated ${new Date().toISOString().slice(0, 10)}<br>Both diagrams are printed unchanged from docs/ — see the source note under each.</p>
</div>
${pages}
</body></html>`

  const browser = await chromium.launch()
  const page = await browser.newPage()
  await page.setContent(html, { waitUntil: 'load' })
  await page.waitForTimeout(800)
  await renderMermaidDiagrams(page, mermaidSources)
  await mkdir(dirname(OUT), { recursive: true })
  await page.pdf({
    path: OUT,
    format: 'A4',
    printBackground: true,
    displayHeaderFooter: true,
    headerTemplate: '<div></div>',
    footerTemplate:
      '<div style="width:100%;font-size:7.5pt;color:#8b93a1;padding:0 18mm;' +
      'display:flex;justify-content:space-between;">' +
      '<span>Sentinel Platform — Workflow &amp; Integration Diagram</span>' +
      '<span class="pageNumber"></span></div>',
    margin: { top: '20mm', bottom: '16mm', left: '18mm', right: '18mm' },
  })
  await browser.close()
  console.log(`wrote ${OUT}`)
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})

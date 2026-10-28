import type { NewsMention } from '@/lib/api/news-analysis'

export interface TextPiece { text: string; start: number; mention?: NewsMention }
const latinWord = (char: string) => /[\p{Script=Latin}\p{N}\p{M}_]/u.test(char)
function nameBoundary(text: string, start: number, end: number, name: string) {
  if (!/\p{Script=Latin}/u.test(name)) return true
  return (!start || !latinWord(text[start - 1]!)) && (end === text.length || !latinWord(text[end]!))
}

/** Every offset is computed in the same JS snapshot: UTF-16 [start,end). */
export function articlePieces(text: string, mentions: NewsMention[]): TextPiece[] {
  const spans: { start: number; end: number; mention: NewsMention }[] = []
  for (const mention of mentions) {
    if (mention.status !== 'linked' || !mention.entity || !mention.mention || !mention.evidence) continue
    let evidenceStart = text.indexOf(mention.evidence)
    let found = false
    while (evidenceStart !== -1 && !found) {
      let local = mention.evidence.indexOf(mention.mention)
      while (local !== -1) {
        const start = evidenceStart + local
        const end = start + mention.mention.length
        if (nameBoundary(text, start, end, mention.mention)) {
          spans.push({ start, end, mention }); found = true; break
        }
        local = mention.evidence.indexOf(mention.mention, local + 1)
      }
      evidenceStart = text.indexOf(mention.evidence, evidenceStart + 1)
    }
  }
  // Prefer longer names when two validated spans overlap. Never replace all occurrences.
  const identities = new Map<string, Set<string>>()
  for (const span of spans) {
    const range = `${span.start}:${span.end}`
    const targets = identities.get(range) ?? new Set<string>()
    targets.add(`${span.mention.entity_type}:${span.mention.entity!.id}`)
    identities.set(range, targets)
  }
  const chosen: typeof spans = []
  for (const span of spans.sort((a, b) => (b.end - b.start) - (a.end - a.start) || a.start - b.start)) {
    if (identities.get(`${span.start}:${span.end}`)!.size > 1) continue
    if (!chosen.some(other => span.start < other.end && other.start < span.end)) chosen.push(span)
  }
  chosen.sort((a, b) => a.start - b.start)
  const pieces: TextPiece[] = []
  let cursor = 0
  for (const span of chosen) {
    if (span.start > cursor) pieces.push({ text: text.slice(cursor, span.start), start: cursor })
    pieces.push({ text: text.slice(span.start, span.end), start: span.start, mention: span.mention })
    cursor = span.end
  }
  if (cursor < text.length || !pieces.length) pieces.push({ text: text.slice(cursor), start: cursor })
  return pieces
}

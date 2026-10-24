import { writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { z } from 'zod'
import { homePreviewSchema, homePreviewAnalysisSchema } from '../src/lib/api/homePreviewSchema'
import { homePreviewResponseSchema } from '../src/lib/api/homePreviewResponse'
import { homeRecommendationsSchema } from '../src/lib/api/homeRecommendationsSchema'
import { sampleMatches, sampleDay } from '../src/mocks/home-preview/data'
import { buildMockPreview } from '../src/mocks/home-preview/preview'
import { buildMockResponse } from '../src/mocks/home-preview/response'
import { buildMockRecommendations } from '../src/mocks/home-preview/recommendations'

// Structural projection. Zod superRefine invariants are specified in PRE-01 and shared negative fixtures.
export function project(schema: z.ZodTypeAny): Record<string, unknown> {
  const d = schema._def
  if (schema instanceof z.ZodEffects) return project(d.schema)
  if (schema instanceof z.ZodNullable) return { anyOf: [project(d.innerType), { type: 'null' }] }
  if (schema instanceof z.ZodObject) return { type: 'object', additionalProperties: false, required: Object.keys(schema.shape), properties: Object.fromEntries(Object.entries(schema.shape).map(([key, child]) => [key, project(child as z.ZodTypeAny)])) }
  if (schema instanceof z.ZodArray) return { type: 'array', items: project(d.type), ...(d.minLength ? { minItems: d.minLength.value } : {}), ...(d.maxLength ? { maxItems: d.maxLength.value } : {}) }
  if (schema instanceof z.ZodEnum) return { type: 'string', enum: d.values }
  if (schema instanceof z.ZodLiteral) return { const: d.value, type: typeof d.value }
  if (schema instanceof z.ZodBoolean) return { type: 'boolean' }
  if (schema instanceof z.ZodString) {
    const out: Record<string, unknown> = { type: 'string' }
    for (const check of d.checks) {
      if (check.kind === 'min') out.minLength = check.value
      if (check.kind === 'datetime') out.format = 'date-time'
      if (check.kind === 'url') out.format = 'uri'
      if (check.kind === 'regex') out.pattern = check.regex.source
    }
    return out
  }
  if (schema instanceof z.ZodNumber) {
    const out: Record<string, unknown> = { type: d.checks.some((c: { kind: string }) => c.kind === 'int') ? 'integer' : 'number' }
    for (const check of d.checks) {
      if (check.kind === 'min') out[check.inclusive ? 'minimum' : 'exclusiveMinimum'] = check.value
      if (check.kind === 'max') out[check.inclusive ? 'maximum' : 'exclusiveMaximum'] = check.value
    }
    return out
  }
  throw new Error(`Unsupported schema ${d.typeName}`)
}
export const contracts = { 'payload': homePreviewSchema, 'response': homePreviewResponseSchema, 'recommendations': homeRecommendationsSchema, 'analysis': homePreviewAnalysisSchema }
export function documentSchema(name: string, schema: z.ZodTypeAny) {
  return { $schema: 'https://json-schema.org/draft/2020-12/schema', title: `Home preview ${name}`, $comment: 'Generated from Zod. Cross-field invariants: docs/features/home-preview-contract.md; enforced by Zod and later BE parity tests.', ...project(schema) }
}
if (process.argv.includes('--write')) {
  for (const [name, schema] of Object.entries(contracts)) writeFileSync(fileURLToPath(new URL(`../../docs/spec/schemas/home-preview-${name}.schema.json`, import.meta.url)), JSON.stringify(documentSchema(name, schema), null, 2) + '\n')
  const match = sampleMatches[0]!
  const scenarios = Object.fromEntries(['ready', 'partial', 'previous', 'pending', 'failed', 'unavailable', 'facts'].map(state => [state, buildMockResponse(match, state, ['pending', 'failed', 'unavailable'].includes(state) ? null : buildMockPreview(match, state))]))
  writeFileSync(fileURLToPath(new URL('../src/mocks/home-preview/responses.json', import.meta.url)), JSON.stringify(scenarios, null, 2) + '\n')
  writeFileSync(fileURLToPath(new URL('../src/mocks/home-preview/recommendations.json', import.meta.url)), JSON.stringify(buildMockRecommendations(sampleMatches, sampleDay).response, null, 2) + '\n')
}

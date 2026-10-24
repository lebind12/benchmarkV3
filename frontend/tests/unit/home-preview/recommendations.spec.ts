import { describe, expect, it } from 'vitest'
import { rank, sampleDay, sampleMatches, selectRecommendations, type Match } from '@/mocks/home-preview/data'

describe('home recommendation policy', () => {
  it('prioritizes stored ongoing status, keeps every eligible match, and separates results', () => {
    const selected = selectRecommendations(sampleMatches, sampleDay)
    expect(selected.matches.map(m => m.id)).toEqual([90002, 90001, 90003, 90004, 90005, 90006, 90007, 90008, 90009])
    expect(selected.results.map(m => m.id)).toEqual([90010])
  })
  it('uses priority before kickoff, then kickoff and stable ID for ties', () => {
    const first = { ...sampleMatches[0]!, id: 90, time: '23:00' }
    const early = { ...first, id: 92, time: '20:00' }
    const tie = { ...early, id: 91 }
    expect(selectRecommendations([first, early, tie, sampleMatches[2]!], sampleDay).matches.map(m => m.id)).toEqual([91, 92, 90, 90003])
  })
  it('moves to the closest eligible scheduled date when today has only results or ineligible games', () => {
    const todayIneligible: Match = { ...sampleMatches[4]!, round: 'リーグフェーズ' }
    expect(rank(todayIneligible)).toBe(Infinity)
    const selected = selectRecommendations([sampleMatches[9]!, todayIneligible, sampleMatches[10]!], sampleDay)
    expect(selected.day).toBe('2026-10-27')
    expect(selected.matches.map(m => m.id)).toEqual([90011])
    expect(selected.results).toHaveLength(1)
  })
  it('does not infer a final from an unknown round and excludes non-big-six UEL before the final', () => {
    expect(rank({ ...sampleMatches[4]!, round: '미정' })).toBe(Infinity)
    expect(rank({ ...sampleMatches[6]!, round: '4강' })).toBe(Infinity)
  })
  it('deduplicates fixture IDs and handles no future eligible matches', () => {
    expect(selectRecommendations([sampleMatches[0]!, sampleMatches[0]!], sampleDay).matches).toHaveLength(1)
    expect(selectRecommendations([sampleMatches[9]!], sampleDay)).toEqual({ day: sampleDay, matches: [], results: [sampleMatches[9]!] })
  })
})

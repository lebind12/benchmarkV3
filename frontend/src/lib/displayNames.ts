import type { BasicPlayerRef } from '@/lib/api/general'

type NamedEntity = {
  name_ko?: string | null
  short_name_ko?: string | null
  name: string
}

export function displayName(entity: NamedEntity): string {
  return entity.name_ko ?? entity.name
}

export function shortName(entity: NamedEntity): string {
  return entity.short_name_ko ?? entity.name_ko ?? entity.name
}

export function leagueName(league: NamedEntity | null): string {
  return league ? displayName(league) : '-'
}

export function teamName(team: NamedEntity | null): string {
  return team ? displayName(team) : '-'
}

export function playerName(player: BasicPlayerRef | NamedEntity | null): string {
  return player ? displayName(player) : '-'
}

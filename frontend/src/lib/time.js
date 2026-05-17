const UTC8_OFFSET_MS = 8 * 60 * 60 * 1000

export function toUTC8(isoString) {
  if (!isoString) return ''
  const d = new Date(isoString)
  if (isNaN(d.getTime())) return ''
  const utc8 = new Date(d.getTime() + UTC8_OFFSET_MS)
  return utc8.toISOString().slice(11, 19)
}

export function toUTC8Full(isoString) {
  if (!isoString) return ''
  const d = new Date(isoString)
  if (isNaN(d.getTime())) return ''
  const utc8 = new Date(d.getTime() + UTC8_OFFSET_MS)
  return utc8.toISOString().slice(0, 19).replace('T', ' ')
}

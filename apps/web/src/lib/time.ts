/** Every time shown in the console is Indian Standard Time, whatever the
 * browser's own timezone — a jury laptop, a cloud desktop or a developer
 * machine set to UTC must show the same clock as the officers' radios and the
 * Movement Report. Formatting stays locale-aware (en/hi/gu). */

export const IST_TIME_ZONE = 'Asia/Kolkata'

type Input = string | number | Date

function toDate(value: Input): Date {
  return value instanceof Date ? value : new Date(value)
}

/** Date and time, e.g. "12 Oct, 14:05". */
export function formatIst(value: Input, language?: string, options: Intl.DateTimeFormatOptions = {}): string {
  const date = toDate(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString(language, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    ...options,
    timeZone: IST_TIME_ZONE,
  })
}

/** Time only, e.g. "14:05". */
export function formatIstTime(value: Input, language?: string, options: Intl.DateTimeFormatOptions = {}): string {
  const date = toDate(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleTimeString(language, { hour: '2-digit', minute: '2-digit', ...options, timeZone: IST_TIME_ZONE })
}

/** Date only, e.g. "12 Oct 2026". */
export function formatIstDate(value: Input, language?: string, options: Intl.DateTimeFormatOptions = {}): string {
  const date = toDate(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString(language, { ...options, timeZone: IST_TIME_ZONE })
}

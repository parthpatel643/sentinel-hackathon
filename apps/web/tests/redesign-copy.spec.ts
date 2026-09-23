import { expect, test } from '@playwright/test'
import { commandCopy } from '../src/locales/command'
import { investigationCopy } from '../src/locales/investigation'
import { monitoringCopy } from '../src/locales/monitoring'
import { managementCopy } from '../src/locales/management'

function flatten(value: object, prefix = ''): Record<string, string> {
  return Object.fromEntries(Object.entries(value).flatMap(([key, child]) =>
    typeof child === 'string' ? [[`${prefix}${key}`, child]] : Object.entries(flatten(child, `${prefix}${key}.`)),
  ))
}

for (const [name, copy] of Object.entries({ command: commandCopy, investigation: investigationCopy, monitoring: monitoringCopy, management: managementCopy })) {
  test(`${name} redesign copy is complete in all three languages`, () => {
    const source = flatten(copy.en)
    expect(Object.keys(source).length).toBeGreaterThan(0)
    for (const locale of [copy.hi, copy.gu]) {
      const translated = flatten(locale)
      expect(Object.keys(translated).sort()).toEqual(Object.keys(source).sort())
      for (const key of Object.keys(source)) {
        expect(translated[key].trim(), key).not.toBe('')
        expect(translated[key].match(/{{[^}]+}}/g)?.sort() ?? [], key).toEqual(source[key].match(/{{[^}]+}}/g)?.sort() ?? [])
      }
    }
  })
}

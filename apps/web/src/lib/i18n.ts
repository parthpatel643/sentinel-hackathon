import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from '../locales/en/translation.json'
import hi from '../locales/hi/translation.json'
import gu from '../locales/gu/translation.json'

export const SUPPORTED_LANGUAGES = ['en', 'hi', 'gu'] as const
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number]

const STORAGE_KEY = 'sentinel-language'

function readStoredLanguage(): SupportedLanguage {
  const stored = localStorage.getItem(STORAGE_KEY)
  return (SUPPORTED_LANGUAGES as readonly string[]).includes(stored ?? '') ? (stored as SupportedLanguage) : 'en'
}

i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    hi: { translation: hi },
    gu: { translation: gu },
  },
  lng: readStoredLanguage(),
  fallbackLng: 'en',
  interpolation: {
    escapeValue: false,
  },
})

i18n.on('languageChanged', (lng) => {
  localStorage.setItem(STORAGE_KEY, lng)
  document.documentElement.lang = lng
})
document.documentElement.lang = i18n.language

export default i18n

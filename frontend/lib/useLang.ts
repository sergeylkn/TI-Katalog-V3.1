'use client'
import { useState, useEffect } from 'react'
import type { Lang } from './translations'

const KEY = 'ti_lang'

export function useLang(): [Lang, (l: Lang) => void] {
  const [lang, setLangState] = useState<Lang>('ua')

  useEffect(() => {
    const saved = localStorage.getItem(KEY) as Lang | null
    if (saved === 'ua' || saved === 'pl') setLangState(saved)
  }, [])

  const setLang = (l: Lang) => {
    localStorage.setItem(KEY, l)
    setLangState(l)
    // Dispatch event so all components update
    window.dispatchEvent(new CustomEvent('langchange', { detail: l }))
  }

  useEffect(() => {
    const handler = (e: Event) => {
      const l = (e as CustomEvent).detail as Lang
      setLangState(l)
    }
    window.addEventListener('langchange', handler)
    return () => window.removeEventListener('langchange', handler)
  }, [])

  return [lang, setLang]
}

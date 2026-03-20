import { Suspense } from 'react'
import SearchInner from './SearchInner'

export default function SearchPage() {
  return (
    <Suspense fallback={<div style={{ padding: 60, textAlign: 'center', color: 'var(--text3)' }}>Завантаження...</div>}>
      <SearchInner />
    </Suspense>
  )
}

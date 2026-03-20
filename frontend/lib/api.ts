const API = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '')

export interface Category {
  id: number; name: string; slug: string
  icon: string; description: string
  product_count: number; section_count: number
}
export interface Section {
  id: number; name: string; slug: string
  category_id: number; description: string; product_count: number
}
export interface Product {
  id: number; title: string; subtitle: string; sku: string
  description: string; certifications: string
  attributes: Record<string, string>
  variants: Record<string, string>[]
  image_url: string; image_bbox: any
  page_number: number | null
  document_id: number; section_id: number | null; category_id: number | null
  document_url: string
}
export interface SearchResult extends Product {
  _score: number; _match: string
}

async function req<T>(path: string, opts?: RequestInit): Promise<T> {
  const r = await fetch(`${API}${path}`, {
    ...opts,
    headers: { 'Content-Type': 'application/json', ...opts?.headers }
  })
  if (!r.ok) throw new Error(`${r.status} ${path}`)
  return r.json()
}

export const api = {
  // Categories
  getCategories: () => req<Category[]>('/api/documents/categories'),
  getCategory:   (slug: string) => req<Category & {sections: Section[]}>(`/api/documents/categories/${slug}`),

  // Products
  getProducts: (p = 1, ps = 24, section_id?: number, category_id?: number) => {
    const params = new URLSearchParams({ page: String(p), page_size: String(ps) })
    if (section_id) params.set('section_id', String(section_id))
    if (category_id) params.set('category_id', String(category_id))
    return req<{ total: number; items: Product[] }>(`/api/products/?${params}`)
  },
  getProductsBySection: (ref: string, p = 1, ps = 24) =>
    req<{ total: number; section: Section; items: Product[] }>(
      `/api/products/section/${ref}?page=${p}&page_size=${ps}`
    ),
  getProduct:      (id: number) => req<Product>(`/api/products/${id}`),
  recommendations: (id: number) => req<{ recommendations: Product[] }>(`/api/products/${id}/recommendations`),
  imageUrl:        (id: number) => `${API}/api/products/${id}/image`,

  // Search
  search: (q: string, p = 1, ps = 20, section_id?: number, category_id?: number) => {
    const params = new URLSearchParams({ q, page: String(p), page_size: String(ps) })
    if (section_id) params.set('section_id', String(section_id))
    if (category_id) params.set('category_id', String(category_id))
    return req<{ total: number; items: SearchResult[]; params_detected: any; vector_used: boolean }>(
      `/api/search/?${params}`
    )
  },
  suggest: (q: string) => req<{ suggestions: { id: number; title: string; sku: string }[] }>(
    `/api/search/suggest?q=${encodeURIComponent(q)}`
  ),

  // Chat
  chat: (message: string, history: any[]) =>
    req<{ reply: string; rag_used: boolean }>('/api/chat/', {
      method: 'POST',
      body: JSON.stringify({ message, history })
    }),

  // Admin
  setApiKey:    (key: string) => req<any>('/api/admin/set-api-key', { method: 'POST', body: JSON.stringify({ api_key: key }) }),
  getApiKey:    () => req<{ has_key: boolean }>('/api/admin/get-api-key'),
  importAll:    () => req<any>('/api/admin/import-all-pdfs', { method: 'POST' }),
  importStatus: () => req<any>('/api/admin/import-status'),
  importLogs:   (n = 50) => req<any>(`/api/admin/import-logs?limit=${n}`),
  parseLogs:    (n = 50) => req<any>(`/api/admin/parse-logs?limit=${n}`),
  clearDatabase: () => req<any>('/api/admin/clear-database', { method: 'POST' }),
  envStatus:    () => req<any>('/api/admin/env-status'),
}

# 🚀 TI-Katalog v3.1 Deployment Guide

## Prerequisites

- Docker & Docker Compose
- PostgreSQL 13+
- R2 Storage (Cloudflare)
- Claude API Key (Anthropic)

## Setup

### 1. Environment Variables

Create `.env` файл в корне проекту:

```bash
# Database
DATABASE_URL=postgresql://ti_user:ti_password@postgres:5432/ti_katalog

# APIs
ANTHROPIC_API_KEY=sk-ant-xxxxx
OPENAI_API_KEY=sk-xxxxx (optional)

# R2 Storage
R2_BUCKET_URL=https://pub-ada201ec5fb84401a3b36b7b21e6ed0f.r2.dev
```

### 2. Docker Deployment

```bash
# Rebuild without cache
docker-compose build --no-cache

# Start services
docker-compose up -d

# Check logs
docker-compose logs -f backend
```

### 3. Access

- **API**: http://localhost:8000
- **Docs**: http://localhost:8000/docs
- **Admin Panel**: http://localhost:3000/admin
- **Frontend**: http://localhost:3000

## API Endpoints

### Admin
- `GET /api/admin/env-status` — Environment configuration
- `GET /api/admin/import-status` — Import progress
- `GET /api/admin/index-stats` — Product statistics
- `POST /api/admin/import-all-pdfs` — Start background import
- `POST /api/admin/clear-database` — Clear all data
- `GET /api/admin/live-log` — Live event stream (SSE)
- `GET /api/admin/parse-logs` — Parse logs (JSON)

### Documents
- `GET /api/documents/categories` — List categories
- `GET /api/documents/categories/{slug}` — Get category with sections
- `GET /api/documents/` — List documents
- `GET /api/documents/{id}` — Get document

### Products
- `GET /api/products/` — List products (paginated)
- `GET /api/products/{id}` — Get product details
- `GET /api/products/{id}/image` — Get product image from PDF
- `GET /api/products/section/{slug}` — Get products by section

### Search
- `GET /api/search/?q=...` — Full-text search
- `GET /api/search/suggest?q=...` — Search suggestions

### Chat
- `POST /api/chat/` — AI product recommendations

## Troubleshooting

### Issue: `ModuleNotFoundError: No module named 'database'`
**Solution**: Make sure Docker is rebuilt with `--no-cache`

### Issue: Admin logs not showing
**Solution**: Check SSE connection - browser console for errors

### Issue: PDF extraction failing
**Solution**: Ensure ANTHROPIC_API_KEY is set and valid

## Database Migrations

Tables are auto-created on first startup via `init_db()` in lifespan handler.

Schema:
- `categories` — Product categories
- `sections` — Category sections
- `documents` — PDF documents
- `products` — Extracted products
- `import_logs` — Import history
- `parse_logs` — Parse event logs

## Performance Tips

1. Use read replicas for search queries
2. Enable Redis cache for categories
3. Adjust `pool_size` in DATABASE_URL for high concurrency
4. Consider async PDF processing for large files

## Support

For issues: https://github.com/sergeylkn/TI-Katalog-V3.1/issues

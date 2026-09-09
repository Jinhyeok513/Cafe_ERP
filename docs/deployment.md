# Deployment

The repository is configured as a Vercel Services project:

| Service | Entrypoint | Route prefix |
|---|---|---|
| Next.js operations UI | `apps/web` | `/` |
| FastAPI operations API | `backend/main.py` | `/backend` |

The Python package lives under `backend/src` so it is bundled inside the independent backend service. FastAPI retains its existing `/api/*` routes, so its deployed health endpoint is `/backend/api/health`. The web service resolves the current production alias from `VERCEL_PROJECT_PRODUCTION_URL`; local development continues to use `CAFE_API_URL`, which takes precedence when provided.

## Required environment

Set `DATABASE_URL` for Preview and Production to a pooled PostgreSQL connection string. `DATABASE_POOL_MAX_SIZE` is optional and defaults to `5`.

Do not commit database credentials. Provision PostgreSQL through a Vercel Marketplace integration such as Neon, then apply every file in `db/migrations` and `db/seeds` before loading a generated scenario with `cafe-load-dataset`.

## Project setup

1. Import `Jinhyeok513/Cafe_ERP` as a Vercel project.
2. Set the Framework Preset to **Services**.
3. Attach PostgreSQL and confirm `DATABASE_URL` is available to the backend service.
4. Apply migrations, seed reference data and load the selected synthetic scenario.
5. Deploy and verify `/backend/api/health`, `/`, `/reorder`, `/pos-usage`, `/forecast` and `/reports`.

The GitHub Actions workflow runs the same database and application checks on every push and pull request. Vercel Git integration can create preview deployments from pull requests and production deployments from `main` after the project is linked.

## Provisioned production resources

- Vercel project: `cafe-erp` on the T_AIM Hobby team
- Production URL: `https://cafe-erp-gamma.vercel.app`
- Production deployment protection: public; preview deployment protection remains available through Vercel
- Database: Neon Free in Sydney (`syd1`)
- Database environments: Production and Preview
- Runtime variable: `DATABASE_URL`
- Neon Auth: disabled because application authentication is outside this prototype's scope
- Loaded dataset: deterministic 30-day `errors` scenario with no data-quality issues

The database resource is intentionally separate from the repository. Its credentials remain in Vercel-managed environment variables and are never committed.

# Sample Application — Reference for Test Authors

"Sample Shop Admin": FastAPI + SQLite + server-rendered pages. It is the system under
test for every UI, API and integration test in this repository.

## Run it

```bash
uv run python -m sample_application --env test             # http://127.0.0.1:8000
uv run python -m sample_application --env test --reset-db  # wipe + reseed first
```
or `scripts/run_app.ps1` / `scripts/run_app.sh`. Swagger UI: <http://127.0.0.1:8000/docs>.

| Variable | Default | Purpose |
|---|---|---|
| `APP_ENV` | `dev` | `test` enables `POST /api/v1/test-support/reset` |
| `APP_DATABASE_URL` | `sqlite:///sample_application/database/app.db` | DB location |
| `APP_JWT_SECRET` | random per start | JWT signing key |
| `APP_TOKEN_TTL_MINUTES` | `60` | token lifetime |
| `FW_CREDENTIALS__ADMIN_* / USER_*` | — (required) | seeded admin / standard user (same values the framework uses) |

## Seed data (reference data — read, don't modify)

* Users: admin, standard user, `grace.hopper@example.test`, `alan.turing@example.test`,
  `disabled.user@example.test` (inactive). 5 users in total.
* 15 products across 6 categories (Books, Clothing, Electronics, Home, Sports, Toys);
  SKUs `EL-1001`…`TY-6002`; 2 are out of stock (`EL-1003`, `BK-2003`); 5 have stock < 5.

Tests that change data must **create their own records** (unique values via Faker) and clean up.

## Authentication

`POST /api/v1/auth/login` returns `{access_token, token_type, expires_in, user}` **and** sets the
HTTP-only cookie `access_token`. Every endpoint/page accepts either the
`Authorization: Bearer <token>` header or that cookie.
→ An integration test can log in via API and add the cookie to the browser context.

Roles: `admin` (everything) and `user` (no user management).

## REST API (`/api/v1`)

| Method & path | Auth | Success | Notable errors |
|---|---|---|---|
| `GET /health` | – | 200 | |
| `POST /auth/login` | – | 200 | 401 `invalid_credentials`, 403 `account_disabled`, 422 |
| `POST /auth/register` | – | 201 | 409 `duplicate_email`, 422 |
| `POST /auth/logout` | – | 204 | |
| `GET /auth/me` | user | 200 | 401 `not_authenticated` / `invalid_token` |
| `GET /users?q&role&page&size` | admin | 200 page | 403 |
| `POST /users` | admin | 201 + `Location` | 409, 422 |
| `GET /users/{id}` | admin or self | 200 | 403, 404 |
| `PUT /users/{id}` | admin | 200 | 400 `self_lockout`, 404, 409, 422 |
| `PATCH /users/{id}` | admin | 200 | 400 `empty_patch` / `self_lockout`, 404, 409, 422 |
| `DELETE /users/{id}` | admin | 204 | 400 `self_delete`, 404 |
| `GET /products?q&category&min_price&max_price&in_stock&sort&page&size` | user | 200 page | 422 |
| `GET /products/categories` | user | 200 | |
| `POST /products` | user | 201 + `Location` | 409 `duplicate_sku`, 422 |
| `GET/PUT/PATCH/DELETE /products/{id}` | user | 200/200/200/204 | 404, 409, 422 |
| `GET/PUT /profile` | user | 200 | 422 |
| `POST /profile/password` | user | 204 | 400 `wrong_password`, 422 |
| `POST /profile/avatar` (multipart `file`) · `GET /profile/avatar` | user | 200 | 413, 415, 404 |
| `GET /notifications?delay_ms=0..5000` | user | 200 (after delay) | 422 |
| `POST /test-support/reset` | – (`APP_ENV=test` only) | 204 | 404 otherwise |

Paged responses: `{items, total, page, size, pages}` - `items` and `total` always come from the
same database snapshot (one query). Sorts: `name_asc` (default),
`name_desc`, `price_asc`, `price_desc`, `newest`. Page size 1–100 (default 10 for products, 20 for users).

**Error body** (every API error):
```json
{"detail": "Validation failed", "code": "validation_error", "correlation_id": "…",
 "errors": [{"field": "price", "message": "Price must be a number"}]}
```
Every response carries `X-Correlation-ID` (echoed if the client sent one) and `X-Response-Time-ms`.

## Validation rules (identical in UI and API)

| Field | Rule | Message examples |
|---|---|---|
| email | valid format, ≤120, stored lower-case, unique | `Enter a valid email address`, `A user with this email already exists` |
| full_name | 2–60 chars | `Full name is required`, `Full name must be at least 2 characters` |
| password | 8–64 chars, ≥1 letter and ≥1 digit | `Password must contain at least one letter and one number` |
| phone | optional, `+`, digits, spaces, dashes (7–20) | `Enter a valid phone number …` |
| product name | 2–80 chars | `Name is required` |
| sku | 3–20, `A-Z 0-9 -`, upper-cased, unique | `SKU must be 3-20 characters: letters, digits or dashes` |
| category | one of the 6 categories | `Category must be one of: …` (API) / `Category is required` (UI) |
| price | > 0, ≤ 100000, max 2 decimals | `Price must be greater than 0`, `Price can have at most 2 decimal places` |
| stock | integer 0–100000 (default 0) | `Stock must be at least 0`, `Stock must be a whole number` |
| description | optional, ≤500 | |

Unknown JSON fields are rejected (`Unknown field 'x'`). A body that is not valid JSON gives
`{"field": "body", "message": "Request body is not valid JSON"}`.

Ids are **never reused** after a delete (SQLite `AUTOINCREMENT`), so a stale id always returns 404.

## Web pages & test hooks

Locate by role/label first (all inputs have `<label for>`; buttons and links have text);
`data-testid` exists as a stable fallback.

| Page | URL | Highlights / hooks |
|---|---|---|
| Login | `/login` | errors `email-error`, `password-error`; `login-error` (role=alert); `?next=` honoured (local paths only) |
| Register | `/register` | `confirm_password` must match |
| Dashboard | `/dashboard` | `welcome-message`, `stat-users`, `stat-products`, `stat-low-stock`, `stat-categories` |
| Users (admin) | `/users`, `/users/new`, `/users/{id}/edit` | rows `user-row[data-user-id]`; delete → JS `confirm()` dialog; non-admin gets 403 page |
| Products | `/products`, `/products/new`, `/products/{id}`, `/products/{id}/edit` | filters form (search, category, min/max price, in stock, sort); rows `product-row[data-sku]`; `results-count`; `empty-state`; pagination; **View opens a new tab**; delete → `confirm()` |
| Profile | `/profile` | details form, change password, **avatar upload** (`avatar-input`, `avatar-image`) |
| Tools | `/tools` | **CSV download** (`export-link`), **CSV upload** (`import-input` → `import-summary` / `import-errors`), **iframe** (`help-frame`, title "Help center"), **popup** ("Open help in new window"), **dynamic list** ("Load notifications" → `notification-item` after ~1.5 s; ids are random on purpose) |
| Flash messages | any | `flash-message` (role=status) after create/update/delete |
| Errors | any | `error-page`, `error-message`; anonymous access redirects to `/login?next=…` |

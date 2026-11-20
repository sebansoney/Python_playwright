# UI + API Integration Testing Guide

Integration tests prove that the two channels of the application agree: what one layer
writes, the other layer reads correctly - and that one login works in both.

```bash
uv run pytest tests/integration                 # all integration tests
uv run pytest -m "integration and smoke"        # the 7 critical cross-layer flows
uv run pytest tests/integration -n 4 --browser firefox
```

## Pattern: set up in one layer, act in the other, verify in the first

| Test | Setup | Act | Verify |
|---|---|---|---|
| `test_api_created_user_is_visible_in_ui_and_can_log_in` | - | API `POST /users` | UI users table + UI login with the API-set password |
| `test_ui_created_product_is_verified_via_api` | - | UI "Add product" form | API list/search: every field, schema, `created_by_id` |
| `test_api_user_update_is_reflected_in_ui` | factory | API `PATCH /users/{id}` (name, role, deactivate) | UI table; UI login refused for the deactivated user |
| `test_api_product_update_is_reflected_in_ui` | factory | API `PATCH /products/{id}` | UI table + detail page (new tab) |
| `test_ui_user_delete_is_verified_via_api` / `test_ui_product_delete_is_verified_via_api` | factory | UI delete + confirm dialog | API `GET` -> 404, search empty |
| `test_ui_registration_creates_account_usable_via_api` | - | UI registration | API login + admin search |
| `test_csv_export_matches_api_data` | factory | UI CSV download | row equals API representation |
| `test_validation_rules_are_identical_in_ui_and_api` (×5) | - | same invalid input to form and API | same message at both layers |
| `test_api_login_session_is_reused_in_browser` | factory | API login | browser opens dashboard with that token, no login screen |
| `test_browser_login_session_is_reused_for_api` | factory | UI login | cookie token works as API Bearer token |
| `test_ui_logout_ends_browser_session_but_issued_token_stays_valid` | factory | UI logout | cookie gone; token still valid (documents N10) |
| `test_profile_change_in_ui_is_visible_via_api` | factory | UI profile form | API `GET /profile` |

## Rules

1. **Setup via factories (backdoor), verification via `api` / `user_api`.** Verification
   calls are part of the test's evidence (`api_log` -> report section on failure); setup
   traffic is not.
2. **Register cleanup before the UI creates data** (`cleanup.add(..., delete_by_sku/email)`)
   - the id is unknown until the API finds it.
3. **Verify all fields, not just existence**, and validate the contract (`matches_schema`)
   when the API reads data the UI wrote.
4. **Search by unique keys** (SKU, email) - never rely on positions or totals of shared lists.

## Session sharing helpers

```python
from framework.browser.session import storage_state_for_token, token_from_context

page = page_for_token(token)                 # fixture: API token -> logged-in page
token = token_from_context(page.context)     # browser cookie -> API token
api_session(token=token).auth.me()           # use it on the API
```
This works because the app accepts the same JWT as `Authorization: Bearer` or as the
HTTP-only `access_token` cookie.

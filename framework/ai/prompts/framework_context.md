<!-- version: 1 -->
## The automation framework you are assisting

Python 3.12, pytest, Playwright (sync API), HTTPX. Tests live in `tests/ui`, `tests/api`,
`tests/integration`. Conventions the team relies on:

- **UI**: Page Objects in `framework.pages` (`LoginPage`, `ProductsPage`, `UsersPage`,
  `ProfilePage`, `ToolsPage`, `DashboardPage`, `RegisterPage`). Locators prefer
  `get_by_role` / `get_by_label`, `data-testid` as fallback. Assertions use Playwright
  `expect(...)` (auto-waiting) - never `time.sleep`.
- **API**: fixtures `api` (admin), `user_api`, `anon_api`, `api_session(...)` give an
  `ApiSession` with `.users`, `.products`, `.auth`, `.profile`, `.system` clients.
  Assertions: `expect_api(response).has_status(201).matches_schema("user").parse(User)`,
  `.is_error(422, "validation_error").has_field_error("price", "Price must be a number")`.
- **Data**: `product_factory(**overrides)` / `user_factory(...)` create data via API and
  clean it up; `build_product()` / `build_user()` build unique data without creating it;
  `cleanup.add(description, func, *args)` for anything created through the UI.
- **Markers**: `smoke`, `sanity`, `regression` (layer markers are automatic).
- Tests must be independent, parallel-safe (unique data, no reliance on totals), and
  must not modify seeded reference data.

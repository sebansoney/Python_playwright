# UI Testing Guide

How the Playwright UI layer is built and how to add tests to it.

## Running

```bash
uv run pytest tests/ui                                   # chromium (config default)
uv run pytest tests/ui --browser firefox --browser webkit
uv run pytest tests/ui --headed --slowmo 300             # watch it
uv run pytest tests/ui -n 4                              # parallel
uv run pytest -m smoke                                   # smoke suite (UI + later API)
uv run pytest tests/ui -k delete --tracing on            # always keep a trace
uv run playwright show-trace reports/playwright/<test>/trace.zip
```
The sample app is **started automatically** if it is not already running (and stopped
at the end of the run). An app you started yourself is reused and left running.

Defaults come from `config/config.yaml` → `browser:`; any pytest-playwright CLI flag
(`--browser`, `--headed`, `--slowmo`, `--tracing`, `--video`, `--screenshot`, `--output`)
overrides them for that run.

## Fixtures you will use

| Fixture | What you get |
|---|---|
| `page` | Fresh, **anonymous** page (own browser context) |
| `admin_page` / `user_page` | Page already **logged in** (session cookie injected - no login UI) |
| `page_for(email, password)` | Logged-in page for any account (e.g. one you just created) |
| `product_factory(**overrides)` / `user_factory(...)` | Creates data **via API**, auto-deleted after the test. Returns `(input_data, api_response)` |
| `backdoor` | API helper for setup/verification (`find_product`, `get_user`, `delete_*`) |
| `cleanup` | Register your own undo actions: `cleanup.add("why", func, *args)` |
| `settings` | Typed configuration (credentials via `settings.credentials.require("admin")`) |

## Writing a test - the pattern

```python
@pytest.mark.smoke
def test_edit_product(admin_page, product_factory, backdoor):
    product, created = product_factory(price=10.0)  # Arrange: precondition via API
    products = ProductsPage(admin_page).open().search(product.sku)

    form = products.open_edit(product.sku)  # Act: only the behaviour under test
    form.form.fill("Price", "12.99")
    form.save()

    products.flash.expect_text("Product updated successfully.")  # Assert: UI ...
    assert backdoor.get_product(created["id"])["price"] == 12.99  # ... and stored state
```

Rules:
1. **Create your own data** (factories) - never modify seed users/products. Unique tokens make tests parallel-safe.
2. **Register cleanup before asserting** when a test creates data through the UI
   (`cleanup.add(..., backdoor.delete_product_by_sku, sku)`), so failures don't leak data.
3. **No sleeps.** Use `expect(...)` (auto-retries up to `browser.expect_timeout_ms`).
4. For lists shared with other tests, assert **properties** ("every row is Electronics"),
   not exact totals - another worker may add rows at the same time.
5. Assertions about *business outcomes* live in the test; page objects provide actions,
   locators and small `expect_*` helpers.

## Locator strategy (in order of preference)

1. `get_by_role(role, name=...)` - buttons, links, headings, rows, cells, dialogs
2. `get_by_label("Email", exact=True)` - form fields (labels never contain the `*` marker)
3. `get_by_text(...)` - static text
4. `get_by_test_id(...)` - stable fallback (`data-testid`), e.g. flash message, counters
5. CSS - last resort (only `iframe[title=...]` today)

Never use generated ids (the notifications demo has random ids on purpose).

Validation errors: `Form.expect_error("Email", "Email is required")` checks the field is
`aria-invalid` **and** that its accessible description (via `aria-describedby`) is the
message - this is stable and also verifies accessibility.

## Building blocks

```
framework/
├── components/   Form, DataTable, NextDialog (JS confirm/alert), NavBar, FlashMessage
├── pages/        BasePage + one class per screen (LoginPage, ProductsPage, ...)
├── fixtures/     app (autostart), browser (contexts, auth), data (factories, cleanup)
└── data/         factories (Faker), backdoor (API setup), cleanup registry
```

Special interactions (see `tests/ui/test_ui_capabilities.py`):

| Need | How |
|---|---|
| Download | `with page.expect_download() as d: click` → `d.value.save_as(path)` (`ToolsPage.export_products`) |
| Upload | `locator.set_input_files(path)` (`ToolsPage.import_products`, `ProfilePage.upload_avatar`) |
| iframe | `page.frame_locator("iframe[title='Help center']")` then normal locators |
| Popup / new tab | `with page.expect_popup() as p: click` → `p.value` (`ProductsPage.view_in_new_tab`) |
| JS confirm | `NextDialog(page, accept=True)` **before** the click; read `.message` after |
| Form submit that may keep the same URL | `BasePage.submit_and_wait(action)` |

## Failure artifacts

On failure (config defaults): screenshot + Playwright trace in `reports/playwright/<test>/`.
Video is off locally, on-failure in CI. The folder is cleared at the start of every run.

**Security note:** setup/auth API calls are deliberately *not* traced (they carry
passwords). Browser traces still contain the short-lived session cookie and anything typed
into fields (login tests type the test password). Treat `reports/playwright` as sensitive,
use only test accounts, and never upload raw traces to external services.

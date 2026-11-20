# API Testing Guide

How the HTTPX-based API layer is built and how to write API tests with it.

## Running

```bash
uv run pytest tests/api                  # all API tests (app auto-starts)
uv run pytest tests/api -n 4             # parallel
uv run pytest -m "api and smoke"         # API smoke tests
uv run pytest tests/api -k boundaries    # by name
```

## Layers

```
test  ──►  ApiSession (api / user_api / anon_api / api_session(...))
              ├── .auth .users .products .profile .system   resource clients: build requests,
              │                                              return ApiResponse, never assert
              └── .client  ApiClient (HTTPX)                 base URL, timeout, auth, correlation id,
                                                             timing, redacted logging, no cookies
assert ──►  expect_api(response)...                          reusable assertions + JSON Schema
            response.parse(Model)                            typed pydantic models
```

| File | Responsibility |
|---|---|
| `framework/api/http_client.py` | `ApiClient`, `ApiResponse` (status, json, `elapsed_ms`, `correlation_id`, `summary()`), `ApiExchangeLog` |
| `framework/api/auth.py` | `TokenProvider` (login once per account, cache until shortly before expiry), `BearerAuth`, `StaticBearerAuth` (negative tests) |
| `framework/api/clients/` | One client per resource, one method per endpoint; `ApiSession` bundles them per identity |
| `framework/api/models.py` | pydantic response models (`User`, `Product`, `Page[T]`, `Token`, `Error`) |
| `framework/api/schemas/*.json` | JSON Schema contracts (Draft 2020-12), cross-referenced with `$ref` |
| `framework/assertions/` | `expect_api(...)` fluent assertions, `schema_errors` / `validate_schema` |

## Fixtures

| Fixture | Identity |
|---|---|
| `api` | seeded **admin** |
| `user_api` | seeded **standard user** |
| `anon_api` | **no credentials** |
| `api_session(role=..., email=..., password=..., token=...)` | any account, or a fixed/invalid token |
| `token_provider` | raw tokens (session-scoped, cached) |
| `api_log` | everything the test sent/received - printed (redacted) in the report on failure |
| `backdoor`, `user_factory`, `product_factory`, `cleanup` | test data setup/cleanup (see UI guide) |

## Writing a test

```python
@pytest.mark.smoke
def test_create_user(api, new_user_payload):
    response = api.users.create(new_user_payload)                       # Act

    user = (expect_api(response)                                         # Assert
            .has_status(201)
            .matches_schema("user")            # contract
            .parse(User))                      # typed object for further checks
    expect_api(response).has_header("Location", f"/api/v1/users/{user.id}")
    assert user.email == new_user_payload["email"]
```

Negative test:
```python
expect_api(api.users.create(payload)) \
    .is_error(422, "validation_error") \
    .has_field_error("email", "Enter a valid email address")
```

### Assertion reference (`expect_api(response)`)

| Method | Checks |
|---|---|
| `has_status(n)` / `is_success()` | status code |
| `has_header(name, value_or_regex)`, `has_content_type()`, `echoes_correlation_id()` | headers |
| `has_json("items.0.sku", value)`, `json_contains({...})`, `has_empty_body()` | body |
| `matches_schema("user")` | JSON Schema contract (all violations listed) |
| `parse(Model)` | pydantic validation, returns typed object (terminal step) |
| `responds_within(ms)` | response time |
| `is_error(status, code)` | status + standard error body schema + machine code |
| `has_detail(text)`, `has_field_error(field, msg)`, `has_field_errors_exactly(*fields)` | error details |

Every failure message ends with the redacted request/response.

## Rules

1. **Clients never assert; tests never build URLs.** Use resource client methods; send
   deliberately broken payloads as plain dicts.
2. **Identity is explicit.** The client stores **no cookies** (a login response sets one
   for browsers - keeping it would silently authenticate later calls). Pick `api`,
   `user_api`, `anon_api` or `api_session(...)`.
3. **Own your data.** Create with factories/fixtures that register cleanup; never modify
   seed data. Assert properties, not global totals, on shared lists (parallel runs).
4. **Boundaries:** test just-below / at / just-above every limit with `parametrize`
   (see `test_price_boundaries`, `test_password_length_boundaries`).
5. **Chaining:** pass ids/tokens from one response into the next call
   (`test_product_crud_lifecycle`, `test_profile_password_change_flow`).
6. **Contract vs. model:** `matches_schema` checks the published contract; `parse(Model)`
   gives typed access. Use both on success responses of the endpoint under test.

## Correlation IDs & timing

Every request carries `X-Correlation-ID` (random, or `client.get(..., correlation_id="x")`).
The app echoes it in the response header, puts it in error bodies and its own log - so a
failing test step can be found in `logs/app_server.log`. `ApiResponse.elapsed_ms` is
measured client-side; slower than `api.slow_response_threshold_ms` logs a warning, and
`responds_within()` turns it into an assertion where timing matters.

# Page Object Model review

POM is the default architecture for UI test suites of any size. Here's what to check.

## Good POM characteristics

- **Encapsulation:** tests don't know selectors. They call `login_page.submit()`, not `page.locator("button.submit").click()`.
- **Navigation returns the next page:** fluent-style `return DashboardPage(self.page)` so test code reads as a flow.
- **Methods represent user intent, not low-level actions:** `login_page.login_as(user)` beats `login_page.fill_email(...)` + `fill_password(...)` + `click_submit(...)` called from the test.
- **No assertions inside POM:** pages *do*, tests *assert*. Exception: internal consistency checks (e.g. `self._assert_loaded()` in `__init__`) are fine.
- **One page = one file.** Not one god-class for the whole app.

## Common POM anti-patterns

### God-object page
One class with 80+ methods covering half the app. Usually means the page should be split into smaller components (header, sidebar, content area) composed into the page.

### Page objects that inherit from `Page`
```python
# BAD
class LoginPage(Page):  # Page is Playwright's Page
    ...
```
Pages *have* a Playwright page, they are not one. Use composition:
```python
class LoginPage:
    def __init__(self, page: Page):
        self.page = page
```

### Selectors as string constants at module level
```python
# Questionable
EMAIL_INPUT = "input[name=email]"
PASSWORD_INPUT = "input[name=password]"

class LoginPage:
    def login(self, email, password):
        self.page.locator(EMAIL_INPUT).fill(email)
```

Works, but loses Playwright's locator semantics. Prefer locators as properties:
```python
class LoginPage:
    def __init__(self, page):
        self.page = page

    @property
    def email_input(self) -> Locator:
        return self.page.get_by_label("Email")
```

### Assertions scattered in tests instead of named methods
```python
# OK but verbose
expect(dashboard.page.locator(".balance")).to_have_text("€100")

# Better — expose a semantic property
class DashboardPage:
    def balance_text(self) -> Locator:
        return self.page.get_by_test_id("balance")

# In test
expect(dashboard.balance_text()).to_have_text("€100")
```

This keeps selectors in the page and tests readable.

### POM method does too much
```python
# BAD — this is a test, not a page method
def complete_checkout(self, user, card, address):
    self.fill_address(address)
    self.fill_card(card)
    self.click_pay()
    assert self.page.url == "/success"  # assertion in POM!
    return OrderConfirmationPage(self.page)
```

Split into atomic steps the test composes, or accept the assertion is a contract of "we got to the next page" and make it explicit (e.g. `return OrderConfirmationPage(self.page).wait_until_loaded()`).

### No `wait_until_loaded()` / `is_loaded()` contract
Page objects should know what "loaded" means for themselves:
```python
class DashboardPage:
    def __init__(self, page):
        self.page = page

    def wait_until_loaded(self):
        expect(self.page.get_by_role("heading", name="Dashboard")).to_be_visible()
        return self
```

Tests use:
```python
dashboard = login_page.login_as(user).wait_until_loaded()
```

This removes race conditions between navigation and first interaction.

## Component objects

For repeated UI elements (nav, modal, toast), create component classes:
```python
class NavBar:
    def __init__(self, page):
        self.page = page
        self.root = page.get_by_role("navigation")

    def open_profile_menu(self):
        self.root.get_by_role("button", name="Profile").click()
        return ProfileMenu(self.page)

class BasePage:
    def __init__(self, page):
        self.page = page
        self.nav = NavBar(page)
```

Flag suites that duplicate header/modal locators across every page.

## Type hints on POM

Fluent chains need proper return types so tests get autocomplete:
```python
def login_as(self, user: User) -> "DashboardPage":
    ...
    return DashboardPage(self.page)
```

In modern Python prefer forward-references in quotes when the class isn't defined yet, or use `from __future__ import annotations` at the top of the file.

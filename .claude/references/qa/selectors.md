# Selector review guide

Playwright's selector priority, from best to worst. When reviewing, flag selectors that skip down the hierarchy without good reason.

## Priority (use this order)

### Tier 1: User-facing (preferred)
These survive refactoring and match how users actually interact with the page.

```python
page.get_by_role("button", name="Submit")
page.get_by_role("textbox", name="Email")
page.get_by_label("Password")
page.get_by_placeholder("Search...")
page.get_by_text("Welcome back")
page.get_by_alt_text("Company logo")
page.get_by_title("Close")
```

**Review tip:** if the app has good accessibility, `get_by_role` works everywhere. If the team avoids it, ask why — often it's because a11y is broken, which is itself worth flagging.

### Tier 2: Test-ids
Explicit contract between dev and QA. Stable across UI changes.

```python
page.get_by_test_id("login-submit")
```

Works out of the box with `data-testid`. Configure a different attribute via `selectors.set_test_id_attribute("data-qa")` if needed.

**Review tip:** test-ids are fine, but if you see `get_by_test_id` where `get_by_role` would work, role is preferred — it also validates accessibility.

### Tier 3: CSS (acceptable with care)
```python
page.locator(".cart-item")
page.locator("#main-nav")
```

OK for:
- Semantic IDs that won't change
- Component-level classes that are clearly intentional

Flag as a concern:
- Deep chains: `.container > .row > .col-6 > div:nth-child(2) > span`
- CSS-in-JS generated classes: `._aX3kL2`, `.css-1abc23`

### Tier 4: XPath (last resort)
```python
page.locator("//div[@class='item']//span[contains(text(), 'Total')]")
```

Flag every XPath. Ask: is there really no better option? Usually there is.

Very rare valid cases:
- Traversing backward (`../`) when no other anchor exists
- Complex text matching that `get_by_text` can't express

## Anti-patterns to flag

### Position-dependent selectors
```python
# BAD — breaks if order changes
page.locator(".product-card").nth(2)
page.locator("tr:nth-child(3) td:nth-child(2)")
```
Use semantic anchors: `get_by_role("row", name="Order #1234")`.

### Text-dependent in multi-locale apps
```python
# BAD — breaks in other locales
page.get_by_text("Submit")
```
If the app is i18n'd, tests should use roles, test-ids, or localized-text helpers. Flag direct Russian/English text selectors in a multi-locale context.

### Locator re-creation in loops
```python
# BAD — re-queries DOM every iteration
for i in range(10):
    page.locator(".item").nth(i).click()

# GOOD — store locator, iterate
items = page.locator(".item")
count = items.count()
for i in range(count):
    items.nth(i).click()
```

### Locator stored on class and reused across pages
```python
# BAD — locator bound to initial page context
class LoginPage:
    def __init__(self, page):
        self.submit = page.locator("button[type=submit]")  # captured once

# GOOD — resolve lazily via property, or store page and create locator in methods
class LoginPage:
    def __init__(self, page):
        self.page = page

    @property
    def submit(self):
        return self.page.get_by_role("button", name="Submit")
```

Actually Playwright locators *are* lazy (they don't resolve until used), so the first pattern works for most cases. But if the `page` reference changes (rare), stored locators break. More important reason to prefer the property pattern: it reads better in POM and allows parametrization.

### `.locator()` with combined syntax when chainable is clearer
```python
# Cryptic
page.locator(".form >> input[name=email]")

# Clearer
page.locator(".form").locator("input[name='email']")
# or better
page.locator(".form").get_by_role("textbox", name="Email")
```

## What to say in review

Bad review: "Use better selectors."

Good review: "Line 42: `page.locator('button.btn.btn-primary.submit-btn')` is brittle — those CSS classes are styling concerns that change. Use `page.get_by_role('button', name='Отправить')` instead."

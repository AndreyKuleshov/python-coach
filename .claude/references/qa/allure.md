# Allure review

Allure is only useful if annotations add information. Decoration without meaning is just noise.

## Minimum viable annotations per test

```python
@allure.epic("Checkout")
@allure.feature("Payment")
@allure.story("Successful card payment")
@allure.severity(allure.severity_level.CRITICAL)
@allure.tag("smoke", "regression")
def test_pay_with_card(checkout_page):
    with allure.step("Fill card details"):
        checkout_page.fill_card(TEST_CARD)
    with allure.step("Submit payment"):
        checkout_page.submit()
    with allure.step("Verify success screen"):
        expect(checkout_page.success_message).to_be_visible()
```

## What to check

### Epic / Feature / Story hierarchy
- Is there a consistent taxonomy across the suite, or does every author invent their own?
- Flag: `@allure.epic("Tests")`, `@allure.feature("test")`, `@allure.story(test.__name__)` — all meaningless.
- Good: hierarchy mirrors product areas (Epic = product domain, Feature = functional area, Story = specific scenario).

### Severity used meaningfully
Allure has: `BLOCKER`, `CRITICAL`, `NORMAL` (default), `MINOR`, `TRIVIAL`.
- If every test is `CRITICAL` — severity is useless.
- If severity is never set — suite can't be filtered by `--allure-severities=blocker,critical`.

### Steps inside POM
The most valuable Allure feature. Every significant POM method should be a step:
```python
class CheckoutPage:
    @allure.step("Fill card: {card.number_masked}")
    def fill_card(self, card: Card):
        self.page.get_by_label("Card number").fill(card.number)
        ...
```

The `{card.number_masked}` interpolation makes the Allure report self-documenting. Tests written like this produce reports you can read without the code.

**Review signal:** if POM methods don't have `@allure.step`, the report will show just "test_pay_with_card: passed" with no breakdown. Flag this.

### Screenshots / videos / traces on failure
Don't scatter `allure.attach(page.screenshot())` through test code. Use a hook:

```python
# conftest.py
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.failed:
        page = item.funcargs.get("page")
        if page:
            allure.attach(
                page.screenshot(),
                name="screenshot",
                attachment_type=allure.attachment_type.PNG,
            )
```

Better: configure Playwright tracing and attach the trace on failure:
```python
# pytest-playwright has --tracing retain-on-failure
# plus a hook to attach the resulting trace zip
```

Flag: tests that manually screenshot on every step pollute the report; tests that never screenshot on failure leave failures undebuggable.

### Test IDs / links to issue tracker
```python
@allure.id("JIRA-1234")
@allure.link("https://jira.example.com/browse/PAY-42", name="PAY-42")
@allure.testcase("https://testrail.example.com/cases/42", name="TC-42")
```

Good for traceability. Don't require them on every test, but flag suites that never link back to requirements — review comment: "worth adding `@allure.link` to connect these tests to PAY-42."

### `allure.dynamic` for parametrized tests
Static decorators run once, so for parametrized tests the title/story is the same for all variants. Use `allure.dynamic` inside the test:
```python
@pytest.mark.parametrize("user_type", ["premium", "trial", "expired"])
def test_subscription_banner(page, user_type):
    allure.dynamic.title(f"Subscription banner for {user_type} user")
    ...
```

### Over-decoration
Flag tests with 8+ decorators where half are duplicates (e.g. `@allure.tag("smoke")` + `@pytest.mark.smoke` + `@allure.label("suite", "smoke")`). Pick one convention.

## Configuration checks

- `pytest.ini` / `pyproject.toml` has `addopts = --alluredir=./allure-results`?
- `.gitignore` excludes `allure-results/` and `allure-report/`?
- CI uploads `allure-results` as artifact, renders in Allure TestOps / GitLab pages?

Not part of code review per se, but worth calling out in the "What's good / suggested" section if missing.

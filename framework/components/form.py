"""Generic form component: fill fields by their visible label, read inline errors.

Locator strategy: fields are found by accessible label (``get_by_label``), the same
way a user finds them. Inline validation errors are linked to their field with
``aria-describedby``, so ``expect_error`` asserts the field's *accessible
description* - robust against layout/CSS changes and good accessibility hygiene.
"""

from __future__ import annotations

from playwright.sync_api import Locator, expect


class Form:
    def __init__(self, root: Locator) -> None:
        self.root = root

    def field(self, label: str) -> Locator:
        return self.root.get_by_label(label, exact=True)

    def fill(self, label: str, value: str | float | int | None) -> Form:
        if value is not None:
            self.field(label).fill(str(value))
        return self

    def clear(self, label: str) -> Form:
        self.field(label).clear()
        return self

    def select(self, label: str, option: str | None) -> Form:
        if option is not None:
            self.field(label).select_option(label=option)
        return self

    def set_checked(self, label: str, checked: bool) -> Form:
        self.field(label).set_checked(checked)
        return self

    def submit(self, button: str) -> None:
        self.root.get_by_role("button", name=button, exact=True).click()

    # ---------------------------------------------------------- assertions
    def expect_error(self, label: str, message: str) -> None:
        field = self.field(label)
        expect(field).to_have_attribute("aria-invalid", "true")
        expect(field).to_have_accessible_description(message)

    def expect_no_error(self, label: str) -> None:
        expect(self.field(label)).not_to_have_attribute("aria-invalid", "true")

    def expect_value(self, label: str, value: str) -> None:
        expect(self.field(label)).to_have_value(value)

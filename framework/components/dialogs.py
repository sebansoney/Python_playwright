"""Native JavaScript dialogs (alert / confirm / prompt).

Playwright auto-dismisses dialogs unless a handler is registered, so register the
handler BEFORE the click that opens the dialog::

    dialog = NextDialog(page, accept=True)
    page.get_by_role("button", name="Delete").click()
    assert dialog.message.startswith("Delete product")
"""

from __future__ import annotations

from playwright.sync_api import Dialog, Page


class NextDialog:
    def __init__(self, page: Page, accept: bool = True, prompt_text: str | None = None) -> None:
        self.accept = accept
        self.prompt_text = prompt_text
        self.message: str | None = None
        self.type: str | None = None
        page.once("dialog", self._handle)

    def _handle(self, dialog: Dialog) -> None:
        self.message = dialog.message
        self.type = dialog.type
        if self.accept:
            dialog.accept(self.prompt_text) if self.prompt_text is not None else dialog.accept()
        else:
            dialog.dismiss()

    @property
    def was_shown(self) -> bool:
        return self.message is not None

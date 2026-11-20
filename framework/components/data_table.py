"""Generic HTML table component: rows, cells by column header, row lookup."""

from __future__ import annotations

from playwright.sync_api import Locator, expect


class DataTable:
    def __init__(self, table: Locator) -> None:
        self.table = table

    @property
    def rows(self) -> Locator:
        """Body rows only (header row excluded)."""
        return self.table.locator("tbody").get_by_role("row")

    def row_with(self, text: str) -> Locator:
        """The row containing a cell whose text is exactly ``text`` (e.g. a SKU or email)."""
        return self.rows.filter(has=self.table.page.get_by_role("cell", name=text, exact=True))

    def headers(self) -> list[str]:
        return [h.strip() for h in self.table.get_by_role("columnheader").all_inner_texts()]

    def column_values(self, header: str) -> list[str]:
        """Text of every body cell under ``header``. Call after the table is stable
        (e.g. after an ``expect`` on the row count or results text)."""
        index = self.headers().index(header)
        return [row.get_by_role("cell").nth(index).inner_text().strip() for row in self.rows.all()]

    def cell(self, row: Locator, header: str) -> Locator:
        return row.get_by_role("cell").nth(self.headers().index(header))

    def expect_row_count(self, count: int) -> None:
        expect(self.rows).to_have_count(count)

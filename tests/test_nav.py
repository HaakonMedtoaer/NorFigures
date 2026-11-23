"""NAV registered unemployment (D20): the page scrape and the xlsx reader.

NAV has no API, so this source breaks when NAV changes its page or its file.
These tests pin each shape we rely on and check that every kind of change
fails loudly with a message that says what changed, never with a wrong number.
The weekly live check (test_live_sources.py) tells us when it actually happens.
"""

import io
import unittest
import zipfile
from decimal import Decimal

from norfigures.fetch import fetch_series, latest
from norfigures.ledger import load
from norfigures.net import Client
from norfigures.sources import nav
from norfigures.sources.base import SourceError

LINK = ('<a href="/_/attachment/download/9356f88f-2984:9736da86/'
        '{m}_HL050%20Helt%20ledige.%20Kjonn%20og%20alder.%20Tidsserie%20maaned.xlsx">xlsx</a>')

SHEET = ["Kjønn", "Prosent"]
MONTHS = ["Januar", "Februar", "Mars"]


def xlsx(rows=None, sheet_name="2. Kjønn Prosent av arbeidsstyr", fmt="#,##0.0",
         period_line="Januar - mars 2026", months=MONTHS, extra_sheets=("1. Kjønn Antall",)):
    """A minimal workbook in NAV's layout: a period line, a month header, value rows."""
    if rows is None:
        rows = [("I alt", ["2.3", "2.2", "2"]), ("Kvinner", ["1.9", "1.9", "1.8"])]

    def cell(ref, text=None, number=None, style=0):
        if number is not None:
            return f'<c r="{ref}" s="{style}"><v>{number}</v></c>'
        return f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>'

    cols = "CDEFGHIJKLMN"
    xml_rows = [f'<row r="6">{cell("B6", period_line)}</row>' if period_line else "",
                '<row r="8">' + "".join(cell(f"{cols[i]}8", m) for i, m in enumerate(months)) + "</row>"]
    for n, (label, values) in enumerate(rows, start=9):
        xml_rows.append(f'<row r="{n}">' + cell(f"B{n}", label) + "".join(
            cell(f"{cols[i]}{n}", number=v, style=1) for i, v in enumerate(values) if v is not None)
            + "</row>")
    sheet = ('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             f'<sheetData>{"".join(xml_rows)}</sheetData></worksheet>')
    names = list(extra_sheets) + [sheet_name]
    workbook = ('<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                + "".join(f'<sheet name="{n}" sheetId="{i}" r:id="rId{i}"/>' for i, n in enumerate(names, 1))
                + "</sheets></workbook>")
    rels = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(f'<Relationship Id="rId{i}" Target="worksheets/sheet{i}.xml" Type="x"/>'
                      for i in range(1, len(names) + 1)) + "</Relationships>")
    styles = ('<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
              f'<numFmts count="1"><numFmt numFmtId="173" formatCode="{fmt}"/></numFmts>'
              '<cellXfs count="2"><xf numFmtId="0"/><xf numFmtId="173"/></cellXfs></styleSheet>')
    empty = ('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             '<sheetData/></worksheet>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", rels)
        z.writestr("xl/styles.xml", styles)
        for i, _ in enumerate(names[:-1], 1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", empty)
        z.writestr(f"xl/worksheets/sheet{len(names)}.xml", sheet)
    return buf.getvalue()


def parse(data):
    return nav.parse_table(data, tuple(SHEET), "I alt", "test file")


class TableFileTest(unittest.TestCase):
    def test_reads_the_national_row_with_the_decimals_nav_shows(self):
        self.assertEqual(parse(xlsx()), {"2026-01": Decimal("2.3"), "2026-02": Decimal("2.2"),
                                         "2026-03": Decimal("2.0")})
        self.assertEqual(str(parse(xlsx())["2026-03"]), "2.0")

    def test_a_month_not_published_yet_is_left_out(self):
        data = xlsx(rows=[("I alt", ["2.3", "2.2", None])])
        self.assertEqual(sorted(parse(data)), ["2026-01", "2026-02"])

    def test_a_january_file_has_a_one_month_period_line(self):
        data = xlsx(rows=[("I alt", ["2.3"])], months=["Januar"], period_line="Januar 2027")
        self.assertEqual(parse(data), {"2027-01": Decimal("2.3")})

    def test_each_change_in_layout_fails_loudly(self):
        cases = {
            "sheet renamed": (xlsx(sheet_name="2. Prosent"), "expected one sheet"),
            "two matching sheets": (xlsx(extra_sheets=("4. Kjønn Prosent kopi",)), "expected one sheet"),
            "no period line": (xlsx(period_line=None), "Januar - <month> <year>"),
            "months renamed": (xlsx(months=["Jan", "Feb", "Mar"]), "no header row"),
            "months out of order": (xlsx(months=["Januar", "Mars", "Februar"]), "not January onwards"),
            "national row renamed": (xlsx(rows=[("Totalt", ["2.3", "2.2", "2"])]), "labelled 'I alt'"),
            "national row twice": (xlsx(rows=[("I alt", ["2.3"]), ("I alt", ["2.1"])]), "found 2"),
            "text in a value cell": (xlsx(rows=[("I alt", ["2,3", "2.2", "2"])]), "is not a number"),
            "more decimals than shown": (xlsx(rows=[("I alt", ["2.34", "2.2", "2"])]), "refusing to round"),
            "a count, not a percent": (xlsx(rows=[("I alt", ["68932", "2.2", "2"])], fmt="#,##0"),
                                       "is not a percent"),
            "general number format": (xlsx(fmt="General"), "cannot read the decimals"),
            "empty row": (xlsx(rows=[("I alt", [None, None, None])]), "has no values"),
            "not an xlsx": (b"<html>Not found</html>", "not a readable .xlsx"),
        }
        for name, (data, message) in cases.items():
            with self.subTest(name=name), self.assertRaises(SourceError) as cm:
                parse(data)
            self.assertIn(message, str(cm.exception))


class PageTest(unittest.TestCase):
    def test_finds_the_table_link_and_its_month(self):
        url, month = nav.find_table_link(LINK.format(m="202610"), "HL050", "page")
        self.assertTrue(url.startswith("https://www.nav.no/_/attachment/download/"))
        self.assertEqual(month, "2026-10")

    def test_pdf_and_other_tables_are_ignored(self):
        page = (LINK.format(m="202610").replace(".xlsx", ".pdf")
                + LINK.format(m="202610").replace("HL050", "HL060") + LINK.format(m="202610"))
        url, _ = nav.find_table_link(page, "HL050", "page")
        self.assertIn("HL050", url)
        self.assertTrue(url.endswith(".xlsx"))

    def test_newest_file_wins_when_two_months_are_linked(self):
        _, month = nav.find_table_link(LINK.format(m="202609") + LINK.format(m="202610"), "HL050", "p")
        self.assertEqual(month, "2026-10")

    def test_page_changes_fail_loudly(self):
        cases = {
            "no link": ("<html>Statistikk per oktober 2026</html>", "has no link"),
            "file renamed": (LINK.format(m="202610").replace("HL050", "HL051"), "has no link"),
            "link off the download path": (LINK.format(m="202610").replace("/_/attachment/download/", "/files/"),
                                           "has no link"),
            "two files for one month": (LINK.format(m="202610")
                                        + LINK.format(m="202610").replace("9356f88f", "aaaa0000"),
                                        "more than one"),
        }
        for name, (page, message) in cases.items():
            with self.subTest(name=name), self.assertRaises(SourceError) as cm:
                nav.find_table_link(page, "HL050", "page")
            self.assertIn(message, str(cm.exception))


class RecordedNavTest(unittest.TestCase):
    """Against the recorded page and file (refresh with NORFIGURES_RECORD=1)."""

    def setUp(self):
        self.client = Client("replay")
        self.series = load()["nav_registered"]

    def test_latest_month_from_the_recorded_file(self):
        obs = latest(self.client, self.series)
        self.assertEqual((obs.source, obs.period, str(obs.value)), ("nav", "2026-10", "2.0"))
        self.assertTrue(obs.url.startswith("https://www.nav.no/_/attachment/download/"))
        self.assertIn("HL050", obs.dims["file"])

    def test_a_range_within_the_year(self):
        obs = fetch_series(self.client, self.series, start="2026-08", end="2026-10")
        self.assertEqual([(o.period, str(o.value)) for o in obs],
                         [("2026-08", "2.1"), ("2026-09", "2.0"), ("2026-10", "2.0")])

    def test_an_earlier_year_comes_from_the_archive_page(self):
        obs = fetch_series(self.client, self.series, start="2025-12", end="2025-12")
        self.assertEqual([o.period for o in obs], ["2025-12"])
        self.assertTrue(obs[0].dims["file"].startswith("202512_HL050"))

    def test_a_month_after_the_file_has_no_value(self):
        self.assertEqual(fetch_series(self.client, self.series, start="2026-11", end="2026-11"), [])

    def test_before_the_archive_is_refused(self):
        with self.assertRaises(SourceError):
            fetch_series(self.client, self.series, start="2019-05", end="2019-05")


if __name__ == "__main__":
    unittest.main()

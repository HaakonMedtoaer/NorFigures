"""NAV registered unemployment ("helt ledige"), read from NAV's published files (D20).

NAV has no API. Each month it puts a new spreadsheet on its statistics page,
under a download URL with a content hash in it, so the URL cannot be kept in
the ledger. This adapter:

1. GETs the statistics page (the current year) or the archive page for an
   earlier year,
2. finds the one link to the table file (`<YYYYMM>_HL050 ... .xlsx`),
3. GETs that file and reads the national row of the percent sheet.

Every step checks the shape it expects and raises SourceError naming what
changed, so a redesign of NAV's pages fails loudly instead of returning a wrong
number. A weekly live check (tests/test_live_sources.py) catches it early.

The xlsx is read with zipfile and xml.etree (standard library only). Values are
taken as written in the cell and given the decimals of the cell's number format,
the figure NAV shows (2 shown as "2,0" is Decimal("2.0")).
"""

from __future__ import annotations

import html
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation

from ..net import Client
from .base import Observation, SourceError

SOURCE = "nav"
BASE = "https://www.nav.no"
STATS = BASE + "/no/nav-og-samfunn/statistikk/arbeidssokere-og-stillinger-statistikk"
CURRENT_PAGE = STATS + "/helt-ledige"
ARCHIVE_PAGE = STATS + "/relatert-informasjon/arkiv-helt-ledige.{year}"
FIRST_ARCHIVE_YEAR = 2020   # the archive pages start here

MONTHS = ("januar", "februar", "mars", "april", "mai", "juni", "juli", "august",
          "september", "oktober", "november", "desember")

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}
_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"
_BUILTIN_DECIMALS = {0: None, 1: 0, 2: 2, 3: 0, 4: 2, 9: 0, 10: 2}


# --------------------------------------------------------------------------- page

def find_table_link(page: str, table: str, page_url: str) -> tuple[str, str]:
    """Return (absolute URL, period of the file) for the one `<YYYYMM>_<table>` xlsx link.

    Monthly tables are named by month (`202610_HL050`), annual ones by year
    (`2025_HL090`); the period is YYYY-MM or YYYY accordingly.
    """
    pat = re.compile(r'href="(/_/attachment/download/[^"/]+/(\d{4})(\d{2})?_' + re.escape(table)
                     + r'(?:%20|\s)[^"/]*\.xlsx)"')
    found = {(m.group(1), m.group(2) + (f"-{m.group(3)}" if m.group(3) else ""))
             for m in pat.finditer(page)}
    if not found:
        raise SourceError(f"NAV page {page_url} has no link to a {table} .xlsx file; "
                          "the page layout or the file name may have changed")
    months = {m for _, m in found}
    if len(found) != len(months):
        raise SourceError(f"NAV page {page_url} links to more than one {table} .xlsx file "
                          f"for the same period: {sorted(found)}")
    href, month = max(found, key=lambda f: f[1])
    return BASE + html.unescape(href), month


# --------------------------------------------------------------------------- xlsx

def _decimals(fmt: str) -> int | None:
    fmt = fmt.split(";")[0]
    if fmt.lower() == "general":
        return None
    m = re.search(r"\.([0#]+)", fmt)
    return len(m.group(1)) if m else 0


class _Workbook:
    def __init__(self, data: bytes, where: str):
        self.where = where
        try:
            self.zip = zipfile.ZipFile(io.BytesIO(data))
            self.strings = self._shared_strings()
            self.formats = self._cell_formats()
            self.sheets = self._sheets()
        except (zipfile.BadZipFile, KeyError, ET.ParseError) as e:
            raise SourceError(f"{where} is not a readable .xlsx file: {e}") from e

    def _xml(self, name: str):
        return ET.fromstring(self.zip.read(name))

    def _shared_strings(self) -> list[str]:
        if "xl/sharedStrings.xml" not in self.zip.namelist():
            return []
        root = self._xml("xl/sharedStrings.xml")
        return ["".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t"))
                for si in root.findall("m:si", _NS)]

    def _cell_formats(self) -> list[int | None]:
        root = self._xml("xl/styles.xml")
        custom = {int(n.get("numFmtId")): n.get("formatCode")
                  for n in root.iterfind("m:numFmts/m:numFmt", _NS)}
        out = []
        for xf in root.iterfind("m:cellXfs/m:xf", _NS):
            fid = int(xf.get("numFmtId", "0"))
            out.append(_decimals(custom[fid]) if fid in custom else _BUILTIN_DECIMALS.get(fid, -1))
        return out

    def _sheets(self) -> dict[str, str]:
        rels = {r.get("Id"): r.get("Target") for r in self._xml("xl/_rels/workbook.xml.rels").iter(_REL)}
        out = {}
        for s in self._xml("xl/workbook.xml").iterfind("m:sheets/m:sheet", _NS):
            target = rels[s.get(f"{{{_NS['r']}}}id")].lstrip("/")
            out[s.get("name")] = target if target.startswith("xl/") else "xl/" + target
        return out

    def rows(self, sheet: str) -> list[dict[str, tuple[str, int | None]]]:
        """Rows as {column letter: (text, decimals of the number format)}; empty cells left out."""
        out = []
        for row in self._xml(self.sheets[sheet]).iterfind("m:sheetData/m:row", _NS):
            cells = {}
            for c in row.findall("m:c", _NS):
                v = c.find("m:v", _NS)
                if v is not None and v.text is not None:
                    text = self.strings[int(v.text)] if c.get("t") == "s" else v.text
                else:
                    inline = c.find("m:is", _NS)
                    if inline is None:
                        continue
                    text = "".join(t.text or "" for t in inline.iter(f"{{{_NS['m']}}}t"))
                style = int(c.get("s", "0"))
                dec = self.formats[style] if style < len(self.formats) else -1
                col = re.match(r"[A-Z]+", c.get("r", "")).group(0)
                cells[col] = (text.strip(), dec)
            if cells:
                out.append(cells)
        return out


def _col_index(col: str) -> int:
    n = 0
    for ch in col:
        n = n * 26 + ord(ch) - 64
    return n


def parse_table(data: bytes, sheet_words: tuple[str, ...], row_label: str,
                where: str, annual: bool = False) -> dict[str, Decimal]:
    """Read one row of a month-by-month sheet: {"YYYY-MM": value}.

    The sheet is the one whose name holds all of `sheet_words`; the year comes from
    the "Januar - oktober 2026" line, the months from the header row, the values from
    the row whose first cell is `row_label` ("I alt"). With `annual`, the header row
    holds years instead ("1995", "1996", ...) and the result is {"YYYY": value}.
    """
    wb = _Workbook(data, where)
    names = [n for n in wb.sheets if all(w.lower() in n.lower() for w in sheet_words)]
    if len(names) != 1:
        raise SourceError(f"{where}: expected one sheet named with {list(sheet_words)}, "
                          f"found {names or 'none'} among {list(wb.sheets)}")
    rows = wb.rows(names[0])
    if annual:
        return _parse_years(rows, names[0], row_label, where)

    year = None
    for r in rows:
        for text, _ in r.values():
            m = re.fullmatch(r"januar(?:\s*-\s*[a-zæøå]+)?\s+(\d{4})", text, re.I)
            if m:
                year = m.group(1)
                break
        if year:
            break
    if not year:
        raise SourceError(f"{where}: no 'Januar - <month> <year>' line in sheet {names[0]!r}")

    header = next((r for r in rows if any(t.lower() == "januar" for t, _ in r.values())), None)
    if header is None:
        raise SourceError(f"{where}: no header row with month names in sheet {names[0]!r}")
    month_cols = sorted(((c, t.lower()) for c, (t, _) in header.items() if t.lower() in MONTHS),
                        key=lambda x: _col_index(x[0]))
    labels = [m for _, m in month_cols]
    if labels != list(MONTHS[:len(labels)]):
        raise SourceError(f"{where}: month headers are not January onwards in order: {labels}")

    target = [r for r in rows if any(t == row_label for t, _ in r.values())
              and not any(t.lower() in MONTHS for t, _ in r.values())]
    if len(target) != 1:
        raise SourceError(f"{where}: expected one row labelled {row_label!r} in sheet "
                          f"{names[0]!r}, found {len(target)}")
    row = target[0]

    out = {}
    for col, month in month_cols:
        if col not in row:
            continue  # month not published yet in this file
        out[f"{year}-{MONTHS.index(month) + 1:02d}"] = _value(row[col], f"{month} {year}", where)
    if not out:
        raise SourceError(f"{where}: row {row_label!r} has no values")
    return out


def _value(cell: tuple, what: str, where: str) -> Decimal:
    """A cell's value with the decimals its number format shows; checked to be a percent."""
    text, dec = cell
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise SourceError(f"{where}: {what} value {text!r} is not a number") from None
    if dec is None or dec < 0:
        raise SourceError(f"{where}: {what} cell has a number format we cannot "
                          "read the decimals from")
    shown = value.quantize(Decimal(1).scaleb(-dec))
    if shown != value:
        raise SourceError(f"{where}: {what} value {text} has more decimals than "
                          f"NAV shows ({dec}); refusing to round it")
    if not Decimal(0) <= shown <= Decimal(100):
        raise SourceError(f"{where}: {what} value {shown} is not a percent")
    return shown


def _is_year(text: str) -> bool:
    return bool(re.fullmatch(r"\d{4}", text))


def _parse_years(rows: list, sheet: str, row_label: str, where: str) -> dict[str, Decimal]:
    """The annual layout: a header row of years, then one row per area (D21)."""
    header = next((r for r in rows if sum(_is_year(t) for t, _ in r.values()) >= 2), None)
    if header is None:
        raise SourceError(f"{where}: no header row with years in sheet {sheet!r}")
    year_cols = sorted(((c, t) for c, (t, _) in header.items() if _is_year(t)),
                       key=lambda x: _col_index(x[0]))
    years = [y for _, y in year_cols]
    if years != [str(y) for y in range(int(years[0]), int(years[0]) + len(years))]:
        raise SourceError(f"{where}: year headers are not consecutive: {years}")
    target = [r for r in rows if any(t == row_label for t, _ in r.values())
              and not any(_is_year(t) for t, _ in r.values())]
    if len(target) != 1:
        raise SourceError(f"{where}: expected one row labelled {row_label!r} in sheet "
                          f"{sheet!r}, found {len(target)}")
    out = {}
    for col, year in year_cols:
        cell = target[0].get(col)
        if cell is None or cell[0] in ("*", ":", ".", "-"):
            continue  # not published, or suppressed by NAV
        out[year] = _value(cell, year, where)
    if not out:
        raise SourceError(f"{where}: row {row_label!r} has no values")
    return out


# --------------------------------------------------------------------------- fetch

def _year_file(client: Client, table: str, year: int | None) -> tuple[str, str, str]:
    """(page URL, file URL, file month) for the current file (year None) or a past year's."""
    page_url = CURRENT_PAGE if year is None else ARCHIVE_PAGE.format(year=year)
    page = client.get(page_url).body
    url, month = find_table_link(page, table, page_url)
    if year is not None and month != f"{year}-12":
        raise SourceError(f"NAV archive page for {year} links to the {month} file, not December")
    return page_url, url, month


def fetch(client: Client, series_id: str, table: str, selection: dict,
          start: str | None = None, end: str | None = None,
          last_n: int | None = None, annual: bool = False) -> list[Observation]:
    """Observations from NAV's table files. Periods are YYYY-MM, or YYYY with `annual`.

    `selection` names the sheet ("sheet": words in its name) and the row ("row").
    An annual table holds every year in one file on the current page.
    """
    words = tuple(selection["sheet"])
    label = selection["row"]
    if annual:
        _, url, _ = _year_file(client, table, None)
        resp = client.get(url)
        if resp.content is None:
            raise SourceError(f"NAV file {url} did not come back as a file")
        values = parse_table(resp.content, words, label, f"NAV file {url}", annual=True)
        since = selection.get("since", "0000")   # earlier years are incomplete in the file
        obs = [Observation(SOURCE, series_id, p, v, url, resp.retrieved_at,
                           {"_table": table, "file": url.rsplit("/", 1)[-1]})
               for p, v in sorted(values.items()) if p >= since]
        if not (start or end):
            return obs[-(last_n or 1):]
        lo, hi = start or end, end or start
        return [o for o in obs if lo <= o.period <= hi]
    _, cur_url, cur_month = _year_file(client, table, None)
    cur_year = int(cur_month[:4])

    def read(url: str, data_year: int) -> list[Observation]:
        resp = client.get(url)
        if resp.content is None:
            raise SourceError(f"NAV file {url} did not come back as a file")
        values = parse_table(resp.content, words, label, f"NAV file {url}")
        if any(p[:4] != str(data_year) for p in values):
            raise SourceError(f"NAV file {url} holds {sorted(values)}, expected {data_year}")
        return [Observation(SOURCE, series_id, p, v, url, resp.retrieved_at,
                            {"_table": table, "file": url.rsplit("/", 1)[-1]})
                for p, v in sorted(values.items())]

    if not (start or end):
        obs = read(cur_url, cur_year)
        n = last_n or 1
        if len(obs) < n and cur_year - 1 >= FIRST_ARCHIVE_YEAR:
            _, url, _ = _year_file(client, table, cur_year - 1)
            obs = read(url, cur_year - 1) + obs
        return obs[-n:]

    lo, hi = start or end, end or start
    out: list[Observation] = []
    for year in range(int(lo[:4]), int(hi[:4]) + 1):
        if year > cur_year:
            break
        if year == cur_year:
            out += read(cur_url, cur_year)
        elif year < FIRST_ARCHIVE_YEAR:
            raise SourceError(f"NAV's archive pages start in {FIRST_ARCHIVE_YEAR}; "
                              f"{year} is not covered")
        else:
            _, url, _ = _year_file(client, table, year)
            out += read(url, year)
    return [o for o in out if lo <= o.period <= hi]

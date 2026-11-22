"""Mutation-kill tests for ``services/export`` (T-Q247, ADR-0131).

Pins the CSV dialect and error payloads, date handling and the exact Parquet schema, compression and
integer precision. Complements ``test_export.py``.
"""

from __future__ import annotations

import io
from datetime import UTC, date, datetime
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from budget_planner.services import export as export_svc
from budget_planner.services.export import ExportColumn

TEXT = ExportColumn("s", "Text", "str")
DATE = ExportColumn("d", "Day", "date")
INT = ExportColumn("i", "Count", "int")
MONEY = ExportColumn("m", "Money", "money_minor")
FLAG = ExportColumn("b", "Flag", "bool")


def test_unknown_column_error_carries_the_missing_key() -> None:
    with pytest.raises(export_svc.UnknownColumnError) as csv_err:
        export_svc.export_csv([{"s": "x"}], [TEXT, DATE])
    assert csv_err.value.args == ("d",)
    with pytest.raises(export_svc.UnknownColumnError) as pq_err:
        export_svc.export_parquet([{"s": "x"}], [TEXT, DATE])
    assert pq_err.value.args == ("d",)


def test_csv_quotes_with_the_excel_dialect() -> None:
    rows = [{"s": 'a,b "c"\nd'}, {"s": "plain"}, {"s": ""}]
    assert export_svc.export_csv(rows, [TEXT]) == b'Text\n"a,b ""c""\nd"\nplain\n""\n'


def test_csv_date_cell_is_iso_and_a_datetime_is_not_space_separated() -> None:
    out = export_svc.export_csv([{"d": datetime(2026, 11, 10, 1, 2, 3, tzinfo=UTC)}], [DATE])
    assert out == b"Day\n2026-11-10T01:02:03+00:00\n"


def test_csv_date_column_rejects_a_string_with_the_column_in_the_message() -> None:
    with pytest.raises(TypeError) as err:
        export_svc.export_csv([{"d": "2026-11-10"}], [DATE])
    assert str(err.value) == "column 'd' expected date, got str"


def test_csv_utf8_bytes() -> None:
    assert export_svc.export_csv([{"s": "zażółć"}], [TEXT]) == "Text\nzażółć\n".encode()


def _read(blob: bytes) -> pa.Table:
    return pq.read_table(io.BytesIO(blob))


def test_parquet_schema_has_no_index_column_and_is_zstd() -> None:
    cols = [TEXT, DATE, INT, MONEY, FLAG]
    rows = [{"s": "a", "d": date(2026, 11, 10), "i": 1, "m": 250, "b": True}]
    blob = export_svc.export_parquet(rows, cols)
    table = _read(blob)
    assert table.column_names == ["Text", "Day", "Count", "Money", "Flag"]
    assert table.schema.types == [pa.string(), pa.date32(), pa.int64(), pa.int64(), pa.bool_()]
    meta = pq.ParquetFile(io.BytesIO(blob)).metadata
    assert meta.row_group(0).column(0).compression == "ZSTD"
    assert b"__index_level_0__" not in blob


def test_parquet_keeps_exact_integers_and_nulls() -> None:
    big = 2**62 + 1  # a float64 detour would round this
    rows: list[dict[str, Any]] = [
        {"s": "a", "d": date(2026, 11, 10), "i": big, "m": None, "b": None},
        {"s": None, "d": None, "i": None, "m": -5, "b": False},
    ]
    table = _read(export_svc.export_parquet(rows, [TEXT, DATE, INT, MONEY, FLAG]))
    assert table.to_pydict() == {
        "Text": ["a", None],
        "Day": [date(2026, 11, 10), None],
        "Count": [big, None],
        "Money": [None, -5],
        "Flag": [None, False],
    }


def test_parquet_of_no_rows_keeps_the_schema() -> None:
    table = _read(export_svc.export_parquet([], [TEXT, INT]))
    assert (table.num_rows, table.column_names) == (0, ["Text", "Count"])

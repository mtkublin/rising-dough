"""Export service (T-027).

Serialise an in-memory list of rows into CSV or Parquet bytes. The service
is intentionally dumb about domain shape — callers hand it a column
specification plus a list of mappings (ADR-0020).

Money columns are exported as raw integer minor units; callers that want a
scaled major-unit column must build it on their side.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Any, Literal

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ColumnKind = Literal["int", "money_minor", "date", "str", "bool"]


@dataclass(frozen=True, slots=True)
class ExportColumn:
    """Describe a single exported column.

    ``currency_key`` is reserved for future multi-currency annotation (v2);
    unused in v1 (ADR-0006).
    """

    key: str
    header: str
    kind: ColumnKind
    currency_key: str | None = None


class UnknownColumnError(KeyError):
    """Raised when a row is missing the key referenced by an ``ExportColumn``."""


def _lookup(row: Mapping[str, Any], column: ExportColumn) -> Any:
    try:
        return row[column.key]
    except KeyError as exc:
        raise UnknownColumnError(column.key) from exc


def _format_csv_cell(value: Any, column: ExportColumn) -> str:
    if value is None:
        return ""
    if column.kind == "bool":
        return "true" if value else "false"
    if column.kind == "date":
        if not isinstance(value, date):  # pragma: no cover - defensive
            raise TypeError(f"column {column.key!r} expected date, got {type(value).__name__}")
        return value.isoformat()
    # int / money_minor / str all go to str()
    return str(value)


def export_csv(
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[ExportColumn],
) -> bytes:
    """UTF-8 CSV with LF line endings, Excel dialect, header row from ``columns``.

    Minor-unit money columns are raw integers. Callers who want a scaled
    major-unit column must build one and pass it as kind='str'.
    """
    buf = io.StringIO()
    writer = csv.writer(buf, dialect="excel", lineterminator="\n")
    writer.writerow(col.header for col in columns)
    for row in rows:
        writer.writerow(_format_csv_cell(_lookup(row, col), col) for col in columns)
    return buf.getvalue().encode()


_DTYPES: Mapping[ColumnKind, Any] = MappingProxyType(
    {
        "int": pd.Int64Dtype(),
        "money_minor": pd.Int64Dtype(),
        "str": pd.StringDtype(),
        "bool": pd.BooleanDtype(),
        "date": "object",  # we'll convert manually
    }
)


def _column_series(rows: Sequence[Mapping[str, Any]], column: ExportColumn) -> pd.Series[Any]:
    values = [_lookup(row, column) for row in rows]
    dtype = "object" if column.kind == "date" else _DTYPES[column.kind]
    series: pd.Series[Any] = pd.Series(values, dtype=dtype)
    return series


def _arrow_type(kind: ColumnKind) -> pa.DataType:
    if kind in ("int", "money_minor"):
        return pa.int64()
    if kind == "bool":
        return pa.bool_()
    if kind == "date":
        return pa.date32()
    return pa.string()


def export_parquet(
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[ExportColumn],
) -> bytes:
    """Apache Parquet (zstd), no index column. Dtypes come from ``ExportColumn.kind``."""
    frame_data = {col.header: _column_series(rows, col) for col in columns}
    df = pd.DataFrame(frame_data)
    schema = pa.schema([pa.field(col.header, _arrow_type(col.kind)) for col in columns])
    table = pa.Table.from_pandas(df, schema=schema, preserve_index=False)
    out = io.BytesIO()
    pq.write_table(table, out, compression="zstd")
    return out.getvalue()


__all__ = [
    "ColumnKind",
    "ExportColumn",
    "UnknownColumnError",
    "export_csv",
    "export_parquet",
]

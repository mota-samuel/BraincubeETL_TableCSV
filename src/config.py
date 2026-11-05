"""Carregamento e validação da configuração."""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Union
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, Field

DATE_FMT = "%Y%m%d_%H%M%S"


def _shift_years(dt: datetime, years: int) -> datetime:
    try:
        return dt.replace(year=dt.year - years)
    except ValueError:  # 29 de fevereiro
        return dt.replace(year=dt.year - years, day=28)


class Settings(BaseModel):
    base_url: str
    braincube: str
    api_key: str
    timeout: float = 60.0
    max_retries: int = 3
    backoff_factor: float = 2.0
    timezone: str = "America/Sao_Paulo"
    data_dir: Path = Path("data")

    @classmethod
    def load(cls, path: Path) -> "Settings":
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        key = os.environ.get("BRAINCUBE_API_KEY")
        if not key:
            raise RuntimeError("BRAINCUBE_API_KEY não definida no ambiente")
        raw["api_key"] = key
        return cls(**raw)


class OrderSpec(BaseModel):
    mode: Literal["auto", "fixed"] = "auto"
    value: str | None = None


class WindowSpec(BaseModel):
    mode: Literal["fixed"] = "fixed"
    lookback_years: int = 2

    def resolve(self, tz: str) -> tuple[str, str]:
        now = datetime.now(ZoneInfo(tz)).replace(tzinfo=None)
        start = _shift_years(now, self.lookback_years).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return start.strftime(DATE_FMT), now.strftime(DATE_FMT)


class DefinitionsSpec(BaseModel):
    source: Literal["file", "list", "dictionary"] = "list"
    values: list[str] = Field(default_factory=list)
    path: Path | None = None
    column: str = "UUID"
    limit: int | None = None


class RenameSpec(BaseModel):
    enabled: bool = True
    priority: list[str] = Field(default_factory=lambda: ["standard", "local", "tag"])


class SplitColumnRule(BaseModel):
    type: Literal["split_column"]
    column: str
    delimiter: str = "#"
    keep: int = 0
    output: str | None = None


class DateShiftRule(BaseModel):
    type: Literal["date_shift"]
    source: str
    target: str
    threshold: str = "22:20"
    shift_days: int = 1


class TrimRule(BaseModel):
    type: Literal["trim"]
    columns: list[str]


Rule = Annotated[
    Union[SplitColumnRule, DateShiftRule, TrimRule], Field(discriminator="type")
]


class SortSpec(BaseModel):
    column: str
    ascending: bool = False


class OutputSpec(BaseModel):
    file: str
    columns: list[str]
    delimiter: str = ";"
    decimal: str = ","
    encoding: str = "utf-8-sig"
    datetime_format: str = "%d/%m/%Y %H:%M:%S"
    date_format: str = "%d/%m/%Y"
    date_only_columns: list[str] = Field(default_factory=list)
    na_rep: str = ""
    allow_missing_columns: bool = False
    sort: list[SortSpec] = Field(default_factory=list)


class QueryConfig(BaseModel):
    name: str
    enabled: bool = True
    data_source: str
    order: OrderSpec = Field(default_factory=OrderSpec)
    window: WindowSpec = Field(default_factory=WindowSpec)
    definitions: DefinitionsSpec = Field(default_factory=DefinitionsSpec)
    filter: dict = Field(default_factory=dict)
    rename: RenameSpec = Field(default_factory=RenameSpec)
    rules: list[Rule] = Field(default_factory=list)
    output: OutputSpec

    @classmethod
    def load(cls, path: Path) -> "QueryConfig":
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls(**raw)
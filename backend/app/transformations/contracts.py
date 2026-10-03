"""Content-free replacement choices shared by preset and review contracts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

StyleName = Literal["token", "stand_in", "date_shift", "partial_mask", "generalize"]
StyleOption = Literal[
    "full",
    "last4",
    "first_letters",
    "email_domain",
    "email_first",
    "url_host",
    "secret_prefix",
    "month_year",
    "year",
    "age_band",
]


class StyleChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    style: StyleName = "token"
    style_option: StyleOption | None = None


class CategoryDefault(StyleChoice):
    action: Literal["label", "redact", "keep"]

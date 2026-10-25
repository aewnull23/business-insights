from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class PreviewIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    title: str = Field(min_length=5, max_length=300)
    text: str = Field(min_length=20, max_length=12000)
    source_url: HttpUrl | None = None
    published_at: date


class FeedbackIn(BaseModel):
    rating: Literal[-1, 1]
    comment: str = Field(default="", max_length=1000)

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Fact(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    text: str
    verification: str = "demo_source"


class Company(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    demo: bool = True
    disclaimer: str = ""
    industry: str | None = None
    okved: str | None = None
    okved_name: str | None = None
    revenue_rub: int | None = None
    business_size: str | None = None
    region: str | None = None
    city: str | None = None
    stage: str | None = None
    employees: int | None = None
    bank_products: list[str] | None = None
    group: dict[str, Any] | None = None
    counterparties: list[dict[str, Any]] | None = None
    payments: dict[str, Any] | None = None


class NewsItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    title: str
    published_at: str
    category: str = "Прочее"
    origin: str = "demonstration"
    demo: bool = False
    source_name: str = "Источник"
    source_url: str | None = None
    summary: str = ""
    topics: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    signals: dict[str, Any] = Field(default_factory=dict)
    facts: list[Fact] = Field(default_factory=list)


class Document(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    title: str
    origin: str = "demonstration"
    is_bank_research: bool = False
    source_url: str | None = None
    topics: list[str] = Field(default_factory=list)
    text: str


class QuestionIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)

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
    synthetic_u: str | None = None
    name: str
    demo: bool = True
    disclaimer: str = ""
    industry: str | None = None
    okved: str | None = None
    okved_name: str | None = None
    revenue_rub: int | None = None
    business_size: str | None = None
    large_business: bool = False
    include_incomplete: bool = False
    region: str | None = None
    city: str | None = None
    stage: str | None = None
    company_age: str | None = None
    org_type: str | None = None
    ownership: str | None = None
    client_type: str | None = None
    employees: int | None = None
    workers_fns: str | None = None
    workers_spark: str | None = None
    bank_products: list[str] | None = None
    has_key_owner_mark: bool | None = None
    fts_flag: bool | None = None
    fts_country: str | None = None
    group: dict[str, Any] | None = None
    related_persons: list[dict[str, Any]] | None = None
    shared_person_links: list[dict[str, Any]] | None = None
    counterparties: list[dict[str, Any]] | None = None
    payments: dict[str, Any] | None = None
    source: str | None = None


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


class UserAccount(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    company_id: str
    role: str
    display_name: str
    focus_topics: list[str] = Field(default_factory=list)


class QuestionIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class SessionIn(BaseModel):
    user_id: str = Field(min_length=2, max_length=64)

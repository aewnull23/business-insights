"""Граница ранжирования: агент получает уже упорядоченную сводку."""

from app.services.impact import level_of, rank_news, score_of
from app.services.users import topic_boosts


def rank_for(company: dict, news_list: list[dict], user: dict | None = None) -> list[dict]:
    return rank_news(company, news_list, topic_boosts(user))

__all__ = ["level_of", "rank_for", "rank_news", "score_of"]

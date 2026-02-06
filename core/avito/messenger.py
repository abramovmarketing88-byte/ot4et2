"""
Логика сбора сообщений (Avito Messenger / чаты).

Модуль для работы с сообщениями и диалогами Avito (если API предоставляет).
Пока — заглушка для последующей реализации.
"""
from typing import Any


async def collect_messages(
    access_token: str,
    user_id: int,
    date_from: str,
    date_to: str,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """
    Собрать сообщения за период (заглушка).

    :param access_token: Bearer-токен Avito
    :param user_id: Avito user_id
    :param date_from: YYYY-MM-DD
    :param date_to: YYYY-MM-DD
    :return: Список сообщений (пока пустой)
    """
    # TODO: интеграция с Avito API (messenger/chats), когда будет доступно
    return []

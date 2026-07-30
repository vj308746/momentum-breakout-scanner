from __future__ import annotations

import time

import requests

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
)


# Telegram's documented text limit is 4096 characters.
# Keep some margin for safety.
TELEGRAM_SAFE_MESSAGE_LENGTH = 3800


def _split_oversized_block(
    block: str,
    max_length: int,
) -> list[str]:
    """
    Split a single oversized block at line boundaries.

    This is a fallback for unusually long stock blocks or summaries.
    Normal splitting happens between complete blank-line-separated blocks.
    """

    lines = block.splitlines()
    chunks: list[str] = []
    current_lines: list[str] = []
    current_length = 0

    for line in lines:
        line_length = len(line) + 1

        if (
            current_lines
            and current_length + line_length > max_length
        ):
            chunks.append(
                "\n".join(current_lines).strip()
            )
            current_lines = [line]
            current_length = line_length
        else:
            current_lines.append(line)
            current_length += line_length

    if current_lines:
        chunks.append(
            "\n".join(current_lines).strip()
        )

    return [
        chunk
        for chunk in chunks
        if chunk
    ]


def split_telegram_message(
    message: str,
    max_length: int = TELEGRAM_SAFE_MESSAGE_LENGTH,
) -> list[str]:
    """
    Split a Telegram message only between complete logical blocks.

    The watchlist formatter separates the header, summary and each stock
    with a blank line. This function preserves those blocks so a stock
    record is not cut in the middle.

    If one block itself exceeds the Telegram limit, it is split safely at
    line boundaries as a fallback.
    """

    clean_message = message.strip()

    if not clean_message:
        return []

    if len(clean_message) <= max_length:
        return [clean_message]

    raw_blocks = [
        block.strip()
        for block in clean_message.split("\n\n")
        if block.strip()
    ]

    blocks: list[str] = []

    for block in raw_blocks:
        if len(block) <= max_length:
            blocks.append(block)
        else:
            blocks.extend(
                _split_oversized_block(
                    block,
                    max_length,
                )
            )

    chunks: list[str] = []
    current_blocks: list[str] = []
    current_length = 0

    for block in blocks:
        separator_length = (
            2
            if current_blocks
            else 0
        )
        proposed_length = (
            current_length
            + separator_length
            + len(block)
        )

        if (
            current_blocks
            and proposed_length > max_length
        ):
            chunks.append(
                "\n\n".join(
                    current_blocks
                ).strip()
            )
            current_blocks = [block]
            current_length = len(block)
        else:
            current_blocks.append(block)
            current_length = proposed_length

    if current_blocks:
        chunks.append(
            "\n\n".join(
                current_blocks
            ).strip()
        )

    total_chunks = len(chunks)

    if total_chunks <= 1:
        return chunks

    numbered_chunks: list[str] = []

    for index, chunk in enumerate(
        chunks,
        start=1,
    ):
        prefix = (
            f"BREAKOUT ALERT "
            f"({index}/{total_chunks})\n\n"
        )

        # The safety margin normally leaves enough space for this prefix.
        # If not, trim only the final few characters rather than breaking
        # a stock block into a new arbitrary chunk.
        available = max_length - len(prefix)

        if len(chunk) > available:
            chunk = chunk[:available].rstrip()

        numbered_chunks.append(
            prefix + chunk
        )

    return numbered_chunks


def send_telegram_message(
    message: str,
) -> None:
    if not TELEGRAM_BOT_TOKEN.strip():
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is empty"
        )

    if not TELEGRAM_CHAT_ID.strip():
        raise RuntimeError(
            "TELEGRAM_CHAT_ID is empty"
        )

    endpoint = (
        "https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    chunks = split_telegram_message(
        message
    )

    if not chunks:
        raise RuntimeError(
            "Telegram message is empty"
        )

    for index, chunk in enumerate(
        chunks,
        start=1,
    ):
        response = requests.post(
            endpoint,
            json={
                "chat_id": (
                    TELEGRAM_CHAT_ID
                ),
                "text": chunk,
                "disable_web_page_preview": True,
            },
            timeout=30,
        )

        response.raise_for_status()

        payload = response.json()

        if not payload.get("ok"):
            raise RuntimeError(
                payload.get(
                    "description",
                    "Telegram error",
                )
            )

        # Avoid rapid consecutive API calls when the report spans
        # multiple Telegram messages.
        if index < len(chunks):
            time.sleep(0.35)

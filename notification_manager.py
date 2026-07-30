from __future__ import annotations

import logging
import time

from config import (
    NOTIFICATION_PROVIDER,
    TELEGRAM_ENABLED,
    WHATSAPP_ENABLED,
)
from telegram_alert import (
    send_telegram_message,
    split_telegram_message,
)


def send_notifications(
    message: str,
) -> None:
    providers = {
        part.strip().lower()
        for part
        in NOTIFICATION_PROVIDER.split(",")
        if part.strip()
    }

    logging.info(
        "Notification stage started | "
        "Provider setting: %s | "
        "Message characters: %s",
        NOTIFICATION_PROVIDER,
        len(message),
    )

    sent_any = False

    if (
        TELEGRAM_ENABLED
        and (
            "telegram" in providers
            or "both" in providers
        )
    ):
        chunks = split_telegram_message(
            message
        )

        logging.info(
            "Telegram notification prepared | "
            "Chunks: %s",
            len(chunks),
        )

        started = time.perf_counter()

        try:
            send_telegram_message(
                message
            )
        except Exception:
            logging.exception(
                "Telegram notification failed"
            )
            raise

        elapsed = (
            time.perf_counter()
            - started
        )

        logging.info(
            "Telegram notification sent successfully | "
            "Chunks: %s | Duration: %.2fs",
            len(chunks),
            elapsed,
        )

        sent_any = True

    if (
        WHATSAPP_ENABLED
        and (
            "whatsapp" in providers
            or "both" in providers
        )
    ):
        logging.warning(
            "WhatsApp is enabled, but the Cloud API "
            "adapter is not configured yet"
        )

    if not sent_any:
        logging.warning(
            "No notification was sent | "
            "Telegram enabled: %s | "
            "WhatsApp enabled: %s | "
            "Providers: %s",
            TELEGRAM_ENABLED,
            WHATSAPP_ENABLED,
            sorted(
                providers
            ),
        )

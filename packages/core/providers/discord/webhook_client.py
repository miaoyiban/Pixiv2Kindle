"""Discord follow-up webhook client.

After the initial deferred ack (type 5), the system uses the
interaction token to POST follow-up messages.

Spec references: §15.1, §18.2.
"""

from __future__ import annotations

import httpx
from loguru import logger

from packages.core.exceptions import DiscordNotifyError

# Discord API base.
_DISCORD_API = "https://discord.com/api/v10"


class DiscordWebhookClient:
    """Send follow-up messages via Discord Interaction webhooks."""

    def __init__(self, *, timeout: float = 10.0) -> None:
        self._timeout = timeout

    async def send_followup(
        self,
        application_id: str,
        interaction_token: str,
        content: str,
    ) -> None:
        """POST a follow-up message to the interaction webhook.

        Parameters
        ----------
        application_id:
            Discord application / bot ID.
        interaction_token:
            Token from the original interaction (valid ~15 min).
        content:
            Message body (max 2 000 chars by Discord API).
        """
        url = f"{_DISCORD_API}/webhooks/{application_id}/{interaction_token}"

        # Truncate to Discord's limit.
        if len(content) > 2000:
            content = content[:1997] + "..."

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json={"content": content})
                resp.raise_for_status()
            logger.info("Discord follow-up sent (app={})", application_id)
        except httpx.HTTPStatusError as exc:
            raise DiscordNotifyError(
                f"Discord follow-up failed: {exc.response.status_code} – {exc.response.text}",
            ) from exc
        except httpx.HTTPError as exc:
            raise DiscordNotifyError(
                f"Discord follow-up HTTP error: {exc}",
            ) from exc

"""Conversation agent that forwards user text to an external HTTP server (LAN)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Literal

import aiohttp

from homeassistant.components.conversation import ChatLog, ConversationEntity
from homeassistant.components.conversation.chat_log import AssistantContent
from homeassistant.components.conversation.models import ConversationInput, ConversationResult
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddEntitiesCallback


from .const import DOMAIN, CONF_BASE_URL

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the conversation entity from a config entry."""
    async_add_entities([JarvisServerConversationAgent(hass, entry)])


@dataclass(frozen=True)
class _ServerReply:
    text: str


class JarvisServerConversationAgent(ConversationEntity):
    """A conversation entity that forwards text to an external server."""

    _attr_has_entity_name = True
    _attr_name = "Jarvis Server"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry

        # Unique ID is important so HA can track the entity correctly.
        self._attr_unique_id = f"{entry.entry_id}_conversation"

        self._session = async_get_clientsession(hass)
        self._server_url: str = entry.data.get(CONF_BASE_URL).rstrip("/")

    @property
    def supported_languages(self) -> list[str] | Literal["*"]:
        """Return supported languages.

        Return "*" to support all languages (HA will still provide user_input.language).
        """
        return "*"

    async def _async_handle_message(
        self,
        user_input: ConversationInput,
        chat_log: ChatLog,
    ) -> ConversationResult:
        """Handle the incoming message and return a ConversationResult."""
        try:
            reply = await self._call_server(user_input, chat_log)
            speech_text = reply.text

            # Add assistant message to chat log (so multi-turn + UI history works nicely).
            chat_log.async_add_assistant_content_without_tools(
                AssistantContent(
                    agent_id=user_input.agent_id,
                    content=speech_text,
                )
            )

            resp = intent.IntentResponse(language=user_input.language)
            resp.async_set_speech(speech_text)

            return ConversationResult(
                conversation_id=user_input.conversation_id,
                response=resp,
                continue_conversation=False,
            )

        except Exception as e:  # noqa: BLE001 - we want a safe catch-all for voice UX
            _LOGGER.exception("Jarvis Server error while handling message: %s", e)
            return self._error_result(user_input, chat_log, f"Could not reach the server ({type(e).__name__}).")

    async def _call_server(self, user_input: ConversationInput, chat_log: ChatLog) -> _ServerReply:
        """Send the user text to the external server and return the reply."""
        # You can change the endpoint/path as you like.
        url = f"{self._server_url}/converse"

        payload: dict[str, Any] = {
            "text": user_input.text,
            "language": user_input.language,
            "conversation_id": user_input.conversation_id,
            "agent_id": user_input.agent_id,
        }

        timeout = aiohttp.ClientTimeout(total=15)

        async with self._session.post(url, json=payload, timeout=timeout) as r:
            # Raise on non-2xx so we end up in the standard error path.
            r.raise_for_status()

            data = await r.json()

        # Expect either {"text": "..."} or {"response": "..."} (accept both).
        text = (data.get("text") or data.get("response") or "").strip()
        if not text:
            text = "Ok, Jarvis will help"

        return _ServerReply(text=text)

    def _error_result(self, user_input: ConversationInput, chat_log: ChatLog, message: str) -> ConversationResult:
        """Return an error result that HA can speak."""
        # Add an assistant message to history (useful for debugging in UI).
        chat_log.async_add_assistant_content_without_tools(
            AssistantContent(
                agent_id=user_input.agent_id,
                content=message,
            )
        )

        resp = intent.IntentResponse(language=user_input.language)
        resp.async_set_speech(message)

        return ConversationResult(
            conversation_id=user_input.conversation_id,
            response=resp,
            continue_conversation=False,
        )

from __future__ import annotations

import asyncio
from aiohttp import ClientError

from homeassistant.components import intent
from homeassistant.components.conversation import (
    AssistantContent,
    ChatLog,
    ConversationEntity,
    ConversationEntityFeature,
    ConversationInput,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_API_KEY, CONF_BASE_URL, DEFAULT_TIMEOUT_SECONDS, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    async_add_entities([ExternalConversationAgent(hass, entry)])


class ExternalConversationAgent(ConversationEntity):
    """A Conversation agent that forwards user text to an external HTTP server."""

    _attr_has_entity_name = True
    _attr_name = "External Agent"
    _attr_supported_features = ConversationEntityFeature.CONTROL
    _attr_supported_languages = "*"  # or ["en", "pt-BR"]

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._session = async_get_clientsession(hass)

        self._base_url: str = entry.data[CONF_BASE_URL].rstrip("/")
        self._api_key: str = entry.data.get(CONF_API_KEY, "") or ""

        # Unique entity id stability across updates
        self._attr_unique_id = f"{DOMAIN}.external_agent"

    async def async_prepare(self, language: str | None = None) -> None:
        """Optional warm-up hook."""
        return

    async def _async_handle_message(
        self,
        user_input: ConversationInput,
        chat_log: ChatLog,
    ) -> intent.ConversationResult:
        headers: dict[str, str] = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        payload = {
            "text": user_input.text,
            "language": user_input.language,
            "conversation_id": user_input.conversation_id,
            "source": "home_assistant",
        }

        url = f"{self._base_url}/chat"

        try:
            async with asyncio.timeout(DEFAULT_TIMEOUT_SECONDS):
                resp = await self._session.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = await resp.json()
        except TimeoutError:
            return self._error_result(user_input, chat_log, "The server timed out.")
        except ClientError as e:
            return self._error_result(
                user_input, chat_log, f"Could not reach the server ({type(e).__name__})."
            )
        except Exception:
            # Avoid crashing Assist on unexpected server replies
            return self._error_result(user_input, chat_log, "Unexpected server error.")

        reply: str = str(data.get("reply", "")).strip()
        if not reply:
            return self._error_result(
                user_input, chat_log, "Server returned an empty reply."
            )

        continue_conv: bool = bool(data.get("continue", False))
        conversation_id: str = str(data.get("conversation_id", user_input.conversation_id))

        # Add assistant message to the chat log (no tool calls for v1)
        chat_log.async_add_assistant_content_without_tools(
            AssistantContent(agent_id=user_input.agent_id, content=reply)
        )

        response = intent.IntentResponse(language=user_input.language)
        response.async_set_speech(reply)

        return intent.ConversationResult(
            conversation_id=conversation_id,
            response=response,
            continue_conversation=continue_conv,
        )

    def _error_result(
        self,
        user_input: ConversationInput,
        chat_log: ChatLog,
        message: str,
    ) -> intent.ConversationResult:
        chat_log.async_add_assistant_content_without_tools(
            AssistantContent(agent_id=user_input.agent_id, content=message)
        )
        response = intent.IntentResponse(language=user_input.language)
        response.async_set_speech(message)
        return intent.ConversationResult(
            conversation_id=user_input.conversation_id,
            response=response,
            continue_conversation=False,
        )

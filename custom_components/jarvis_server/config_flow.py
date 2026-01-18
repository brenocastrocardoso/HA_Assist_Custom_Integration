from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME

from .const import DOMAIN, CONF_BASE_URL, CONF_API_KEY


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is None:
            schema = vol.Schema(
                {
                    vol.Required(CONF_NAME, default="External Agent"): str,
                    vol.Required(CONF_BASE_URL, default="http://192.168.1.50:8080"): str,
                    vol.Optional(CONF_API_KEY, default=""): str,
                }
            )
            return self.async_show_form(step_id="user", data_schema=schema)

        base_url: str = user_input[CONF_BASE_URL].rstrip("/")
        user_input[CONF_BASE_URL] = base_url

        # Single instance by default (simple “set and forget”)
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

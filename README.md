# My External Conversation Agent (Home Assistant)

A simple Conversation Agent for Home Assistant Assist that forwards user text to an external HTTP server.

## Server API
POST `${BASE_URL}/chat`

Request:
```json
{"text":"...", "language":"en", "conversation_id":"...", "source":"home_assistant"}

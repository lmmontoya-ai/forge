"""Optional forms of the COMMIT tool schema shown to a model seat.

The default form is `map`: `spec/tools.v1.json` exactly as frozen, where
COMMIT `slots` is an object of slot_id -> value.  The engine rejects an
empty map ("COMMIT needs slots"), but that schema allows one.

Two opt-in forms, used by the five-model clear-goal study:

  nonempty-map  the same map with `minProperties: 1`, and a repair
                sentence appended to the re-prompt after an empty COMMIT.
  entries       `slots` served as a nonempty list of {slot_id, value}
                entries; the reply is converted back to the native map
                before the parser and the engine see it (the logged raw
                response holds the converted map).  The repair sentence
                applies too.  The study used this form for its Gemini 3.7
                Flash and Grok 4.5 seats and `nonempty-map` for the others.

No form changes what the engine accepts, the prompt messages, or the
prompt digest; they change the tool schema the model sees and, after an
empty COMMIT only, the re-prompt text.
"""
from __future__ import annotations

import copy
import json

COMMIT_FORMS = ("map", "nonempty-map", "entries")
DEFAULT_COMMIT_FORM = "map"

EMPTY_COMMIT_ERROR = "COMMIT needs slots"
EMPTY_COMMIT_REPAIR = (
    " The slots map cannot be empty. Copy the visible opening-menu "
    "slot IDs and include one allowed value for each slot."
)


def check_commit_form(form: str) -> str:
    if form not in COMMIT_FORMS:
        raise ValueError(f"unknown COMMIT form {form!r}; expected one of {COMMIT_FORMS}")
    return form


def _commit_slots(tools: list) -> dict:
    matches = [tool for tool in tools if tool["function"]["name"] == "commit"]
    if len(matches) != 1:
        raise ValueError("the tool set does not contain exactly one COMMIT")
    return matches[0]["function"]["parameters"]["properties"]


def commit_tools(tools: list, form: str) -> list:
    """The tool list a seat with this COMMIT form is sent (`tools` is not modified)."""
    if check_commit_form(form) == "map":
        return tools
    adapted = copy.deepcopy(tools)
    properties = _commit_slots(adapted)
    properties["slots"]["minProperties"] = 1
    if form == "entries":
        properties["slots"] = {
            "type": "array",
            "description": properties["slots"]["description"],
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "slot_id": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["slot_id", "value"],
                "additionalProperties": False,
            },
        }
    return adapted


def entries_to_map(raw: dict) -> dict:
    """Convert COMMIT slot entries in a provider response to the native map.

    Changes `raw` in place and returns it.  A COMMIT whose slots are not a
    well-formed entry list (an entry with other keys, a non-string field or
    a repeated slot_id) is left as it was, for the engine to reject.
    """
    for choice in raw.get("choices") or []:
        message = choice.get("message") or {}
        for call in message.get("tool_calls") or []:
            function = call.get("function") or {}
            if str(function.get("name", "")).lower() != "commit":
                continue
            arguments = function.get("arguments", "{}")
            was_text = isinstance(arguments, str)
            try:
                payload = json.loads(arguments) if was_text else copy.deepcopy(arguments)
            except (TypeError, json.JSONDecodeError):
                continue
            slots = payload.get("slots") if isinstance(payload, dict) else None
            if not isinstance(slots, list):
                continue
            native = {}
            for entry in slots:
                if not isinstance(entry, dict) or set(entry) != {"slot_id", "value"}:
                    break
                slot_id, value = entry["slot_id"], entry["value"]
                if not isinstance(slot_id, str) or not isinstance(value, str) or slot_id in native:
                    break
                native[slot_id] = value
            else:
                payload["slots"] = native
                function["arguments"] = (
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
                    if was_text else payload
                )
    return raw


def repair_corrective(messages: list, error: str) -> list:
    """Append the repair sentence to the rejection notes of an empty COMMIT."""
    if EMPTY_COMMIT_ERROR in error:
        for message in messages:
            if message.get("role") in {"tool", "user"}:
                message["content"] = (message.get("content") or "") + EMPTY_COMMIT_REPAIR
    return messages

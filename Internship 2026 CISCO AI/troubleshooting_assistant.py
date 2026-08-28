"""Strict AI troubleshooting response handling and responsible-AI review logging."""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, field_validator


SYSTEM_PROMPT = """You are a Cisco Packet Tracer troubleshooting assistant.
Analyze the supplied Cisco symptom and show-command output conservatively.
Return ONLY one valid JSON object. Do not use Markdown, code fences, prose,
comments, or additional keys.
The JSON object MUST contain exactly these keys:
- root_cause: a concise, technically specific likely cause
- confidence: a number from 0.0 to 1.0
- evidence: an array of strings; every string MUST be an exact quote copied
  from the supplied show-command text, including the command output wording
- next_command: exactly one Cisco show or diagnostic command to run next
- fix_steps: an array of concise, ordered remediation steps
Never invent command output. If evidence is insufficient, say so in
root_cause, use a lower confidence, and quote the closest available output.
"""


class TroubleshootingResponse(BaseModel):
    """The only response shape accepted from the troubleshooting model."""

    model_config = ConfigDict(extra="forbid", strict=True)

    root_cause: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[str] = Field(min_length=1)
    next_command: str = Field(min_length=1)
    fix_steps: list[str] = Field(min_length=1)

    @field_validator("evidence", "fix_steps")
    @classmethod
    def reject_blank_items(cls, items):
        if any(not item.strip() for item in items):
            raise ValueError("list items must not be blank")
        return items


class ReviewLogger:
    """Append reviewer decisions to a JSON array without losing prior reviews."""

    VALID_DECISIONS = frozenset({"Accepted", "Edited", "Rejected"})

    def __init__(self, path="responsible_ai_log.json"):
        self.path = Path(path)

    def append(self, decision, correction_notes="", metadata=None):
        """Append one review and return the record that was written."""
        if decision not in self.VALID_DECISIONS:
            raise ValueError("decision must be Accepted, Edited, or Rejected")
        if not isinstance(correction_notes, str):
            raise TypeError("correction_notes must be a string")
        if metadata is not None and not isinstance(metadata, dict):
            raise TypeError("metadata must be a dictionary")

        reviews = self._read_reviews()
        record = {
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
            "decision": decision,
            "correction_notes": correction_notes,
        }
        if metadata:
            record.update(metadata)
        reviews.append(record)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(reviews, indent=2) + "\n", encoding="utf-8")
        return record

    def _read_reviews(self):
        if not self.path.exists():
            return []
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"cannot read review log {self.path}: {error}") from error
        if not isinstance(value, list):
            raise ValueError(f"review log {self.path} must contain a JSON array")
        return value


def analyze_troubleshooting(
    symptom: str,
    show_commands: str,
    model_call: Callable[[str, str], Any],
) -> TroubleshootingResponse:
    """Call an injected LLM function and validate its JSON response.

    ``model_call`` receives ``(SYSTEM_PROMPT, user_prompt)`` and must return a
    JSON string or a dictionary. Evidence is checked against the supplied
    ``show_commands`` after Pydantic validates the response shape.
    """
    if not isinstance(symptom, str) or not symptom.strip():
        raise ValueError("symptom must be a non-empty string")
    if not isinstance(show_commands, str) or not show_commands.strip():
        raise ValueError("show_commands must be a non-empty string")
    if not callable(model_call):
        raise TypeError("model_call must be callable")

    user_prompt = (
        "Symptom:\n"
        f"{symptom.strip()}\n\n"
        "Supplied show-command text:\n"
        f"{show_commands.strip()}"
    )
    raw_response = model_call(SYSTEM_PROMPT, user_prompt)
    try:
        response = (
            TroubleshootingResponse.model_validate_json(raw_response)
            if isinstance(raw_response, str)
            else TroubleshootingResponse.model_validate(raw_response)
        )
    except (TypeError, ValueError) as error:
        raise ValueError(f"AI response failed the troubleshooting schema: {error}") from error

    missing_quotes = [quote for quote in response.evidence if quote not in show_commands]
    if missing_quotes:
        raise ValueError("AI evidence contains text not found in supplied show-command output")
    return response


if __name__ == "__main__":
    sample_output = "show ip interface brief\nGigabitEthernet0/1 10.44.8.9 YES manual administratively down down"

    def sample_model(_system_prompt, _user_prompt):
        return {
            "root_cause": "The uplink interface is administratively disabled.",
            "confidence": 0.98,
            "evidence": ["GigabitEthernet0/1 10.44.8.9 YES manual administratively down down"],
            "next_command": "show running-config interface GigabitEthernet0/1",
            "fix_steps": ["Enter interface configuration mode.", "Issue no shutdown."],
        }

    print(analyze_troubleshooting("The uplink is unreachable.", sample_output, sample_model).model_dump_json())

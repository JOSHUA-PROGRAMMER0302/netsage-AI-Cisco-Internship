"""Gemini-powered Cisco troubleshooting diagnosis engine."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


MODEL_NAME = "gemini-3.6-flash"
SYSTEM_PROMPT = """You are a Senior Cisco TAC Engineer assisting with Cisco Packet Tracer troubleshooting.
Analyze the reported symptom and the supplied Cisco show-command output.
Return only the requested structured JSON response. Never return Markdown,
code fences, commentary, or fields outside the schema.

Rules:
- State one technically specific root cause, or say that evidence is insufficient.
- Set confidence to Low, Medium, or High based only on the supplied evidence.
- The evidence field must quote one or more exact lines copied from show_output.
  Do not paraphrase, normalize, or invent command output.
- Recommend exactly one useful Cisco show or diagnostic command in next_command.
- Give concise, ordered, actionable fix_steps; do not claim a fix was applied.
"""

# Keep the Gemini request schema independent from Pydantic's JSON-schema output.
GEMINI_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "root_cause": {"type": "STRING"},
        "confidence": {"type": "STRING"},
        "evidence": {"type": "STRING"},
        "next_command": {"type": "STRING"},
        "fix_steps": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
    },
    "required": ["root_cause", "confidence", "evidence", "next_command", "fix_steps"],
}


class DiagnosisResponse(BaseModel):
    """Strict structured response returned by the Gemini diagnosis engine."""

    model_config = ConfigDict(extra="forbid", strict=True)

    root_cause: str = Field(min_length=1)
    confidence: Literal["Low", "Medium", "High"]
    evidence: str = Field(min_length=1)
    next_command: str = Field(min_length=1)
    fix_steps: list[str] = Field(min_length=1)

    @field_validator("root_cause", "evidence", "next_command")
    @classmethod
    def reject_blank_text(cls, value):
        if not value.strip():
            raise ValueError("text fields must not be blank")
        return value

    @field_validator("fix_steps")
    @classmethod
    def reject_blank_steps(cls, steps):
        if any(not step.strip() for step in steps):
            raise ValueError("fix steps must not be blank")
        return steps


def run_ai_diagnosis(symptom: str, show_output: str, api_key: str) -> DiagnosisResponse:
    """Diagnose a Cisco issue with Gemini structured output.

    The SDK import is intentionally local so schema and prompt tests can run
    without network credentials or an installed Google client.
    """
    if not isinstance(symptom, str) or not symptom.strip():
        raise ValueError("symptom must be a non-empty string")
    if not isinstance(show_output, str) or not show_output.strip():
        raise ValueError("show_output must be a non-empty string")
    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError("api_key must be a non-empty string")

    try:
        from google import genai
    except ImportError as error:
        raise RuntimeError("google-genai is required; install dependencies from requirements.txt") from error

    prompt = (
        "Reported symptom:\n"
        f"{symptom.strip()}\n\n"
        "Cisco show-command output:\n"
        f"{show_output.strip()}"
    )
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config={
                "system_instruction": SYSTEM_PROMPT,
                "response_mime_type": "application/json",
                "response_schema": GEMINI_SCHEMA,
            },
        )
        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, DiagnosisResponse):
            diagnosis = parsed
        elif parsed is not None:
            diagnosis = DiagnosisResponse.model_validate(parsed)
        else:
            response_text = getattr(response, "text", None)
            if not isinstance(response_text, str) or not response_text.strip():
                raise ValueError("Gemini returned no structured response")
            diagnosis = DiagnosisResponse.model_validate_json(response_text)
    except Exception as error:
        if isinstance(error, (ValueError, TypeError)):
            raise ValueError(f"Gemini returned an invalid diagnosis: {error}") from error
        raise RuntimeError(f"Gemini diagnosis failed: {error}") from error

    if diagnosis.evidence not in show_output:
        raise ValueError("diagnosis evidence is not an exact quote from show_output")
    return diagnosis

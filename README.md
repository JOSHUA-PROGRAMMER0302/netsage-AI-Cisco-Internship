# netsage-AI-Cisco-Internship

# NetSage AI: Network Troubleshooting Assistant with Human Oversight

[![Streamlit](https://img.shields.io/badge/Frontend-Streamlit-FF4B4B.svg)](https://streamlit.io/)
[![Google Gemini](https://img.shields.io/badge/AI-Gemini%20API-4285F4.svg)](https://ai.google.dev/)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB.svg)](https://www.python.org/)

NetSage AI is an AI-assisted diagnostic assistant designed for Cisco Packet Tracer and enterprise lab environments. It processes network symptoms and CLI show-command outputs, flags deterministic configuration errors, generates structured AI diagnoses, and enforces a mandatory human-in-the-loop review workflow.

---

## Key Features

- **Dual-Layer Diagnostics**: Runs deterministic regex-based rule checks (duplicate IPs, missing subnets, disabled interfaces) before querying the LLM engine.
- **Structured JSON Inference**: Powered by Google Gemini with strict schema validation for deterministic troubleshooting outputs.
- **Human-in-the-Loop Validation**: Review interface enabling network engineers to accept, edit, or reject AI diagnoses and log rationale to `responsible_ai_log.json`.
- **Dataset Explorer**: Searchable catalog of 30 standardized Packet Tracer test cases spanning VLANs, ACLs, DHCP, NAT, and dynamic routing.
- **Analytics Dashboard**: Tracks acceptance rates, fault classifications, and model alignment metrics over time.

---

## Architecture Overview

Packet Tracer Symptom & Show Outputs
│
▼
┌──────────────────────────┐
│ Deterministic Rule Check │ ──(Layer 1/2/3 Syntax & State Errors)
└──────────────────────────┘
│
▼
┌──────────────────────────┐
│ Gemini Diagnostic Engine │ ──(Root Cause, Evidence, Fix Steps)
└──────────────────────────┘
│
▼
┌──────────────────────────┐
│ Human Review & Audit Log │ ──(Accept / Edit / Reject -> responsible_ai_log.json)
└──────────────────────────┘


---

## Project Structure

```text
├── app.py                   # Streamlit UI (Troubleshooter, Explorer, Dashboard)
├── diagnose.py              # LLM client & structured JSON schema parser
├── rule_checker.py          # Deterministic Python validation engine
├── logger.py                # Human review audit logging logic
├── cases.csv                # 30 curated Packet Tracer troubleshooting cases
├── diagnose_prompt.md       # Production prompt specifications
├── responsible_ai_log.json  # Documented human review & correction log
├── requirements.txt         # Project dependencies
└── README.md                # Project documentation

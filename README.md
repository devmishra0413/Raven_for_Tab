RAVEN — Personal AI Assistant

RAVEN is a personal AI assistant project focused on a modular, privacy-aware architecture. It brings together chat/orchestration, memory, privacy filtering, scheduling, tools, voice-related components, and a web UI in one local project.

Project status: In active development. Features and interfaces may change; not every planned capability is production-ready.

Overview

RAVEN is designed to provide a single place to interact with an AI assistant while keeping control over local components and deciding what information is sent to an external model provider.

Current project areas include:

Assistant and orchestration — coordinates chat requests and model transport.

Privacy filtering — sanitizes sensitive text before it is sent to a remote provider, with a preview/confirmation flow intended to show the outgoing payload.

Memory — a foundation for storing and retrieving useful facts and conversation-related information.

Scheduling — a dedicated module for scheduled tasks and assistant routines.

Tools — modular actions the assistant can use.

Voice — voice-related components, including wake-word support dependencies.

Web UI and API — API routes and a bundled frontend build.

Tests — automated tests for selected API and internal modules.

The exact availability of each capability depends on the current implementation and configuration.

Technology Stack

Python

FastAPI

Pydantic

NumPy

ONNX Runtime

OpenWakeWord

pytest

HTML/CSS/JavaScript frontend build (in ui/)

See requirements.txt for the Python dependencies currently listed by the repository.

Repository Structure

Raven_for_Tab/
├── api/             # API routes and request handling
├── core/            # Core assistant logic and orchestration
├── memory/          # Memory components
├── privacy/         # Privacy filtering and sanitization
├── scheduler/       # Scheduling functionality
├── scripts/         # Development and utility scripts
├── tests/           # Automated tests
├── tools/           # Assistant tools/actions
├── ui/              # Frontend assets and built UI
├── voice/           # Voice-related functionality
├── BRAIN_NOTES.md   # Orchestration and design notes
├── MEMORY_NOTES.md  # Memory design notes
├── VOICE_NOTES.md   # Voice design notes
├── config.json      # Application configuration (review before sharing)
├── main.py          # CLI entry point
├── pytest.ini       # pytest configuration
└── requirements.txt # Python dependencies

Requirements

Python 3.11 or a compatible Python version

Git

Windows, Linux, or macOS (platform-specific voice features may vary)

Some optional features may require additional system packages, model files, or provider credentials.

Setup

1. Clone the repository

git clone https://github.com/devmishra0413/Raven_for_Tab.git
cd Raven_for_Tab

2. Create and activate a virtual environment

Windows PowerShell

python -m venv .venv
.\.venv\Scripts\Activate.ps1

Linux/macOS

python3 -m venv .venv
source .venv/bin/activate

3. Install dependencies

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

4. Review configuration

Review config.json and any environment-variable settings before starting the application. Add credentials only through a local, untracked configuration or environment file where supported. Never commit API keys, tokens, passwords, private model files, or personal data.

5. Start RAVEN

The repository's main.py entry point starts the CLI:

python main.py

The project also contains API and UI components. Their exact startup commands depend on the current server and frontend configuration; check the relevant files before running them.

Running Tests

Run the test suite with:

python -m pytest -v

To run the API and core tests specifically:

python -m pytest tests/core tests/api_tests -v

A test passing locally does not guarantee every integration or optional hardware-dependent feature is configured.

Privacy and Security

Privacy is a core design goal, but this project should not yet be treated as a security-audited application.

Review the payload before sending private information to any external model provider.

Keep API keys and OAuth credentials out of source control.

Bind a local development server to 127.0.0.1 unless you have deliberately configured and secured remote access.

Do not expose the API to a public network without authentication, access controls, and a security review.

Local storage may not be encrypted. Do not store highly sensitive information unless you understand the storage and backup behavior.

Inspect config.json before publishing or sharing the repository. If a real secret was ever committed, remove it from the repository and rotate/revoke it; deleting it from the latest version alone may not remove it from Git history.

Development Notes

The repository includes design notes that document implementation decisions and known limitations:

BRAIN_NOTES.md

MEMORY_NOTES.md

VOICE_NOTES.md

These notes may describe work in progress. Use the source code and tests as the source of truth for what currently works.

Roadmap

Potential next steps for the project include:

Improve and test the full assistant request flow.

Expand memory retrieval and persistence tests.

Strengthen privacy-filter coverage and secret redaction.

Improve API/UI integration and document the exact launch commands.

Add clearer setup examples for model providers and optional voice components.

Review storage encryption, authentication, and safe remote-access options before production use.

Contributing

For changes, create a branch, make a focused update, and run the relevant tests before opening a pull request.

git checkout -b feature/your-change
python -m pytest -v
git add .
git commit -m "Describe your change"

License

No license information has been confirmed in this README. Add a LICENSE file and update this section before presenting the project as open source.

Built as an evolving personal AI assistant project. 🪶

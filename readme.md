# Email-Newsletter-Agent

**Automatischer Newsletter aus eingehenden E-Mails mit Ollama LLM**

Der Agent ruft ein IMAP-Postfach ab, extrahiert relevante Informationen aus den
E-Mails und erstellt automatisch einen Newsletter. 
Der Newsletter wird dann per E-Mail an eine definierte E-Mail zur weiteren
Bearbeitung gesendet.

[![PyPI version](https://badge.fury.io/py/event-agent.svg)](https://badge.fury.io/py/event-agent)
[![Tests](https://github.com/IhrUsername/event-newsletter-agent/actions/workflows/tests.yml/badge.svg)](https://github.com/IhrUsername/event-newsletter-agent/actions)

## 🚀 Quickstart

```bash
git clone https://github.com/IhrUsername/event-newsletter-agent
cd event-newsletter-agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# .env bearbeiten
python -m event_agent.main
```
ollama installieren: https://ollama.com/docs/installation
LLM mit `ollama pull ollama/llama-3.2:latest` herunterladen
ollama starten: `ollama serve`


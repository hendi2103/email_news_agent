import json
import ollama
from pydantic import BaseModel


class MailContent(BaseModel):
    category: str
    original_sender: str | None
    original_sent_date: str | None
    heading: str
    summary: str
    event_date: str | None
    event_time: str | None
    event_location: str | None
    link_to_event: str | None
    registration_info: str | None


def test_ollama_chat():
    # Try to contact the real Ollama service once; if it fails, skip the test
    try:
        response = ollama.chat(model="llama3.2:3b", messages=[{"role": "user", "content": "ping"}])
        assert "message" in response and "content" in response["message"], "Response should contain 'message' with 'content'"
        print("Ollama chat test passed. Response content:", response["message"]["content"])
        for e in response: print(e)
    except Exception as e:
        print(f"Ollama chat test failed: {e}")
        assert False, f"Ollama not available or model not loaded: {e}"

def analyze_mail(content: str, model: str = 'llama3.2:3b') -> dict:
    """Analyzes and summarizes email content and returns a JSON dict."""
    prompt = (f"""Du bist ein Newsletter-Redaktionsassistent. Analysiere den folgenden E-Mail-Inhalt und extrahiere strukturierte Informationen.

Kategorisiere die E-Mail entweder als 'event' oder 'information'.
Verwende die folgenden Felder, um die Informationen zu extrahieren: 


- category: 'event' oder 'information'
- original_sender: Name und E-Mail-Adresse de ursprünglichen Absenders, wenn die E-Mail weitergeleitet wurde oder null, wenn nicht weitergeleitet
- original_sent_date: das ursprüngliche Datum, wenn die E-Mail weitergeleitet wurde, oder null, wenn nicht weitergeleitet
- heading: eine Überschrift, die den Inhalt der E-Mail zusammenfasst (maximal 80 Zeichen)
- summary: eine Zusammenfassung des E-Mail-Inhalts für einen Newsletter (maximal 320 Zeichen)
- event_date: das Datum der Veranstaltung, oder null, wenn nicht angegeben
- event_time: die Uhrzeit der Veranstaltung, oder null, wenn nicht angegeben
- event_location: der Ort der Veranstaltung, oder null, wenn nicht angegeben
- link_to_event: ein URL-Link zur Veranstaltung, oder null, wenn nicht angegeben
- registration_information: Angaben zur Anmeldung, Fristen, und Kosten, oder null, wenn nicht angegeben
  
Email-Inhalt:      
  
{content}"""
    )

    try:
        response = ollama.chat(
            model=model,
            messages=[
                {"role": "user", "content": prompt}
            ],
            format = MailContent.model_json_schema()
        )
        try:
            mail_content_model = MailContent.model_validate_json(response.message.content)
            result = mail_content_model.model_dump()
        except Exception as e:
            raise ValueError(
                f"Failed to validate LLM JSON against MailContent: {e}\nRaw: {raw_json!r}") from e

    except Exception as e:
        raise RuntimeError(
            f"Failed to contact Ollama service or load model '{model}': {e}"
        ) from e


    return result



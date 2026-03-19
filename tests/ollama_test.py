import ollama
from pydantic import BaseModel

content = """Du bist ein E-Mail-Analyse-Assistent. Analysiere den folgenden E-Mail-Inhalt und extrahiere strukturierte Informationen.

Kategorisiere die E-Mail entweder als 'event' oder 'information'.
Verwende die folgenden Felder, um die Informationen zu extrahieren. Wenn ein Feld nicht verfügbar ist, setze es auf null.:

- subject: der Betreff der E-Mail
- category: 'event' oder 'information'
- sender: Name und E-Mail-Adresse des Absenders
- sent_date: das Datum, an dem die E-Mail gesendet wurde (als String)
- original_sender: Name und E-Mail-Adresse de ursprünglichen Absenders, wenn die E-Mail weitergeleitet wurde
- original_sent_date: das ursprüngliche Datum, wenn die E-Mail weitergeleitet wurde
- heading: eine Überschrift, die den Inhalt der E-Mail zusammenfasst (maximal 80 Zeichen)
- summary: eine Zusammenfassung des E-Mail-Inhalts (maximal 320 Zeichen)
- event_date: das Datum der Veranstaltung
- event_time: die Uhrzeit der Veranstaltung
- event_location: der Ort der Veranstaltung
- link_to_event: ein URL-Link zur Veranstaltung
- registration_information: Registrierungsdetails oder Frist

Betreff:
Einladung - Tag der Muttersprache und Zuckerfest am 27.03.2026 um 15:30 Uhr!
Von:
Auslaenderbeauftragte@Dresden.DE
Datum:
19.03.26, 08:32
An:
undisclosed-recipients:;

Liebe Interessierte,

anbei eine Veranstaltungseinladung von Kolibri e. V. am 27. März, um die sprachliche Vielfalt zu feiern.
_

Mit freundlichen Grüßen
das Team der Integrations- und Ausländerbeauftragten


Landeshauptstadt Dresden
Büro der Integrations- und Ausländerbeauftragten

Telefon (03 51) 4 88 21 31
Lingnerallee 3, 01067 Dresden | Postfach 120020, 01001 Dresden
auslaenderbeauftragte@dresden.de | www.dresden.de/auslaenderbeauftragte
________________________________________________________________________________________
Zentraler Behördenruf 115 - Wir lieben Fragen

----- Weitergeleitet von Shirin Jaqueline Iqbal/OB/StadtverwDresden/DE am 19.03.2026 08:29 -----

Von:        "Kristina Daniels" <kristina.daniels@kolibri-dresden.de>
An:        "auslaenderbeauftragte@dresden.de" <auslaenderbeauftragte@dresden.de>
Datum:        18.03.2026 16:23
Betreff:        Einladung - Tag der Muttersprache und Zuckerfest am 27.03.2026 um 15:30 Uhr!



Sehr geehrte Damen und Herren,
liebe Freunde und Förderer von Kolibri e.V. und der Villa der Kulturen,
 
es ist bei Kolibri schon zu einer Tradition geworden, jährlich den Tag der Muttersprache zu feiern.
Dieser Tag ist ein von der UNESCO ausgerufener Gedenktag zur „Förderung sprachlicher und kultureller Vielfalt und Mehrsprachigkeit". Er erinnert auch daran, dass jeder Mensch das Recht haben sollte, seine Muttersprache(n) zu sprechen.
 
Da am eigentlichen Gedenktag, dem 21.2., eine Veranstaltung nicht möglich war, feiern wir am 27. März diesen Tag mit einem vielfältigen und vielsprachigen Programm.
Anschließend ab 17:00 Uhr wird das Ende des Ramadan beim Zuckerfest gefeiert, bei dem es Tanz (für Frauen) und selbst gebackene Speisen gibt.
 
Wir freuen uns, Sie am 27.3. bei uns in der Villa der Kulturen begrüßen zu dürfen!
 
Herzliche Grüße
 
Halyna Yefremova und das Team von Kolibri e.V.
 
Kinder- und Elternzentrum "Kolibri" e.V.
Ritzenbergstr. 3, 01067 Dresden
 
Träger der Villa der Kulturen
Kraftwerk Mitte 2, 01067 Dresden
Mobil: 017684235979
info@kolibri-dresden.de

www.kolibri-dresden.de
   
 

Anhänge:
Plakat Tag der Muttersprache.pdf	482 KB
Subject: Test Email
"""

class MailContent(BaseModel):
    subject: str
    category: str
    sender: str
    sent_date: str | None
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
        response = ollama.chat(model="llama3.2:3b", messages=[{"role": "user", "content": f"{content}"}], format=MailContent.model_json_schema())
        assert "message" in response and "content" in response["message"], "Response should contain 'message' with 'content'"
        print("Ollama chat test passed. Response content:", response["message"]["content"])
        for e in response: print(e)
    except Exception as e:
        print(f"Ollama chat test failed: {e}")
        assert False, f"Ollama not available or model not loaded: {e}"


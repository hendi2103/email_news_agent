import json
import ollama


def analyze_relevance(content: str, model: str = 'llama3') -> dict:
    """Analyzes and summarizes email content and returns a JSON dict."""
    prompt = (
        "You are an email analysis assistant. Analyze the following email content and extract structured information.\n\n"
        "Categorize the email as either 'event announcement' or 'general information'.\n\n"
        "Return ONLY a valid JSON object with these exact keys:\n"
        "- category: 'event announcement' or 'general information'\n"
        "- sender: the sender's name and/or email address\n"
        "- original_sender: the original sender if the email was forwarded, otherwise null\n"
        "- date: the date the email was sent (as a string)\n"
        "- original_date: the original date if the email was forwarded, otherwise null\n"
        "- summary: a concise summary of the email content (maximum 320 characters)\n"
        "- event_date: the date of the event if applicable, otherwise null\n"
        "- event_time: the time of the event if applicable, otherwise null\n"
        "- event_location: the location of the event if applicable, otherwise null\n"
        "- link_to_event: a URL link to the event if available, otherwise null\n"
        "- registration_information: registration details or deadline if available, otherwise null\n\n"
        "Email content:\n"
        f"{content}\n\n"
        "Respond with only the JSON object, no additional text."
    )

    try:
        response = ollama.chat(
            model=model,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
    except Exception as e:
        raise RuntimeError(
            f"Failed to contact Ollama service or load model '{model}': {e}"
        ) from e

    response_text = response["message"]["content"].strip()

    # Extract JSON from the response, handling cases where the model
    # may wrap the JSON in markdown code fences
    if "```" in response_text:
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        if start != -1 and end > start:
            response_text = response_text[start:end]

    try:
        result = json.loads(response_text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"LLM returned a response that could not be parsed as JSON: {e}\n"
            f"Response was: {response_text}"
        ) from e

    # Enforce summary length limit
    if "summary" in result and result["summary"] and len(result["summary"]) > 320:
        result["summary"] = result["summary"][:320]

    return result

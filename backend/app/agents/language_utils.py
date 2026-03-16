LANGUAGE_LABELS = {
    "en_GB": "English (UK)",
    "en_US": "English (US)",
    "it": "Italian",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "pt": "Portuguese",
}


def language_instruction(lang_code: str | None) -> str:
    if not lang_code or lang_code == "en_GB":
        return ""
    label = LANGUAGE_LABELS.get(lang_code, "English (UK)")
    return f"\nIMPORTANT: You MUST reply in {label}. All output text must be written in {label}."

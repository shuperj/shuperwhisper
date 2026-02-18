"""Text formatting with Claude API and template fallback."""

_EMAIL_TONE_DESC = {
    1: "warm, friendly, and approachable",
    2: "polite and conversational",
    3: "standard professional",
    4: "formal and business-like",
    5: "very formal, corporate, and authoritative",
}

_PROMPT_DETAIL_DESC = {
    1: "Ultra-concise and direct. Minimize word count ruthlessly.",
    2: "Concise but clear. Remove unnecessary words.",
    3: "Balanced clarity and brevity.",
    4: "Detailed and well-structured. Include context and constraints.",
    5: (
        "Comprehensive and structured. Use sections, bullet points, "
        "explicit constraints, and examples where helpful."
    ),
}

_FILLER_WORDS = [
    "um", "uh", "like", "you know", "basically", "actually",
    "just", "sort of", "kind of", "i mean", "well",
]


class TextFormatter:
    """Formats transcribed text using Claude API with template fallback."""

    def __init__(self):
        self._client = None
        self._api_available = False
        self._init_api()

    def _init_api(self):
        try:
            import anthropic
            self._client = anthropic.Anthropic()
            self._api_available = True
        except Exception:
            self._api_available = False

    def format_text(
        self,
        text: str,
        mode: str,
        email_tone: int = 3,
        prompt_detail: int = 3,
    ) -> str:
        """Format text according to the specified mode.

        Tries Claude API first, falls back to template-based formatting.
        Returns original text for 'normal' mode.
        """
        if not text or mode == "normal":
            return text

        if self._api_available:
            try:
                return self._format_with_api(text, mode, email_tone, prompt_detail)
            except Exception:
                pass

        return self._format_with_template(text, mode, email_tone, prompt_detail)

    def _get_system_prompt(
        self, mode: str, email_tone: int, prompt_detail: int
    ) -> str:
        if mode == "professional_email":
            tone = _EMAIL_TONE_DESC.get(email_tone, _EMAIL_TONE_DESC[3])
            return (
                f"Rewrite this dictated text as a professional email. "
                f"Tone: {tone} ({email_tone}/5). "
                f"Maintain the core message but use proper grammar "
                f"and standard email conventions. "
                f"Output ONLY the formatted text, nothing else."
            )
        elif mode == "ai_prompt":
            detail = _PROMPT_DETAIL_DESC.get(prompt_detail, _PROMPT_DETAIL_DESC[3])
            return (
                f"Rewrite this dictated text as an AI prompt. "
                f"Detail level: {detail} ({prompt_detail}/5). "
                f"Remove filler words, structure for optimal AI comprehension. "
                f"Output ONLY the formatted text, nothing else."
            )
        return ""

    def _format_with_api(
        self,
        text: str,
        mode: str,
        email_tone: int,
        prompt_detail: int,
    ) -> str:
        system = self._get_system_prompt(mode, email_tone, prompt_detail)
        response = self._client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1024,
            system=system,
            messages=[{"role": "user", "content": text}],
        )
        return response.content[0].text

    def _format_with_template(
        self,
        text: str,
        mode: str,
        email_tone: int,
        prompt_detail: int,
    ) -> str:
        if mode == "professional_email":
            return self._template_professional(text, email_tone)
        elif mode == "ai_prompt":
            return self._template_ai_prompt(text, prompt_detail)
        return text

    def _template_professional(self, text: str, email_tone: int) -> str:
        text = text.strip()
        if not text:
            return text
        sentences = text.split(". ")
        result = ". ".join(s.strip().capitalize() for s in sentences if s.strip())
        if result and not result.endswith("."):
            result += "."
        if email_tone >= 4:
            result = f"Dear recipient,\n\n{result}\n\nBest regards"
        return result

    def _template_ai_prompt(self, text: str, prompt_detail: int) -> str:
        result = text.strip()
        for filler in _FILLER_WORDS:
            result = result.replace(f" {filler} ", " ")
            if result.lower().startswith(f"{filler} "):
                result = result[len(filler) + 1:]
        while "  " in result:
            result = result.replace("  ", " ")
        result = result.strip()
        if prompt_detail >= 4 and result:
            result = f"Task: {result}"
        return result

class RetrievalAgent:
    """
    Agno-powered grounded assistant with mandatory citations.
    """

    def answer(self, question: str, scope: dict | None = None) -> dict:
        # TODO: integrate retrieval and citation formatting.
        return {"question": question, "answer": "", "citations": [], "scope": scope or {}}


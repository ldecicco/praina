class ValidationAgent:
    """
    Agno-powered onboarding validator.
    Ensures structural and assignment consistency before project activation.
    """

    def run(self, project_id: str) -> dict:
        # TODO: bind to AssignmentValidationService + explainable issue output.
        return {"project_id": project_id, "issues": []}


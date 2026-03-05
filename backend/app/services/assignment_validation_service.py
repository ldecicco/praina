class AssignmentValidationService:
    """
    Validates the project assignment rule:
    - Every WP/Task/Milestone/Deliverable must have leader_organization and responsible_person.
    - responsible_person must be an active member of leader_organization.
    """

    def validate(self) -> list[str]:
        # TODO: implement data-backed validation checks.
        return []


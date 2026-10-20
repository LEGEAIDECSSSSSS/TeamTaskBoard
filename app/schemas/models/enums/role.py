from enum import Enum


class OrgRole(str, Enum):
    """What someone can do across a whole organisation. Granted only by an owner or through an invitation."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class TeamRole(str, Enum):
    """What someone can do inside one team. A person can lead one team and be a member of another."""

    LEAD = "lead"
    MEMBER = "member"

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, EmailStr, PlainSerializer, StringConstraints

from app.core.time import ensure_utc


def _strip(value):
    return value.strip() if isinstance(value, str) else value


def _lower(value: str) -> str:
    return value.lower()


# Validated with email-validator (syntax + domain rules), trimmed and lower-cased so one address is one account.
NormalizedEmail = Annotated[EmailStr, BeforeValidator(_strip), AfterValidator(_lower)]

PersonName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
OrgName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
ShortTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]


def validate_password_strength(value: str) -> str:
    if len(value) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if len(value) > 128:
        raise ValueError("Password must be at most 128 characters.")
    if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
        raise ValueError("Password must include at least one letter and one number.")
    return value


Password = Annotated[str, AfterValidator(validate_password_strength)]


def _serialize_utc(value: datetime) -> str:
    return ensure_utc(value).isoformat().replace("+00:00", "Z")


# Incoming datetimes are converted to UTC. Outgoing ones are always sent with a trailing Z.
UTCDatetimeIn = Annotated[datetime, AfterValidator(ensure_utc)]
UTCDatetime = Annotated[datetime, PlainSerializer(_serialize_utc, return_type=str, when_used="always")]

from pydantic import BaseModel, Field

from app.schemas.types import NormalizedEmail, Password, PersonName


class RegisterRequest(BaseModel):
    name: PersonName
    email: NormalizedEmail
    password: Password


class LoginRequest(BaseModel):
    email: NormalizedEmail
    password: str = Field(min_length=1, max_length=128)


class EmailRequest(BaseModel):
    email: NormalizedEmail


class TokenRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class ResetPasswordRequest(TokenRequest):
    password: Password


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: Password


class UpdateProfileRequest(BaseModel):
    name: PersonName

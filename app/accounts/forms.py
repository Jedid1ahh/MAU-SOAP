"""Registration and login forms for institutional accounts."""

from __future__ import annotations

from typing import ClassVar

from flask import current_app
from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    ValidationError,
)


class RegistrationForm(FlaskForm):
    """Shared fields and exact-domain validation for account registration."""

    domain_setting: ClassVar[str]

    full_name = StringField(
        "Full name",
        validators=[DataRequired(), Length(min=2, max=255)],
    )
    email = StringField(
        "Institutional email address",
        validators=[DataRequired(), Email(), Length(max=255)],
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(min=12, max=128)],
    )
    confirm_password = PasswordField(
        "Confirm password",
        validators=[
            DataRequired(),
            EqualTo("password", message="Passwords must match."),
        ],
    )
    submit = SubmitField("Create account")

    def validate_email(self, field) -> None:
        """Accept only the exact institutional domain for this account type."""

        configured_domain = str(current_app.config[self.domain_setting]).casefold()
        submitted_domain = (field.data or "").rsplit("@", 1)[-1].casefold()
        if submitted_domain != configured_domain:
            raise ValidationError(
                f"Use an email address ending in @{configured_domain}."
            )


class LecturerRegistrationForm(RegistrationForm):
    """Register a Lecturer using an official staff address."""

    domain_setting = "LECTURER_EMAIL_DOMAIN"


class StudentRegistrationForm(RegistrationForm):
    """Register a Student using an official student address."""

    domain_setting = "CANDIDATE_EMAIL_DOMAIN"


class AccountLoginForm(FlaskForm):
    """Authenticate an approved Lecturer or verified Student."""

    email = StringField(
        "Institutional email address",
        validators=[DataRequired(), Email(), Length(max=255)],
    )
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Log in")

"""Forms for passwordless Candidate verification."""

from flask import current_app
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import (
    DataRequired,
    Email,
    Length,
    Regexp,
    ValidationError,
)


class CandidateIdentityForm(FlaskForm):
    """Collect the Candidate's identity for one examination."""

    name = StringField(
        "Full name",
        validators=[DataRequired(), Length(min=2, max=255)],
    )
    email = StringField(
        "Institutional email address",
        validators=[DataRequired(), Email(), Length(max=255)],
    )
    submit = SubmitField("Send verification code")

    def validate_email(self, field) -> None:
        """Restrict verification to the configured domain."""

        configured_domain = current_app.config[
            "CANDIDATE_EMAIL_DOMAIN"
        ].lower()
        submitted_domain = (
            field.data or ""
        ).rsplit("@", 1)[-1].lower()

        if submitted_domain != configured_domain:
            raise ValidationError(
                f"Use an email address ending in "
                f"@{configured_domain}."
            )


class OTPVerificationForm(FlaskForm):
    """Accept exactly one six-digit Candidate OTP."""

    otp = StringField(
        "Six-digit verification code",
        validators=[
            DataRequired(),
            Regexp(
                r"^\d{6}$",
                message=(
                    "Enter the six-digit code from your email."
                ),
            ),
        ],
    )
    submit = SubmitField("Verify and continue")
"""Forms used by Admin authentication and account recovery."""

from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length


class LoginForm(FlaskForm):
    """Authenticate the pre-provisioned Admin."""

    email = StringField(
        "Email address",
        validators=[DataRequired(), Email(), Length(max=255)],
    )
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Log in")


class PasswordResetRequestForm(FlaskForm):
    """Request a reset link without revealing whether an account exists."""

    email = StringField(
        "Admin email address",
        validators=[DataRequired(), Email(), Length(max=255)],
    )
    submit = SubmitField("Send reset link")


class PasswordResetForm(FlaskForm):
    """Set a new Admin password from a valid reset link."""

    password = PasswordField(
        "New password",
        validators=[DataRequired(), Length(min=12, max=128)],
    )
    confirm_password = PasswordField(
        "Confirm new password",
        validators=[
            DataRequired(),
            EqualTo("password", message="Passwords must match."),
        ],
    )
    submit = SubmitField("Reset password")
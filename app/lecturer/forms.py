"""Lecturer course-roster forms."""

from flask_wtf import FlaskForm
from wtforms import SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length


class CourseInvitationForm(FlaskForm):
    """Invite one or more registered Students by institutional email."""

    student_emails = TextAreaField(
        "Registered Student email addresses",
        validators=[DataRequired(), Length(max=10000)],
        description="Separate addresses with commas, spaces, or new lines.",
    )
    submit = SubmitField("Send invitations")

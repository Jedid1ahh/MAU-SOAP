"""Student coursework forms."""

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField
from wtforms import SubmitField, TextAreaField
from wtforms.validators import Length, Optional


class AssignmentSubmissionForm(FlaskForm):
    text_response = TextAreaField(
        "Response", validators=[Optional(), Length(max=50000)]
    )
    submission_file = FileField(
        "Attachment",
        validators=[
            Optional(),
            FileAllowed(
                [
                    "pdf",
                    "doc",
                    "docx",
                    "ppt",
                    "pptx",
                    "xls",
                    "xlsx",
                    "csv",
                    "txt",
                    "zip",
                ],
                "Unsupported file type.",
            ),
        ],
    )
    submit = SubmitField("Submit assignment")

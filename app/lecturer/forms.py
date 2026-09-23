"""Lecturer course-roster forms."""

from flask_wtf import FlaskForm
from flask_wtf.file import FileAllowed, FileField, FileRequired
from wtforms import (
    BooleanField,
    DateTimeLocalField,
    DecimalField,
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
    URLField,
)
from wtforms.validators import (
    URL,
    DataRequired,
    InputRequired,
    Length,
    NumberRange,
    Optional,
)

from app.admin.exam_forms import QuestionForm
from app.models import DifficultyLevel


class CourseInvitationForm(FlaskForm):
    """Invite one or more registered Students by institutional email."""

    student_emails = TextAreaField(
        "Registered Student email addresses",
        validators=[DataRequired(), Length(max=10000)],
        description="Separate addresses with commas, spaces, or new lines.",
    )
    submit = SubmitField("Send invitations")


class QuestionBankForm(QuestionForm):
    """Create or edit a reusable categorized question."""

    category = StringField(
        "Category", validators=[DataRequired(), Length(min=2, max=100)]
    )
    difficulty = SelectField(
        "Difficulty",
        choices=[(item.value, item.value.title()) for item in DifficultyLevel],
        validators=[DataRequired()],
        default=DifficultyLevel.MEDIUM.value,
    )


class QuestionBankImportForm(FlaskForm):
    csv_file = FileField(
        "Question-bank CSV",
        validators=[FileRequired(), FileAllowed(["csv"], "Upload a CSV file.")],
    )
    submit = SubmitField("Import questions")


class QuestionAssemblyForm(FlaskForm):
    category = SelectField("Category", validators=[Optional()])
    difficulty = SelectField(
        "Difficulty",
        choices=[("", "Any difficulty")]
        + [(item.value, item.value.title()) for item in DifficultyLevel],
        validators=[Optional()],
    )
    random_count = IntegerField(
        "Number of random questions",
        validators=[Optional(), NumberRange(min=1, max=200)],
    )
    submit = SubmitField("Add to examination")


class AnnouncementForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=255)])
    body = TextAreaField("Announcement", validators=[DataRequired(), Length(max=10000)])
    is_pinned = BooleanField("Pin this announcement")
    submit = SubmitField("Publish announcement")


class MaterialForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=255)])
    description = TextAreaField(
        "Description", validators=[Optional(), Length(max=5000)]
    )
    external_url = URLField(
        "External link", validators=[Optional(), URL(), Length(max=2048)]
    )
    material_file = FileField(
        "File",
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
    submit = SubmitField("Add material")


class AssignmentForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=255)])
    instructions = TextAreaField(
        "Instructions", validators=[DataRequired(), Length(max=20000)]
    )
    due_at = DateTimeLocalField(
        "Due date and time (UTC)", format="%Y-%m-%dT%H:%M", validators=[DataRequired()]
    )
    max_marks = DecimalField(
        "Maximum marks",
        places=2,
        validators=[InputRequired(), NumberRange(min=0.01, max=999999.99)],
    )
    is_published = BooleanField("Visible to Students", default=True)
    submit = SubmitField("Save assignment")


class AssignmentGradeForm(FlaskForm):
    awarded_marks = DecimalField(
        "Awarded marks", places=2, validators=[InputRequired(), NumberRange(min=0)]
    )
    feedback = TextAreaField("Feedback", validators=[Optional(), Length(max=10000)])
    submit = SubmitField("Save grade")

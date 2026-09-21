"""Forms for Phase 4 examination and question management."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    DateTimeLocalField,
    DecimalField,
    IntegerField,
    SelectField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import (
    DataRequired,
    InputRequired,
    Length,
    NumberRange,
    Optional,
)

from app.models import MonitorType, QuestionType, ReleaseOption


class ExamForm(FlaskForm):
    """Create or update an examination's Phase 4 configuration."""

    title = StringField(
        "Examination title",
        validators=[DataRequired(), Length(max=255)],
    )
    instructions = TextAreaField(
        "Candidate instructions",
        validators=[Optional(), Length(max=5000)],
    )
    time_limit_minutes = IntegerField(
        "Time limit in minutes",
        validators=[
            InputRequired(),
            NumberRange(
                min=1,
                max=1440,
                message="Time limit must be between 1 and 1440 minutes.",
            ),
        ],
    )
    monitor_type = SelectField(
        "Webcam monitoring",
        choices=[
            (MonitorType.FACE.value, "Face presence"),
            (MonitorType.EYE_GAZE.value, "Eye/gaze monitoring"),
        ],
        validators=[DataRequired()],
    )
    release_option = SelectField(
        "Result release",
        choices=[
            (
                ReleaseOption.IMMEDIATE.value,
                "Immediately after grading",
            ),
            (
                ReleaseOption.SCHEDULED.value,
                "At a scheduled UTC time",
            ),
        ],
        default=ReleaseOption.IMMEDIATE.value,
        validators=[DataRequired()],
    )
    scheduled_release_at = DateTimeLocalField(
        "Scheduled release date and time (UTC)",
        format="%Y-%m-%dT%H:%M",
        validators=[Optional()],
    )
    submit = SubmitField("Save examination")

    def validate(self, extra_validators=None) -> bool:
        """Require a future UTC timestamp for scheduled result release."""

        is_valid = super().validate(extra_validators)
        if not is_valid:
            return False

        if self.release_option.data == ReleaseOption.SCHEDULED.value:
            if self.scheduled_release_at.data is None:
                self.scheduled_release_at.errors.append(
                    "Choose when the result should be released."
                )
                return False

            current_utc = datetime.now(UTC).replace(tzinfo=None)
            if self.scheduled_release_at.data <= current_utc:
                self.scheduled_release_at.errors.append(
                    "Scheduled release must be in the future."
                )
                return False

        return True


class QuestionForm(FlaskForm):
    """Create or update one positioned examination question."""

    question_text = TextAreaField(
        "Question",
        validators=[DataRequired(), Length(max=10000)],
    )
    question_type = SelectField(
        "Question type",
        choices=[
            (QuestionType.MCQ.value, "Multiple choice"),
            (QuestionType.SHORT_ANSWER.value, "Short answer"),
            (QuestionType.OPEN_ENDED.value, "Open ended"),
        ],
        validators=[DataRequired()],
    )
    marks = DecimalField(
        "Marks",
        places=2,
        validators=[
            DataRequired(),
            NumberRange(
                min=Decimal("0.01"),
                max=Decimal("999999.99"),
            ),
        ],
    )

    mcq_option_a = StringField(
        "Option A",
        validators=[Optional(), Length(max=1000)],
    )
    mcq_option_b = StringField(
        "Option B",
        validators=[Optional(), Length(max=1000)],
    )
    mcq_option_c = StringField(
        "Option C",
        validators=[Optional(), Length(max=1000)],
    )
    mcq_option_d = StringField(
        "Option D",
        validators=[Optional(), Length(max=1000)],
    )
    correct_option = SelectField(
        "Correct option",
        choices=[
            ("", "Select the correct option"),
            *[(key, key) for key in "ABCD"],
        ],
        validators=[Optional()],
    )

    short_answer = StringField(
        "Correct short answer",
        validators=[Optional(), Length(max=5000)],
    )
    short_answer_case_sensitive = BooleanField(
        "Answer is case-sensitive"
    )
    short_answer_trim_whitespace = BooleanField(
        "Ignore leading and trailing spaces",
        default=True,
    )
    submit = SubmitField("Save question")

    def validate(self, extra_validators=None) -> bool:
        """Apply requirements that depend on the selected question type."""

        is_valid = super().validate(extra_validators)
        if not is_valid:
            return False

        question_type = QuestionType(self.question_type.data)

        if question_type is QuestionType.MCQ:
            options = {
                "A": (self.mcq_option_a.data or "").strip(),
                "B": (self.mcq_option_b.data or "").strip(),
                "C": (self.mcq_option_c.data or "").strip(),
                "D": (self.mcq_option_d.data or "").strip(),
            }

            if not options["A"]:
                self.mcq_option_a.errors.append(
                    "Option A is required."
                )
                is_valid = False

            if not options["B"]:
                self.mcq_option_b.errors.append(
                    "Option B is required."
                )
                is_valid = False

            if (
                not self.correct_option.data
                or not options.get(self.correct_option.data, "")
            ):
                self.correct_option.errors.append(
                    "Select a correct option that contains an answer."
                )
                is_valid = False

        elif question_type is QuestionType.SHORT_ANSWER:
            if not (self.short_answer.data or "").strip():
                self.short_answer.errors.append(
                    "A correct short answer is required."
                )
                is_valid = False

        return is_valid

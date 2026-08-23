"""Forms for Phase 9 Admin manual grading."""

from decimal import Decimal

from flask_wtf import FlaskForm
from wtforms import DecimalField, TextAreaField
from wtforms.validators import InputRequired, Length, NumberRange, Optional


class ManualGradeForm(FlaskForm):
    """Validate one open-ended mark and optional Candidate feedback."""

    awarded_marks = DecimalField(
        "Awarded marks",
        places=2,
        validators=[
            InputRequired(),
            NumberRange(
                min=Decimal("0.00"),
                message="Awarded marks cannot be negative.",
            ),
        ],
    )
    feedback = TextAreaField(
        "Feedback",
        validators=[Optional(), Length(max=5000)],
    )
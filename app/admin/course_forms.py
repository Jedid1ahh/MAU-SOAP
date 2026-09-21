"""Forms for Admin course creation and Lecturer assignment."""

from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length


class CourseForm(FlaskForm):
    """Create or edit one Lecturer-assigned course workspace."""

    code = StringField(
        "Course code",
        validators=[DataRequired(), Length(min=2, max=50)],
    )
    title = StringField(
        "Course title",
        validators=[DataRequired(), Length(min=2, max=255)],
    )
    description = TextAreaField(
        "Course description",
        validators=[Length(max=5000)],
    )
    lecturer_id = SelectField(
        "Assigned Lecturer",
        coerce=int,
        validators=[DataRequired()],
    )
    submit = SubmitField("Save course")

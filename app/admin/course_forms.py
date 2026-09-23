"""Forms for Admin course creation and Lecturer assignment."""

from flask_wtf import FlaskForm
from wtforms import IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


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
    semester_id = SelectField("Academic session and semester", coerce=int, default=0)
    department_id = SelectField("Department", coerce=int, default=0)
    programme_id = SelectField("Programme", coerce=int, default=0)
    level = IntegerField(
        "Course level", validators=[Optional(), NumberRange(min=100, max=900)]
    )
    credit_units = IntegerField(
        "Credit units", validators=[Optional(), NumberRange(min=1, max=30)]
    )
    lecturer_id = SelectField(
        "Assigned Lecturer",
        coerce=int,
        validators=[DataRequired()],
    )
    submit = SubmitField("Save course")

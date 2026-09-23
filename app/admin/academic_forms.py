"""Forms for the Admin academic-structure registry."""

from flask_wtf import FlaskForm
from wtforms import BooleanField, DateField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, Optional


class AcademicSessionForm(FlaskForm):
    name = StringField(
        "Session name", validators=[DataRequired(), Length(min=4, max=50)]
    )
    start_date = DateField("Start date", validators=[DataRequired()])
    end_date = DateField("End date", validators=[DataRequired()])
    is_current = BooleanField("Make this the current academic session")
    submit = SubmitField("Add session")


class SemesterForm(FlaskForm):
    academic_session_id = SelectField(
        "Academic session", coerce=int, validators=[DataRequired()]
    )
    name = StringField(
        "Semester name", validators=[DataRequired(), Length(min=2, max=50)]
    )
    start_date = DateField("Start date", validators=[DataRequired()])
    end_date = DateField("End date", validators=[DataRequired()])
    is_current = BooleanField("Make this the current semester")
    submit = SubmitField("Add semester")


class FacultyForm(FlaskForm):
    code = StringField("Faculty code", validators=[DataRequired(), Length(max=30)])
    name = StringField("Faculty name", validators=[DataRequired(), Length(max=255)])
    submit = SubmitField("Add faculty")


class DepartmentForm(FlaskForm):
    faculty_id = SelectField("Faculty", coerce=int, validators=[DataRequired()])
    code = StringField("Department code", validators=[DataRequired(), Length(max=30)])
    name = StringField("Department name", validators=[DataRequired(), Length(max=255)])
    submit = SubmitField("Add department")


class ProgrammeForm(FlaskForm):
    department_id = SelectField("Department", coerce=int, validators=[DataRequired()])
    code = StringField("Programme code", validators=[DataRequired(), Length(max=30)])
    name = StringField("Programme name", validators=[DataRequired(), Length(max=255)])
    award = StringField("Award (optional)", validators=[Optional(), Length(max=100)])
    submit = SubmitField("Add programme")

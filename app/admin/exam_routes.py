"""Phase 4 Admin examination and question management routes."""

from __future__ import annotations

import secrets

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, select

from app.extensions import db
from app.models import Exam, MonitorType, Question, QuestionType, ReleaseOption

from . import admin_bp
from .auth import admin_required
from .exam_forms import ExamForm, QuestionForm


def _owned_exam(exam_id: int) -> Exam:
    """Load one examination belonging to the logged-in Admin."""

    exam = db.session.scalar(
        select(Exam).where(
            Exam.id == exam_id,
            Exam.admin_id == current_user.id,
        )
    )
    if exam is None:
        abort(404)
    return exam


def _owned_question(exam: Exam, question_id: int) -> Question:
    """Load one question belonging to the selected Admin-owned examination."""

    question = db.session.scalar(
        select(Question).where(
            Question.id == question_id,
            Question.exam_id == exam.id,
        )
    )
    if question is None:
        abort(404)
    return question


def _locked_redirect(exam: Exam):
    """Redirect structural writes after the first Candidate has started."""

    if not exam.is_locked:
        return None

    flash(
        "This examination is locked because a Candidate has already started it.",
        "error",
    )
    return redirect(url_for("admin.exam_detail", exam_id=exam.id))


def _apply_exam_form(exam: Exam, form: ExamForm) -> None:
    """Copy validated examination form values onto a model instance."""

    exam.title = form.title.data.strip()
    exam.course_code = form.course_code.data.strip().upper()
    exam.course_title = form.course_title.data.strip()
    exam.instructions = (form.instructions.data or "").strip() or None
    exam.time_limit_minutes = form.time_limit_minutes.data
    exam.monitor_type = MonitorType(form.monitor_type.data)


def _question_values(form: QuestionForm) -> dict:
    """Convert the conditional question form into model-ready values."""

    question_type = QuestionType(form.question_type.data)

    values = {
        "question_text": form.question_text.data.strip(),
        "question_type": question_type,
        "marks": form.marks.data,
        "options": None,
        "correct_answer": None,
        "short_answer_case_sensitive": False,
        "short_answer_trim_whitespace": True,
    }

    if question_type is QuestionType.MCQ:
        raw_options = {
            "A": form.mcq_option_a.data,
            "B": form.mcq_option_b.data,
            "C": form.mcq_option_c.data,
            "D": form.mcq_option_d.data,
        }

        values["options"] = {
            key: answer.strip()
            for key, answer in raw_options.items()
            if answer and answer.strip()
        }
        values["correct_answer"] = form.correct_option.data

    elif question_type is QuestionType.SHORT_ANSWER:
        values["correct_answer"] = form.short_answer.data.strip()
        values["short_answer_case_sensitive"] = (
            form.short_answer_case_sensitive.data
        )
        values["short_answer_trim_whitespace"] = (
            form.short_answer_trim_whitespace.data
        )

    return values


def _exam_form_for_edit(exam: Exam) -> ExamForm:
    """Create an edit form that serializes enum values correctly."""

    if request.method == "POST":
        return ExamForm()

    return ExamForm(
        data={
            "title": exam.title,
            "course_code": exam.course_code,
            "course_title": exam.course_title,
            "instructions": exam.instructions,
            "time_limit_minutes": exam.time_limit_minutes,
            "monitor_type": exam.monitor_type.value,
        }
    )


def _question_form_for_edit(question: Question) -> QuestionForm:
    """Create an edit form populated for any supported question type."""

    if request.method == "POST":
        return QuestionForm()

    options = question.options or {}

    data = {
        "question_text": question.question_text,
        "question_type": question.question_type.value,
        "marks": question.marks,
        "mcq_option_a": options.get("A", ""),
        "mcq_option_b": options.get("B", ""),
        "mcq_option_c": options.get("C", ""),
        "mcq_option_d": options.get("D", ""),
        "correct_option": (
            question.correct_answer
            if question.question_type is QuestionType.MCQ
            else ""
        ),
        "short_answer": (
            question.correct_answer
            if question.question_type is QuestionType.SHORT_ANSWER
            else ""
        ),
        "short_answer_case_sensitive": question.short_answer_case_sensitive,
        "short_answer_trim_whitespace": question.short_answer_trim_whitespace,
    }

    return QuestionForm(data=data)


@admin_bp.route("/exams/new", methods=["GET", "POST"])
@admin_required
def create_exam():
    """Create an Admin-owned examination and its random share token."""

    form = ExamForm()

    if form.validate_on_submit():
        exam = Exam(
            admin_id=current_user.id,
            title="",
            course_code="",
            course_title="",
            time_limit_minutes=1,
            monitor_type=MonitorType.FACE,
            release_option=ReleaseOption.IMMEDIATE,
            exam_link_token=secrets.token_urlsafe(32),
        )

        _apply_exam_form(exam, form)
        db.session.add(exam)
        db.session.commit()

        flash("Examination created. You can now add questions.", "success")
        return redirect(url_for("admin.exam_detail", exam_id=exam.id))

    return render_template(
        "admin/exam_form.html",
        form=form,
        form_title="Create examination",
        submit_label="Create examination",
    )


@admin_bp.get("/exams/<int:exam_id>")
@admin_required
def exam_detail(exam_id: int):
    """Show one examination, its questions, and its shareable link."""

    return render_template(
        "admin/exam_detail.html",
        exam=_owned_exam(exam_id),
    )


@admin_bp.route("/exams/<int:exam_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_exam(exam_id: int):
    """Update examination metadata before any Candidate starts."""

    exam = _owned_exam(exam_id)

    if locked_response := _locked_redirect(exam):
        return locked_response

    form = _exam_form_for_edit(exam)

    if form.validate_on_submit():
        _apply_exam_form(exam, form)
        db.session.commit()

        flash("Examination updated.", "success")
        return redirect(url_for("admin.exam_detail", exam_id=exam.id))

    return render_template(
        "admin/exam_form.html",
        form=form,
        form_title="Edit examination",
        submit_label="Save changes",
        exam=exam,
    )


@admin_bp.post("/exams/<int:exam_id>/delete")
@admin_required
def delete_exam(exam_id: int):
    """Delete an examination only before a Candidate starts it."""

    exam = _owned_exam(exam_id)

    if locked_response := _locked_redirect(exam):
        return locked_response

    exam.questions.clear()
    exam.verification_tokens.clear()
    db.session.delete(exam)
    db.session.commit()

    flash("Examination deleted.", "success")
    return redirect(url_for("admin.index"))


@admin_bp.route(
    "/exams/<int:exam_id>/questions/new",
    methods=["GET", "POST"],
)
@admin_required
def create_question(exam_id: int):
    """Append one question to an unlocked examination."""

    exam = _owned_exam(exam_id)

    if locked_response := _locked_redirect(exam):
        return locked_response

    form = QuestionForm()

    if form.validate_on_submit():
        max_position = db.session.scalar(
            select(func.max(Question.position)).where(
                Question.exam_id == exam.id
            )
        )

        question = Question(
            exam=exam,
            position=(max_position or 0) + 1,
            **_question_values(form),
        )

        db.session.add(question)
        db.session.commit()

        flash("Question added.", "success")
        return redirect(url_for("admin.exam_detail", exam_id=exam.id))

    return render_template(
        "admin/question_form.html",
        form=form,
        exam=exam,
        form_title="Add question",
        submit_label="Add question",
    )


@admin_bp.route(
    "/exams/<int:exam_id>/questions/<int:question_id>/edit",
    methods=["GET", "POST"],
)
@admin_required
def edit_question(exam_id: int, question_id: int):
    """Update a question before the examination becomes locked."""

    exam = _owned_exam(exam_id)
    question = _owned_question(exam, question_id)

    if locked_response := _locked_redirect(exam):
        return locked_response

    form = _question_form_for_edit(question)

    if form.validate_on_submit():
        for field_name, value in _question_values(form).items():
            setattr(question, field_name, value)

        db.session.commit()

        flash("Question updated.", "success")
        return redirect(url_for("admin.exam_detail", exam_id=exam.id))

    return render_template(
        "admin/question_form.html",
        form=form,
        exam=exam,
        question=question,
        form_title="Edit question",
        submit_label="Save question",
    )


@admin_bp.post(
    "/exams/<int:exam_id>/questions/<int:question_id>/delete"
)
@admin_required
def delete_question(exam_id: int, question_id: int):
    """Delete a question before the examination becomes locked."""

    exam = _owned_exam(exam_id)
    question = _owned_question(exam, question_id)

    if locked_response := _locked_redirect(exam):
        return locked_response

    db.session.delete(question)
    db.session.commit()

    flash("Question deleted.", "success")
    return redirect(url_for("admin.exam_detail", exam_id=exam.id))
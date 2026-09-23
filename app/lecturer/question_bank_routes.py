"""Lecturer question-bank management and exam assembly routes."""

from __future__ import annotations

import csv
import io
import secrets
from decimal import Decimal, InvalidOperation

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, select

from app.admin.exam_routes import _locked_redirect, _owned_exam
from app.extensions import db
from app.models import DifficultyLevel, Question, QuestionBankItem, QuestionType

from . import lecturer_bp
from .auth import lecturer_required
from .forms import QuestionAssemblyForm, QuestionBankForm, QuestionBankImportForm
from .routes import owned_course


def _bank_values(form: QuestionBankForm) -> dict:
    question_type = QuestionType(form.question_type.data)
    values = {
        "category": form.category.data.strip(),
        "difficulty": DifficultyLevel(form.difficulty.data),
        "question_text": form.question_text.data.strip(),
        "question_type": question_type,
        "marks": form.marks.data,
        "options": None,
        "correct_answer": None,
        "short_answer_case_sensitive": False,
        "short_answer_trim_whitespace": True,
    }
    if question_type is QuestionType.MCQ:
        raw = {
            "A": form.mcq_option_a.data,
            "B": form.mcq_option_b.data,
            "C": form.mcq_option_c.data,
            "D": form.mcq_option_d.data,
        }
        values["options"] = {
            key: value.strip() for key, value in raw.items() if value and value.strip()
        }
        values["correct_answer"] = form.correct_option.data
    elif question_type is QuestionType.SHORT_ANSWER:
        values["correct_answer"] = form.short_answer.data.strip()
        values["short_answer_case_sensitive"] = form.short_answer_case_sensitive.data
        values["short_answer_trim_whitespace"] = form.short_answer_trim_whitespace.data
    return values


def _bank_form_for_edit(item: QuestionBankItem) -> QuestionBankForm:
    if request.method == "POST":
        return QuestionBankForm()
    options = item.options or {}
    return QuestionBankForm(
        data={
            "category": item.category,
            "difficulty": item.difficulty.value,
            "question_text": item.question_text,
            "question_type": item.question_type.value,
            "marks": item.marks,
            "mcq_option_a": options.get("A", ""),
            "mcq_option_b": options.get("B", ""),
            "mcq_option_c": options.get("C", ""),
            "mcq_option_d": options.get("D", ""),
            "correct_option": item.correct_answer or "",
            "short_answer": (
                item.correct_answer
                if item.question_type is QuestionType.SHORT_ANSWER
                else ""
            ),
            "short_answer_case_sensitive": item.short_answer_case_sensitive,
            "short_answer_trim_whitespace": item.short_answer_trim_whitespace,
        }
    )


def _owned_bank_item(course_id: int, item_id: int) -> QuestionBankItem:
    item = db.session.scalar(
        select(QuestionBankItem).where(
            QuestionBankItem.id == item_id,
            QuestionBankItem.course_id == course_id,
            QuestionBankItem.lecturer_id == current_user.id,
        )
    )
    if item is None:
        abort(404)
    return item


def _copy_to_exam(item: QuestionBankItem, exam, position: int) -> Question:
    return Question(
        exam=exam,
        source_bank_item_id=item.id,
        position=position,
        question_text=item.question_text,
        question_type=item.question_type,
        marks=item.marks,
        options=dict(item.options) if item.options else None,
        correct_answer=item.correct_answer,
        short_answer_case_sensitive=item.short_answer_case_sensitive,
        short_answer_trim_whitespace=item.short_answer_trim_whitespace,
    )


@lecturer_bp.get("/courses/<int:course_id>/question-bank")
@lecturer_required
def question_bank(course_id: int):
    course = owned_course(course_id)
    items = db.session.scalars(
        select(QuestionBankItem)
        .where(QuestionBankItem.course_id == course.id)
        .order_by(QuestionBankItem.category, QuestionBankItem.created_at.desc())
    ).all()
    return render_template(
        "lecturer/question_bank.html",
        course=course,
        items=items,
        import_form=QuestionBankImportForm(),
    )


@lecturer_bp.route(
    "/courses/<int:course_id>/question-bank/new", methods=["GET", "POST"]
)
@lecturer_required
def create_bank_item(course_id: int):
    course = owned_course(course_id)
    form = QuestionBankForm()
    if form.validate_on_submit():
        db.session.add(
            QuestionBankItem(
                course=course,
                lecturer_id=current_user.id,
                **_bank_values(form),
            )
        )
        db.session.commit()
        flash("Question saved to the course bank.", "success")
        return redirect(url_for("lecturer.question_bank", course_id=course.id))
    return render_template(
        "lecturer/question_bank_form.html",
        course=course,
        form=form,
        form_title="Add bank question",
    )


@lecturer_bp.route(
    "/courses/<int:course_id>/question-bank/<int:item_id>/edit",
    methods=["GET", "POST"],
)
@lecturer_required
def edit_bank_item(course_id: int, item_id: int):
    course = owned_course(course_id)
    item = _owned_bank_item(course.id, item_id)
    form = _bank_form_for_edit(item)
    if form.validate_on_submit():
        for name, value in _bank_values(form).items():
            setattr(item, name, value)
        db.session.commit()
        flash("Question-bank item updated.", "success")
        return redirect(url_for("lecturer.question_bank", course_id=course.id))
    return render_template(
        "lecturer/question_bank_form.html",
        course=course,
        item=item,
        form=form,
        form_title="Edit bank question",
    )


@lecturer_bp.post("/courses/<int:course_id>/question-bank/<int:item_id>/delete")
@lecturer_required
def delete_bank_item(course_id: int, item_id: int):
    course = owned_course(course_id)
    item = _owned_bank_item(course.id, item_id)
    db.session.delete(item)
    db.session.commit()
    flash("Question removed from the bank.", "success")
    return redirect(url_for("lecturer.question_bank", course_id=course.id))


def _csv_item(row: dict[str, str], course) -> QuestionBankItem:
    question_type = QuestionType(row.get("question_type", "").strip().casefold())
    difficulty = DifficultyLevel(
        (row.get("difficulty") or DifficultyLevel.MEDIUM.value).strip().casefold()
    )
    question_text = row.get("question_text", "").strip()
    category = row.get("category", "").strip()
    if not question_text or not category:
        raise ValueError("category and question_text are required")
    try:
        marks = Decimal(row.get("marks", ""))
    except InvalidOperation as error:
        raise ValueError("marks must be numeric") from error
    if marks <= 0:
        raise ValueError("marks must be positive")
    options = None
    correct_answer = (row.get("correct_answer") or "").strip() or None
    if question_type is QuestionType.MCQ:
        options = {
            key: row.get(f"option_{key.casefold()}", "").strip()
            for key in "ABCD"
            if row.get(f"option_{key.casefold()}", "").strip()
        }
        if len(options) < 2 or correct_answer not in options:
            raise ValueError("MCQ rows require two options and a valid correct_answer")
    elif question_type is QuestionType.SHORT_ANSWER and not correct_answer:
        raise ValueError("short-answer rows require correct_answer")
    else:
        correct_answer = (
            None if question_type is QuestionType.OPEN_ENDED else correct_answer
        )
    return QuestionBankItem(
        course=course,
        lecturer_id=current_user.id,
        category=category,
        difficulty=difficulty,
        question_text=question_text,
        question_type=question_type,
        marks=marks,
        options=options,
        correct_answer=correct_answer,
        short_answer_case_sensitive=(
            (row.get("case_sensitive") or "").strip().casefold() in {"1", "true", "yes"}
        ),
        short_answer_trim_whitespace=(
            (row.get("trim_whitespace") or "true").strip().casefold()
            not in {"0", "false", "no"}
        ),
    )


@lecturer_bp.post("/courses/<int:course_id>/question-bank/import")
@lecturer_required
def import_question_bank(course_id: int):
    course = owned_course(course_id)
    form = QuestionBankImportForm()
    if not form.validate_on_submit():
        flash("Choose a valid CSV file.", "error")
        return redirect(url_for("lecturer.question_bank", course_id=course.id))
    raw = form.csv_file.data.read(1_000_001)
    if len(raw) > 1_000_000:
        flash("Question-bank CSV files are limited to 1 MB.", "error")
        return redirect(url_for("lecturer.question_bank", course_id=course.id))
    try:
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        if not rows or len(rows) > 500:
            raise ValueError("CSV must contain between 1 and 500 questions")
        items = [_csv_item(row, course) for row in rows]
    except (UnicodeDecodeError, ValueError) as error:
        db.session.rollback()
        flash(f"Question-bank import failed: {error}.", "error")
        return redirect(url_for("lecturer.question_bank", course_id=course.id))
    db.session.add_all(items)
    db.session.commit()
    flash(f"Imported {len(items)} question-bank item(s).", "success")
    return redirect(url_for("lecturer.question_bank", course_id=course.id))


@lecturer_bp.route("/exams/<int:exam_id>/question-bank", methods=["GET", "POST"])
@lecturer_required
def assemble_from_bank(exam_id: int):
    exam = _owned_exam(exam_id)
    if locked_response := _locked_redirect(exam):
        return locked_response
    items = db.session.scalars(
        select(QuestionBankItem)
        .where(QuestionBankItem.course_id == exam.course_id)
        .order_by(QuestionBankItem.category, QuestionBankItem.created_at)
    ).all()
    categories = sorted({item.category for item in items})
    form = QuestionAssemblyForm()
    form.category.choices = [("", "Any category")] + [
        (value, value) for value in categories
    ]
    if form.validate_on_submit():
        selected_ids = {
            int(value)
            for value in request.form.getlist("bank_item_ids")
            if value.isdigit()
        }
        pool = [
            item
            for item in items
            if (not form.category.data or item.category == form.category.data)
            and (
                not form.difficulty.data
                or item.difficulty.value == form.difficulty.data
            )
        ]
        chosen = [item for item in items if item.id in selected_ids]
        if form.random_count.data:
            available = [item for item in pool if item not in chosen]
            if form.random_count.data > len(available):
                form.random_count.errors.append(
                    f"Only {len(available)} matching bank question(s) are available."
                )
            else:
                chosen.extend(
                    secrets.SystemRandom().sample(available, form.random_count.data)
                )
        if not form.errors and chosen:
            existing_sources = {
                question.source_bank_item_id
                for question in exam.questions
                if question.source_bank_item_id is not None
            }
            chosen = [item for item in chosen if item.id not in existing_sources]
            max_position = (
                db.session.scalar(
                    select(func.max(Question.position)).where(
                        Question.exam_id == exam.id
                    )
                )
                or 0
            )
            for offset, item in enumerate(chosen, start=1):
                db.session.add(_copy_to_exam(item, exam, max_position + offset))
            db.session.commit()
            flash(f"Added {len(chosen)} question(s) from the bank.", "success")
            return redirect(url_for("lecturer.exam_detail", exam_id=exam.id))
        if not chosen and not form.errors:
            flash("Select at least one question or request a random set.", "error")
    return render_template(
        "lecturer/question_bank_assemble.html",
        exam=exam,
        items=items,
        form=form,
    )

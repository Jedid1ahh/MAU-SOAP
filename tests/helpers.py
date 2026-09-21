"""Shared factories for course-centered test data."""

from datetime import UTC, datetime

from sqlalchemy import select

from app.extensions import bcrypt, db
from app.models import (
    Course,
    CourseEnrollment,
    EnrollmentStatus,
    Exam,
    Role,
    User,
)


def course_for(owner: User, code: str, title: str) -> Course:
    """Return a persisted course suitable for an Exam owned by ``owner``."""

    normalized_code = code.strip().upper()
    course = next(
        (
            item
            for item in db.session.new
            if isinstance(item, Course) and item.code == normalized_code
        ),
        None,
    )
    if course is None:
        course = db.session.scalar(
            select(Course).where(Course.code == normalized_code)
        )
    if course is not None:
        return course

    creator = owner
    if owner.role is not Role.ADMIN:
        creator = db.session.scalar(
            select(User).where(User.role == Role.ADMIN)
        ) or owner
    course = Course(
        code=normalized_code,
        title=title,
        lecturer=owner if owner.role is Role.LECTURER else None,
        created_by=creator,
    )
    db.session.add(course)
    db.session.flush()
    return course


def authenticate_enrolled_student(
    client,
    exam: Exam,
    *,
    email: str = "amina@student.mau.edu.ng",
    name: str = "Amina Bello",
    accepted: bool = True,
) -> User:
    """Create and authenticate a Student with an invitation to ``exam``."""

    normalized_email = email.strip().casefold()
    password = "RouteTestPassword!"
    student = db.session.scalar(select(User).where(User.email == normalized_email))
    if student is None:
        now = datetime.now(UTC)
        student = User(
            full_name=name,
            email=normalized_email,
            password_hash=bcrypt.generate_password_hash(password, rounds=4).decode(
                "utf-8"
            ),
            role=Role.STUDENT,
            email_verified_at=now,
            approved_at=now,
        )
        db.session.add(student)
        db.session.flush()

    enrollment = db.session.scalar(
        select(CourseEnrollment).where(
            CourseEnrollment.course_id == exam.course_id,
            CourseEnrollment.student_id == student.id,
        )
    )
    if enrollment is None:
        enrollment = CourseEnrollment(
            course=exam.course,
            student=student,
            status=(
                EnrollmentStatus.ACCEPTED
                if accepted
                else EnrollmentStatus.PENDING
            ),
            accepted_at=datetime.now(UTC) if accepted else None,
        )
        db.session.add(enrollment)
    db.session.commit()

    client.post("/account/logout")
    response = client.post(
        "/account/login",
        data={"email": student.email, "password": password},
    )
    assert response.status_code == 302

    return student

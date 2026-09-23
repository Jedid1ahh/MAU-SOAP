"""Integrated coverage for academic, assessment, and coursework phases."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.candidate.session_services import (
    exam_availability,
    start_submission,
    submission_deadline,
)
from app.extensions import bcrypt, db
from app.models import (
    AcademicSession,
    Assignment,
    AssignmentSubmission,
    Course,
    CourseAnnouncement,
    CourseEnrollment,
    CourseMaterial,
    DifficultyLevel,
    EnrollmentStatus,
    Exam,
    ExamAccommodation,
    Faculty,
    MonitorType,
    Question,
    QuestionBankItem,
    QuestionType,
    ReleaseOption,
    Role,
    User,
)


def _login(client, user: User, password: str):
    return client.post(
        "/account/login", data={"email": user.email, "password": password}
    )


def _student(email="student@student.mau.edu.ng") -> User:
    student = User(
        full_name="Amina Bello",
        email=email,
        password_hash=bcrypt.generate_password_hash("StudentPassword!").decode(),
        role=Role.STUDENT,
        email_verified_at=datetime.now(UTC),
    )
    db.session.add(student)
    db.session.commit()
    return student


def _course(admin: User, lecturer: User, code="CSC 450") -> Course:
    course = Course(
        code=code,
        title="Applied Computing",
        lecturer=lecturer,
        created_by=admin,
    )
    db.session.add(course)
    db.session.commit()
    return course


def _enroll(course: Course, student: User, lecturer: User) -> None:
    db.session.add(
        CourseEnrollment(
            course=course,
            student=student,
            invited_by=lecturer,
            status=EnrollmentStatus.ACCEPTED,
            accepted_at=datetime.now(UTC),
        )
    )
    db.session.commit()


def _exam(course: Course, lecturer: User, **values) -> Exam:
    exam = Exam(
        course=course,
        admin=lecturer,
        title="Final Examination",
        course_code=course.code,
        course_title=course.title,
        time_limit_minutes=30,
        monitor_type=MonitorType.FACE,
        release_option=ReleaseOption.IMMEDIATE,
        exam_link_token=f"token-{course.code}",
        **values,
    )
    db.session.add(exam)
    db.session.commit()
    return exam


def test_admin_builds_academic_structure(client, admin):
    client.post(
        "/admin/login",
        data={"email": admin.email, "password": "Phase3TestPassword!"},
    )
    session_response = client.post(
        "/admin/academic-structure/sessions",
        data={
            "session-name": "2026/2027",
            "session-start_date": "2026-09-01",
            "session-end_date": "2027-07-31",
            "session-is_current": "y",
        },
    )
    faculty_response = client.post(
        "/admin/academic-structure/faculties",
        data={"faculty-code": "FSC", "faculty-name": "Faculty of Science"},
    )
    page = client.get("/admin/academic-structure")
    assert session_response.status_code == 302
    assert faculty_response.status_code == 302
    assert b"2026/2027" in page.data
    assert b"Faculty of Science" in page.data
    assert db.session.scalar(select(AcademicSession)).is_current
    assert db.session.scalar(select(Faculty)).code == "FSC"


def test_question_bank_creates_imports_and_assembles(client, admin, lecturer):
    course = _course(admin, lecturer)
    exam = _exam(course, lecturer)
    _login(client, lecturer, "LecturerTestPassword!")
    created = client.post(
        f"/lecturer/courses/{course.id}/question-bank/new",
        data={
            "category": "Algorithms",
            "difficulty": DifficultyLevel.MEDIUM.value,
            "question_text": "What is an algorithm?",
            "question_type": QuestionType.MCQ.value,
            "marks": "2.00",
            "mcq_option_a": "A finite procedure",
            "mcq_option_b": "A database",
            "correct_option": "A",
        },
    )
    item = db.session.scalar(select(QuestionBankItem))
    assembled = client.post(
        f"/lecturer/exams/{exam.id}/question-bank",
        data={"bank_item_ids": str(item.id), "category": "", "difficulty": ""},
    )
    question = db.session.scalar(select(Question))
    assert created.status_code == 302
    assert assembled.status_code == 302
    assert question.source_bank_item_id == item.id
    assert question.correct_answer == "A"


def test_exam_controls_attempts_randomization_and_accommodation(app, admin, lecturer):
    student = _student()
    course = _course(admin, lecturer)
    _enroll(course, student, lecturer)
    exam = _exam(
        course,
        lecturer,
        attempt_limit=2,
        shuffle_questions=True,
        shuffle_options=True,
    )
    db.session.add_all(
        [
            Question(
                exam=exam,
                position=position,
                question_text=f"Question {position}",
                question_type=QuestionType.MCQ,
                marks=Decimal("1.00"),
                options={"A": "First", "B": "Second"},
                correct_answer="A",
            )
            for position in (1, 2)
        ]
    )
    db.session.add(ExamAccommodation(exam=exam, student=student, extra_time_minutes=15))
    db.session.commit()
    first, created = start_submission(exam, student)
    db.session.commit()
    assert created is True
    assert first.attempt_number == 1
    assert set(first.question_order) == {question.id for question in exam.questions}
    assert set(first.option_orders[str(exam.questions[0].id)]) == {"A", "B"}
    assert submission_deadline(first) == first.started_at.replace(
        tzinfo=UTC
    ) + timedelta(minutes=45)
    first.submitted_at = datetime.now(UTC)
    db.session.commit()
    second, created = start_submission(exam, student)
    assert created is True
    assert second.attempt_number == 2
    exam.opens_at = datetime.now(UTC) + timedelta(hours=1)
    assert exam_availability(exam) == "upcoming"


def test_coursework_moves_from_lecturer_to_student_and_back(client, admin, lecturer):
    student = _student()
    course = _course(admin, lecturer)
    _enroll(course, student, lecturer)
    _login(client, lecturer, "LecturerTestPassword!")
    assert (
        client.post(
            f"/lecturer/courses/{course.id}/announcements",
            data={"title": "Welcome", "body": "Read the course guide."},
        ).status_code
        == 302
    )
    assert (
        client.post(
            f"/lecturer/courses/{course.id}/materials",
            data={"title": "Reference", "external_url": "https://example.com/guide"},
        ).status_code
        == 302
    )
    due_at = (datetime.now(UTC) + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
    response = client.post(
        f"/lecturer/courses/{course.id}/assignments/new",
        data={
            "title": "Essay",
            "instructions": "Explain server-authoritative timing.",
            "due_at": due_at,
            "max_marks": "20",
            "is_published": "y",
        },
    )
    assignment = db.session.scalar(select(Assignment))
    assert response.status_code == 302
    client.post("/account/logout")
    _login(client, student, "StudentPassword!")
    page = client.get(f"/student/courses/{course.id}")
    submitted = client.post(
        f"/student/assignments/{assignment.id}",
        data={"text_response": "The server owns the deadline."},
    )
    submission = db.session.scalar(select(AssignmentSubmission))
    assert b"Welcome" in page.data
    assert b"Reference" in page.data
    assert submitted.status_code == 302
    assert submission.text_response == "The server owns the deadline."
    client.post("/account/logout")
    _login(client, lecturer, "LecturerTestPassword!")
    graded = client.post(
        f"/lecturer/assignments/{assignment.id}/submissions/{submission.id}/grade",
        data={"awarded_marks": "18", "feedback": "Strong answer."},
    )
    db.session.refresh(submission)
    assert graded.status_code == 302
    assert submission.awarded_marks == Decimal("18.00")
    assert submission.feedback == "Strong answer."
    assert db.session.scalar(select(CourseAnnouncement)) is not None
    assert db.session.scalar(select(CourseMaterial)) is not None

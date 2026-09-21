"""Course ownership, invitation, enrollment, and access-control tests."""

from datetime import UTC, datetime

from sqlalchemy import select

from app.extensions import bcrypt, db, mail
from app.models import (
    Course,
    CourseEnrollment,
    EnrollmentStatus,
    Exam,
    MonitorType,
    ReleaseOption,
    Role,
    User,
    VerificationToken,
)


def _admin_login(client):
    return client.post(
        "/admin/login",
        data={
            "email": "admin@mau.edu.ng",
            "password": "Phase3TestPassword!",
        },
    )


def _portal_login(client, user: User, password: str):
    return client.post(
        "/account/login",
        data={"email": user.email, "password": password},
    )


def _account(email: str, role: Role, password: str, *, active=True) -> User:
    now = datetime.now(UTC)
    user = User(
        full_name=email.split("@", 1)[0].replace(".", " ").title(),
        email=email,
        password_hash=bcrypt.generate_password_hash(password).decode("utf-8"),
        role=role,
        is_active=active,
        email_verified_at=now,
        approved_at=now if role is Role.LECTURER else None,
    )
    db.session.add(user)
    db.session.commit()
    return user


def _exam(course: Course, lecturer: User) -> Exam:
    exam = Exam(
        course=course,
        admin=lecturer,
        title="Course Examination",
        course_code=course.code,
        course_title=course.title,
        time_limit_minutes=30,
        monitor_type=MonitorType.FACE,
        release_option=ReleaseOption.IMMEDIATE,
        exam_link_token="course-workspace-exam",
    )
    db.session.add(exam)
    db.session.commit()
    return exam


def test_admin_creates_validates_and_transfers_complete_course_workspace(
    client, admin, lecturer
):
    second = _account(
        "second.lecturer@mau.edu.ng",
        Role.LECTURER,
        "SecondLecturerPassword!",
    )
    _admin_login(client)

    page = client.get("/admin/courses/new")
    invalid = client.post(
        "/admin/courses/new",
        data={"code": "", "title": "", "lecturer_id": ""},
    )
    assert page.status_code == 200
    assert lecturer.email.encode() in page.data
    assert invalid.status_code == 200
    assert b"This field is required" in invalid.data

    created = client.post(
        "/admin/courses/new",
        data={
            "code": " csc 451 ",
            "title": " Distributed Applications ",
            "description": " Course workspace ",
            "lecturer_id": str(lecturer.id),
        },
    )
    course = db.session.scalar(select(Course).where(Course.code == "CSC 451"))
    assert created.status_code == 302
    assert course is not None
    assert course.title == "Distributed Applications"
    assert course.description == "Course workspace"
    assert course.lecturer_id == lecturer.id
    assert course.created_by_admin_id == admin.id
    assert "Course" in repr(course)

    duplicate = client.post(
        "/admin/courses/new",
        data={
            "code": "CSC 451",
            "title": "Duplicate",
            "lecturer_id": str(lecturer.id),
        },
    )
    assert b"already exists" in duplicate.data

    exam = _exam(course, lecturer)
    edit_page = client.get(f"/admin/courses/{course.id}/edit")
    unchanged_owner = client.post(
        f"/admin/courses/{course.id}/edit",
        data={
            "code": course.code,
            "title": course.title,
            "description": course.description,
            "lecturer_id": str(lecturer.id),
        },
    )
    transferred = client.post(
        f"/admin/courses/{course.id}/edit",
        data={
            "code": "CSC 452",
            "title": "Advanced Distributed Applications",
            "description": "",
            "lecturer_id": str(second.id),
        },
    )
    assert edit_page.status_code == 200
    assert unchanged_owner.status_code == 302
    assert transferred.status_code == 302
    assert course.code == "CSC 452"
    assert course.description is None
    assert course.lecturer_id == second.id
    assert exam.admin_id == second.id
    assert exam.course_code == "CSC 452"
    assert exam.course_title == "Advanced Distributed Applications"

    client.post("/admin/logout")
    _portal_login(client, lecturer, "LecturerTestPassword!")
    assert client.get(f"/lecturer/courses/{course.id}").status_code == 404
    client.post("/account/logout")
    _portal_login(client, second, "SecondLecturerPassword!")
    assert client.get(f"/lecturer/courses/{course.id}").status_code == 200
    assert client.get(f"/lecturer/exams/{exam.id}").status_code == 200

    client.post("/account/logout")
    _admin_login(client)
    assert client.get("/admin/courses/999999/edit").status_code == 404
    assert client.get(f"/admin/exams/{exam.id}").status_code == 404


def test_course_edit_rejects_duplicate_code(client, admin, lecturer):
    first = Course(
        code="CSC 401",
        title="Algorithms",
        lecturer=lecturer,
        created_by=admin,
    )
    second = Course(
        code="CSC 402",
        title="Databases",
        lecturer=lecturer,
        created_by=admin,
    )
    db.session.add_all([first, second])
    db.session.commit()
    _admin_login(client)

    response = client.post(
        f"/admin/courses/{second.id}/edit",
        data={
            "code": first.code,
            "title": second.title,
            "description": "",
            "lecturer_id": str(lecturer.id),
        },
    )
    assert response.status_code == 200
    assert b"already exists" in response.data
    assert second.code == "CSC 402"


def test_lecturer_invites_registered_students_and_student_accepts(
    client, admin, lecturer
):
    password = "StudentCoursePassword!"
    student = _account("amina@student.mau.edu.ng", Role.STUDENT, password)
    inactive = _account(
        "inactive@student.mau.edu.ng", Role.STUDENT, password, active=False
    )
    course = Course(
        code="CSC 460",
        title="Cloud Computing",
        lecturer=lecturer,
        created_by=admin,
    )
    other_course = Course(
        code="CSC 461",
        title="Computer Graphics",
        created_by=admin,
    )
    db.session.add_all([course, other_course])
    db.session.commit()
    exam = _exam(course, lecturer)

    _portal_login(client, lecturer, "LecturerTestPassword!")
    assert client.get(f"/lecturer/courses/{other_course.id}").status_code == 404
    empty = client.post(
        f"/lecturer/courses/{course.id}/invitations",
        data={"student_emails": ""},
        follow_redirects=True,
    )
    assert b"Enter at least one" in empty.data

    invited = client.post(
        f"/lecturer/courses/{course.id}/invitations",
        data={
            "student_emails": (
                "AMINA@student.mau.edu.ng, amina@student.mau.edu.ng; "
                "missing@student.mau.edu.ng inactive@student.mau.edu.ng "
                "outsider@gmail.com"
            )
        },
        follow_redirects=True,
    )
    enrollment = db.session.scalar(
        select(CourseEnrollment).where(
            CourseEnrollment.course_id == course.id,
            CourseEnrollment.student_id == student.id,
        )
    )
    assert enrollment is not None
    assert enrollment.status is EnrollmentStatus.PENDING
    assert enrollment.invited_by_lecturer_id == lecturer.id
    assert b"Sent 1 course invitation" in invited.data
    assert b"Ignored non-student-domain" in invited.data
    assert b"No registered Student account" in invited.data
    assert inactive.email.encode() in invited.data
    assert "CourseEnrollment" in repr(enrollment)

    repeated = client.post(
        f"/lecturer/courses/{course.id}/invitations",
        data={"student_emails": student.email},
        follow_redirects=True,
    )
    assert b"already invited or enrolled" in repeated.data

    client.post("/account/logout")
    _portal_login(client, student, password)
    dashboard = client.get("/student/")
    assert b"Courses waiting for you" in dashboard.data
    assert course.title.encode() in dashboard.data
    assert client.post("/student/invitations/999999/accept").status_code == 404

    accepted = client.post(
        f"/student/invitations/{enrollment.id}/accept",
        follow_redirects=True,
    )
    assert accepted.status_code == 200
    assert b"now enrolled" in accepted.data
    assert b"Course Examination" in accepted.data
    assert enrollment.status is EnrollmentStatus.ACCEPTED
    assert enrollment.accepted_at is not None
    assert enrollment.is_accepted is True

    repeated_accept = client.post(
        f"/student/invitations/{enrollment.id}/accept",
        follow_redirects=True,
    )
    assert b"already accepted" in repeated_accept.data

    client.post("/account/logout")
    _portal_login(client, lecturer, "LecturerTestPassword!")
    roster = client.get(f"/lecturer/courses/{course.id}")
    assert student.full_name.encode() in roster.data
    assert student.email.encode() in roster.data
    assert exam.title.encode() in roster.data
    reinvite = client.post(
        f"/lecturer/courses/{course.id}/invitations",
        data={"student_emails": student.email},
        follow_redirects=True,
    )
    assert b"already invited or enrolled" in reinvite.data


def test_exam_link_requires_accepted_registered_course_membership(
    client, admin, lecturer
):
    password = "EnrollmentGatePassword!"
    student = _account("gate@student.mau.edu.ng", Role.STUDENT, password)
    course = Course(
        code="CSC 470",
        title="Secure Computing",
        lecturer=lecturer,
        created_by=admin,
    )
    enrollment = CourseEnrollment(
        course=course,
        student=student,
        invited_by=lecturer,
        status=EnrollmentStatus.PENDING,
    )
    db.session.add_all([course, enrollment])
    db.session.commit()
    exam = _exam(course, lecturer)
    access_url = f"/exam/{exam.exam_link_token}"

    blocked = client.post(
        access_url,
        data={"name": student.full_name, "email": student.email},
    )
    assert blocked.status_code == 200
    assert b"Accept this course invitation" in blocked.data
    assert db.session.scalar(select(VerificationToken)) is None

    enrollment.status = EnrollmentStatus.ACCEPTED
    enrollment.accepted_at = datetime.now(UTC)
    db.session.commit()
    with mail.record_messages() as outbox:
        allowed = client.post(
            access_url,
            data={"name": student.full_name, "email": student.email},
        )
    assert allowed.status_code == 302
    assert len(outbox) == 1
    assert db.session.scalar(select(VerificationToken)) is not None

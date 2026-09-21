"""Tests for institutional registration, approval, and role access."""

import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy import select

from app.accounts.services import (
    aware_utc,
    create_account_verification,
    resolve_account_verification,
    send_account_verification_email,
    token_digest,
)
from app.extensions import bcrypt, db, mail
from app.models import AccountVerificationToken, Role, User


def _user(
    *,
    email: str,
    role: Role,
    verified: bool = True,
    approved: bool = True,
    active: bool = True,
) -> User:
    now = datetime.now(UTC)
    user = User(
        full_name="Test User",
        email=email,
        password_hash=bcrypt.generate_password_hash(
            "InstitutionPassword!"
        ).decode("utf-8"),
        role=role,
        is_active=active,
        email_verified_at=now if verified else None,
        approved_at=now if approved else None,
    )
    db.session.add(user)
    db.session.commit()
    return user


def _register(client, role: str, email: str):
    with mail.record_messages() as outbox:
        response = client.post(
            f"/account/register/{role}",
            data={
                "full_name": "Amina Bello",
                "email": email,
                "password": "InstitutionPassword!",
                "confirm_password": "InstitutionPassword!",
            },
        )
        messages = list(outbox)
    return response, messages


def _verification_path(message) -> str:
    match = re.search(r"https?://[^\s<]+", message.body)
    assert match is not None
    return urlsplit(match.group(0)).path


def _login(client, email: str, password: str = "InstitutionPassword!"):
    return client.post(
        "/account/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )


def _admin_login(client):
    return client.post(
        "/admin/login",
        data={
            "email": "admin@mau.edu.ng",
            "password": "Phase3TestPassword!",
        },
    )


def test_registration_pages_enforce_exact_role_domains(client):
    lecturer_page = client.get("/account/register/lecturer")
    student_page = client.get("/account/register/student")
    wrong_lecturer, _ = _register(
        client,
        "lecturer",
        "lecturer@student.mau.edu.ng",
    )
    wrong_student, _ = _register(
        client,
        "student",
        "student@mau.edu.ng",
    )

    assert lecturer_page.status_code == 200
    assert b"Admin approval" in lecturer_page.data
    assert student_page.status_code == 200
    assert b"@student.mau.edu.ng" in student_page.data
    assert b"ending in @mau.edu.ng" in wrong_lecturer.data
    assert b"ending in @student.mau.edu.ng" in wrong_student.data


def test_student_registration_verification_and_login(client):
    response, messages = _register(
        client,
        "student",
        "AMINA@STUDENT.MAU.EDU.NG",
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/account/check-email")
    assert len(messages) == 1
    assert messages[0].recipients == ["amina@student.mau.edu.ng"]

    user = db.session.scalar(select(User).where(User.role == Role.STUDENT))
    token = db.session.scalar(select(AccountVerificationToken))
    path = _verification_path(messages[0])
    raw_token = path.rsplit("/", 1)[-1]

    assert user is not None
    assert user.full_name == "Amina Bello"
    assert user.is_email_verified is False
    assert user.is_approved is True
    assert user.can_access_portal is False
    assert token is not None
    assert token.token_hash == token_digest(raw_token)
    assert raw_token not in token.token_hash
    assert token.is_used is False
    assert token.is_invalidated is False
    assert "AccountVerificationToken" in repr(token)

    check_email = client.get("/account/check-email")
    assert b"amina@student.mau.edu.ng" in check_email.data

    verified = client.get(path, follow_redirects=True)
    assert b"Email verified" in verified.data
    assert user.is_email_verified is True
    assert user.approved_at is not None
    assert token.is_used is True

    login = _login(client, user.email)
    assert login.status_code == 302
    assert login.headers["Location"].endswith("/student/")
    dashboard = client.get("/student/")
    assert b"Student dashboard" in dashboard.data
    assert b"No examination attempts yet" in dashboard.data


def test_lecturer_requires_verification_then_admin_approval(client, admin):
    response, messages = _register(
        client,
        "lecturer",
        "lecturer@mau.edu.ng",
    )
    assert response.status_code == 302

    user = db.session.scalar(select(User).where(User.role == Role.LECTURER))
    assert user is not None

    unverified_login = _login(client, user.email)
    assert unverified_login.status_code == 200
    assert b"Verify your institutional email" in unverified_login.data

    client.get(_verification_path(messages[0]))
    assert user.is_email_verified is True
    assert user.is_approved is False

    pending_login = _login(client, user.email)
    assert pending_login.status_code == 200
    assert b"awaiting Admin approval" in pending_login.data

    _admin_login(client)
    accounts_page = client.get("/admin/accounts")
    assert accounts_page.status_code == 200
    assert b"Approval pending" in accounts_page.data

    approved = client.post(f"/admin/accounts/{user.id}/approve")
    assert approved.status_code == 302
    assert user.approved_at is not None

    client.post("/admin/logout")
    login = _login(client, user.email)
    assert login.headers["Location"].endswith("/lecturer/")
    dashboard = client.get("/lecturer/")
    assert b"Lecturer dashboard" in dashboard.data
    assert b"No examinations yet" in dashboard.data


def test_registration_rejects_duplicate_and_rolls_back_mail_failure(
    client,
    monkeypatch,
):
    _user(email="duplicate@student.mau.edu.ng", role=Role.STUDENT)

    duplicate, messages = _register(
        client,
        "student",
        "duplicate@student.mau.edu.ng",
    )
    assert duplicate.status_code == 200
    assert b"account already exists" in duplicate.data
    assert messages == []

    monkeypatch.setattr(
        "app.accounts.routes.send_account_verification_email",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("SMTP unavailable")),
    )
    failed, _ = _register(
        client,
        "student",
        "failure@student.mau.edu.ng",
    )
    assert failed.status_code == 200
    assert b"account could not be created" in failed.data
    assert db.session.scalar(
        select(User).where(User.email == "failure@student.mau.edu.ng")
    ) is None


def test_verification_service_invalidates_older_and_rejects_bad_states(app):
    user = _user(
        email="verify@student.mau.edu.ng",
        role=Role.STUDENT,
        verified=False,
        approved=False,
    )
    first_raw, first = create_account_verification(user)
    second_raw, second = create_account_verification(user)
    db.session.commit()

    assert first.invalidated_at is not None
    assert resolve_account_verification(first_raw) is None
    assert resolve_account_verification(second_raw) is second
    assert resolve_account_verification("unknown") is None

    second.used_at = datetime.now(UTC)
    db.session.commit()
    assert resolve_account_verification(second_raw) is None

    expired_raw, expired = create_account_verification(user)
    expired.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.session.commit()
    assert resolve_account_verification(expired_raw) is None
    assert aware_utc(expired.expires_at).tzinfo is UTC
    aware_now = datetime.now(UTC)
    assert aware_utc(aware_now) == aware_now


def test_invalid_verification_link_and_email_delivery_service(
    app,
    client,
    monkeypatch,
):
    invalid = client.get("/account/verify/not-valid", follow_redirects=True)
    assert b"invalid or has expired" in invalid.data

    user = _user(
        email="delivery@student.mau.edu.ng",
        role=Role.STUDENT,
        verified=False,
        approved=False,
    )
    sent = []
    app.config["MAIL_SUPPRESS_SEND"] = False
    monkeypatch.setattr(mail, "send", sent.append)
    with app.test_request_context():
        send_account_verification_email(user, "raw-token")
    assert len(sent) == 1
    assert sent[0].recipients == [user.email]
    assert "raw-token" in sent[0].body


def test_account_login_rejects_invalid_inactive_and_wrong_portal(client, admin):
    student = _user(email="student@student.mau.edu.ng", role=Role.STUDENT)
    inactive = _user(
        email="inactive@student.mau.edu.ng",
        role=Role.STUDENT,
        active=False,
    )

    wrong = _login(client, student.email, "WrongPassword!")
    unknown = _login(client, "unknown@student.mau.edu.ng")
    inactive_response = _login(client, inactive.email)
    admin_response = _login(client, admin.email, "Phase3TestPassword!")

    assert b"Invalid email address or password" in wrong.data
    assert b"Invalid email address or password" in unknown.data
    assert b"Invalid email address or password" in inactive_response.data
    assert admin_response.status_code == 302
    assert admin_response.headers["Location"].endswith("/admin/login")


def test_account_login_accepts_only_local_next_and_logout_is_post_only(client):
    student = _user(email="next@student.mau.edu.ng", role=Role.STUDENT)

    local = client.post(
        "/account/login?next=/student/%3Ftab=results",
        data={"email": student.email, "password": "InstitutionPassword!"},
    )
    assert local.headers["Location"].endswith("/student/?tab=results")

    assert client.get("/account/logout").status_code == 405
    client.post("/account/logout")

    external = client.post(
        "/account/login?next=https://attacker.example/steal",
        data={"email": student.email, "password": "InstitutionPassword!"},
    )
    assert external.headers["Location"].endswith("/student/")

    client.post("/account/logout")
    anonymous_logout = client.post("/account/logout", follow_redirects=True)
    assert b"You have been logged out" in anonymous_logout.data


def test_authenticated_users_redirect_from_account_entry_pages(client):
    lecturer = _user(email="redirect@mau.edu.ng", role=Role.LECTURER)
    _login(client, lecturer.email)

    for path in (
        "/account/login",
        "/account/register/lecturer",
        "/account/register/student",
    ):
        response = client.get(path)
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/lecturer/")


def test_admin_manages_non_admin_accounts_only(client, admin):
    verified = _user(
        email="verified@mau.edu.ng",
        role=Role.LECTURER,
        approved=False,
    )
    unverified = _user(
        email="unverified@mau.edu.ng",
        role=Role.LECTURER,
        verified=False,
        approved=False,
    )
    student = _user(
        email="managed@student.mau.edu.ng",
        role=Role.STUDENT,
    )
    _admin_login(client)

    assert client.post(f"/admin/accounts/{verified.id}/approve").status_code == 302
    assert client.post(f"/admin/accounts/{unverified.id}/approve").status_code == 400
    assert client.post(f"/admin/accounts/{student.id}/approve").status_code == 400
    assert client.post(f"/admin/accounts/{admin.id}/approve").status_code == 404
    assert client.post("/admin/accounts/99999/toggle-active").status_code == 404

    suspended = client.post(f"/admin/accounts/{student.id}/toggle-active")
    assert suspended.status_code == 302
    assert student.is_active is False
    client.post(f"/admin/accounts/{student.id}/toggle-active")
    assert student.is_active is True


def test_role_guards_prevent_cross_portal_access(client, admin):
    student = _user(email="guard@student.mau.edu.ng", role=Role.STUDENT)

    anonymous = client.get("/student/")
    assert anonymous.status_code == 302
    assert "/account/login" in anonymous.headers["Location"]

    _login(client, student.email)
    assert client.get("/lecturer/").status_code == 403
    assert client.get("/admin/").status_code == 403

    client.post("/account/logout")
    _admin_login(client)
    assert client.get("/student/").status_code == 403


def test_role_guard_rejects_authenticated_unverified_account(client):
    student = _user(
        email="unverified@student.mau.edu.ng",
        role=Role.STUDENT,
        verified=False,
        approved=False,
    )
    with client.session_transaction() as account_session:
        account_session["_user_id"] = str(student.id)
        account_session["_fresh"] = True

    assert client.get("/student/").status_code == 403


def test_account_form_validation_and_empty_check_email(client):
    invalid = client.post(
        "/account/register/student",
        data={
            "full_name": "A",
            "email": "bad",
            "password": "short",
            "confirm_password": "different",
        },
    )
    assert b"Invalid email address" in invalid.data
    assert b"Passwords must match" in invalid.data

    login = client.post(
        "/account/login",
        data={"email": "bad", "password": ""},
    )
    assert b"Invalid email address" in login.data
    assert b"This field is required" in login.data

    check_email = client.get("/account/check-email")
    assert check_email.status_code == 200
    assert b"Check your institutional email" in check_email.data

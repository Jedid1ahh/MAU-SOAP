"""Tests for the Phase 3 Admin password-reset workflow."""

import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from sqlalchemy import func, select

from app.admin.services import _aware_utc, token_digest
from app.extensions import bcrypt, db, mail
from app.models import PasswordResetToken


def _request_reset(client, email="admin@mau.edu.ng"):
    with mail.record_messages() as outbox:
        response = client.post(
            "/admin/password-reset",
            data={"email": email},
            follow_redirects=True,
        )
        messages = list(outbox)
    return response, messages


def _token_path(message):
    match = re.search(
        r"https?://[^\s]+(/admin/password-reset/[^\s]+)",
        message.body,
    )
    assert match is not None
    return urlsplit(match.group(0)).path


def test_password_reset_request_page_and_validation(client):
    page = client.get("/admin/password-reset")
    invalid = client.post(
        "/admin/password-reset",
        data={"email": "bad-address"},
    )

    assert page.status_code == 200
    assert b"Reset your password" in page.data
    assert invalid.status_code == 200
    assert b"Invalid email address" in invalid.data


def test_known_admin_receives_hashed_single_use_reset_link(client, admin):
    response, messages = _request_reset(client)

    assert response.status_code == 200
    assert b"If that address belongs to the Admin account" in response.data
    assert len(messages) == 1
    assert messages[0].recipients == [admin.email]

    reset_token = db.session.scalar(select(PasswordResetToken))
    raw_token = _token_path(messages[0]).rsplit("/", 1)[-1]

    assert reset_token is not None
    assert reset_token.token_hash == token_digest(raw_token)
    assert raw_token not in reset_token.token_hash
    assert reset_token.expires_at > datetime.now(UTC).replace(tzinfo=None)


def test_reset_request_does_not_disclose_unknown_or_inactive_accounts(
    client,
    admin,
):
    known_response, _ = _request_reset(client)
    db.session.query(PasswordResetToken).delete()
    db.session.commit()

    unknown_response, unknown_messages = _request_reset(
        client,
        email="nobody@mau.edu.ng",
    )

    admin.is_active = False
    db.session.commit()
    inactive_response, inactive_messages = _request_reset(client)

    expected = b"If that address belongs to the Admin account"

    assert expected in known_response.data
    assert expected in unknown_response.data
    assert expected in inactive_response.data
    assert unknown_messages == []
    assert inactive_messages == []
    assert db.session.scalar(select(func.count(PasswordResetToken.id))) == 0


def test_requesting_a_new_link_locks_the_previous_link(client, admin):
    _, first_messages = _request_reset(client)
    first_path = _token_path(first_messages[0])

    _, second_messages = _request_reset(client)
    second_path = _token_path(second_messages[0])

    tokens = db.session.scalars(
        select(PasswordResetToken).order_by(PasswordResetToken.id)
    ).all()

    assert len(tokens) == 2
    assert tokens[0].is_locked is True
    assert tokens[1].is_locked is False
    assert client.get(first_path).status_code == 302
    assert client.get(second_path).status_code == 200


def test_valid_link_resets_password_logs_out_admin_and_invalidates_siblings(
    client,
    admin,
):
    _, messages = _request_reset(client)
    reset_path = _token_path(messages[0])
    primary_token = db.session.scalar(select(PasswordResetToken))

    sibling = PasswordResetToken(
        user=admin,
        token_hash="f" * 64,
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    db.session.add(sibling)
    db.session.commit()

    client.post(
        "/admin/login",
        data={
            "email": "admin@mau.edu.ng",
            "password": "Phase3TestPassword!",
        },
    )

    response = client.post(
        reset_path,
        data={
            "password": "ACompletelyNewPassword!",
            "confirm_password": "ACompletelyNewPassword!",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Your password has been reset" in response.data
    assert bcrypt.check_password_hash(
        admin.password_hash,
        "ACompletelyNewPassword!",
    )
    assert primary_token.is_used is True
    assert sibling.is_locked is True
    assert client.get("/admin/").status_code == 302
    assert client.get(reset_path).status_code == 302

    relogin = client.post(
        "/admin/login",
        data={
            "email": admin.email,
            "password": "ACompletelyNewPassword!",
        },
    )

    assert relogin.status_code == 302
    assert relogin.headers["Location"].endswith("/admin/")


def test_expired_locked_used_and_unknown_tokens_are_rejected(client, admin):
    now = datetime.now(UTC)

    tokens = [
        PasswordResetToken(
            user=admin,
            token_hash=token_digest("expired"),
            expires_at=now - timedelta(seconds=1),
        ),
        PasswordResetToken(
            user=admin,
            token_hash=token_digest("locked"),
            expires_at=now + timedelta(minutes=5),
            locked_at=now,
        ),
        PasswordResetToken(
            user=admin,
            token_hash=token_digest("used"),
            expires_at=now + timedelta(minutes=5),
            used_at=now,
        ),
    ]

    db.session.add_all(tokens)
    db.session.commit()

    for raw_token in ("expired", "locked", "used", "unknown"):
        response = client.get(f"/admin/password-reset/{raw_token}")

        assert response.status_code == 302
        assert response.headers["Location"].endswith("/admin/password-reset")


def test_five_invalid_password_submissions_lock_reset_link(client, admin):
    _, messages = _request_reset(client)
    reset_path = _token_path(messages[0])
    reset_token = db.session.scalar(select(PasswordResetToken))

    for attempt in range(1, 6):
        response = client.post(
            reset_path,
            data={
                "password": "ValidLengthPassword!",
                "confirm_password": "DoesNotMatchPassword!",
            },
        )

        if attempt < 5:
            assert response.status_code == 200
            assert b"Passwords must match" in response.data
        else:
            assert response.status_code == 302

    assert reset_token.attempts == 5
    assert reset_token.is_locked is True
    assert client.get(reset_path).status_code == 302


def test_anonymous_admin_can_complete_password_reset(client, admin):
    _, messages = _request_reset(client)
    reset_path = _token_path(messages[0])

    response = client.post(
        reset_path,
        data={
            "password": "AnotherSecurePassword!",
            "confirm_password": "AnotherSecurePassword!",
        },
    )

    assert response.status_code == 302
    assert bcrypt.check_password_hash(
        admin.password_hash,
        "AnotherSecurePassword!",
    )


def test_timezone_normalizer_preserves_aware_time():
    aware = datetime.now(UTC)

    assert _aware_utc(aware) == aware
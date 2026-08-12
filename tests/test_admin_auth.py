"""Tests for Phase 3 Admin login, authorization, and logout."""
import re

from flask_login import login_user

from app import create_app
from app.extensions import db


def _login(client, password="Phase3TestPassword!", path="/admin/login"):
    return client.post(
        path,
        data={"email": "ADMIN@MAU.EDU.NG", "password": password},
        follow_redirects=False,
    )


def test_login_page_is_available_without_registration(client):
    response = client.get("/admin/login")

    assert response.status_code == 200
    assert b"Welcome back" in response.data
    assert b"Forgot your password?" in response.data

    for path in ("/admin/register", "/admin/signup"):
        assert client.get(path).status_code == 404
        assert client.post(path).status_code == 404


def test_valid_admin_login_reaches_protected_dashboard(client, admin):
    response = _login(client)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/")

    dashboard = client.get("/admin/")
    assert dashboard.status_code == 200
    assert b"Authenticated" in dashboard.data
    assert admin.email.encode() in dashboard.data


def test_authenticated_admin_is_redirected_away_from_login(client, admin):
    _login(client)

    response = client.get("/admin/login")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/")


def test_login_rejects_wrong_credentials_and_inactive_admin(client, admin):
    wrong_password = _login(client, password="DefinitelyWrong!")

    assert wrong_password.status_code == 200
    assert b"Invalid email address or password" in wrong_password.data

    admin.is_active = False
    db.session.commit()
    inactive = _login(client)

    assert inactive.status_code == 200
    assert b"Invalid email address or password" in inactive.data

    unknown = client.post(
        "/admin/login",
        data={"email": "unknown@mau.edu.ng", "password": "SomePassword123!"},
    )
    assert unknown.status_code == 200
    assert b"Invalid email address or password" in unknown.data


def test_login_form_validates_email_and_password(client):
    response = client.post(
        "/admin/login",
        data={"email": "not-an-email", "password": ""},
    )

    assert response.status_code == 200
    assert b"Invalid email address" in response.data
    assert b"This field is required" in response.data


def test_login_accepts_only_safe_local_next_urls(client, admin):
    local = _login(client, path="/admin/login?next=/admin/%3Ftab=security")
    assert local.headers["Location"].endswith("/admin/?tab=security")

    client.post("/admin/logout")
    external = _login(
        client,
        path="/admin/login?next=https://attacker.example/steal",
    )
    assert external.headers["Location"].endswith("/admin/")

    client.post("/admin/logout")
    relative = _login(client, path="/admin/login?next=admin/profile")
    assert relative.headers["Location"].endswith("/admin/")


def test_logout_ends_session_and_is_post_only(client, admin):
    _login(client)

    assert client.get("/admin/logout").status_code == 405
    response = client.post("/admin/logout", follow_redirects=True)

    assert response.status_code == 200
    assert b"You have been logged out" in response.data
    assert client.get("/admin/").status_code == 302


def test_malformed_session_user_id_is_treated_as_anonymous(app, client):
    with client.session_transaction() as session:
        session["_user_id"] = "not-an-integer"
        session["_fresh"] = True

    assert client.get("/admin/").status_code == 302


def test_valid_session_user_id_restores_admin(client, admin):
    with client.session_transaction() as session:
        session["_user_id"] = str(admin.id)
        session["_fresh"] = True

    assert client.get("/admin/").status_code == 200


def test_login_manager_rejects_inactive_user_session(app, client, admin):
    admin.is_active = False
    db.session.commit()

    with app.test_request_context():
        assert login_user(admin) is False


def test_csrf_protection_rejects_unsigned_login_post():
    application = create_app("testing", {"WTF_CSRF_ENABLED": True})
    csrf_client = application.test_client()

    response = csrf_client.post(
        "/admin/login",
        data={"email": "admin@mau.edu.ng", "password": "AnyPassword123!"},
    )

    assert response.status_code == 400

def test_valid_csrf_token_allows_login_form_processing(app, client, admin):
    app.config["WTF_CSRF_ENABLED"] = True
    page = client.get("/admin/login")
    match = re.search(
        rb'name="csrf_token"[^>]*value="([^"]+)"',
        page.data,
    )

    assert match is not None

    response = client.post(
        "/admin/login",
        data={
            "csrf_token": match.group(1).decode("utf-8"),
            "email": admin.email,
            "password": "DefinitelyWrong!",
        },
    )

    assert response.status_code == 200
    assert b"Invalid email address or password" in response.data
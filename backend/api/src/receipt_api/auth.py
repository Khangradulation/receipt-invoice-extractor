"""Firebase Authentication: verify the ID token sent as ``Authorization: Bearer <token>``.

The user's identity comes only from a verified token, never from request bodies or paths.
With ``FIREBASE_AUTH_EMULATOR_HOST`` set, firebase-admin verifies emulator tokens instead.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Annotated, Protocol

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from receipt_shared.config import Settings

logger = logging.getLogger("receipt.auth")

_bearer = HTTPBearer(auto_error=False, description="Firebase ID token")


@dataclass(frozen=True)
class CurrentUser:
    uid: str
    email: str | None = None


class InvalidTokenError(Exception):
    pass


class TokenVerifier(Protocol):
    def verify(self, token: str) -> CurrentUser: ...


class FirebaseTokenVerifier:
    """Verifies Firebase ID tokens (signature, expiry, audience = project, issuer)."""

    _APP_NAME = "receipt-api"

    def __init__(self, settings: Settings) -> None:
        project_id = settings.effective_firebase_project_id
        if not project_id:
            raise RuntimeError("FIREBASE_PROJECT_ID / GCP_PROJECT_ID is not set")
        self._project_id = project_id
        self._lock = threading.Lock()
        self._app: object | None = None

    def _get_app(self) -> object:
        import firebase_admin

        with self._lock:
            if self._app is None:
                try:
                    self._app = firebase_admin.get_app(self._APP_NAME)
                except ValueError:
                    self._app = firebase_admin.initialize_app(
                        options={"projectId": self._project_id}, name=self._APP_NAME
                    )
            return self._app

    def verify(self, token: str) -> CurrentUser:
        from firebase_admin import auth

        try:
            claims = auth.verify_id_token(token, app=self._get_app(), clock_skew_seconds=10)
        except (ValueError, auth.InvalidIdTokenError, auth.CertificateFetchError) as exc:
            # ExpiredIdTokenError / RevokedIdTokenError subclass InvalidIdTokenError.
            raise InvalidTokenError(type(exc).__name__) from exc
        uid = claims.get("uid") or claims.get("sub")
        if not isinstance(uid, str) or not uid:
            raise InvalidTokenError("token has no subject")
        email = claims.get("email")
        return CurrentUser(uid=uid, email=email if isinstance(email, str) else None)


def get_token_verifier(request: Request) -> TokenVerifier:
    verifier: TokenVerifier | None = getattr(request.app.state, "token_verifier", None)
    if verifier is None:
        verifier = FirebaseTokenVerifier(request.app.state.settings)
        request.app.state.token_verifier = verifier
    return verifier


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    verifier: Annotated[TokenVerifier, Depends(get_token_verifier)],
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise _unauthorized("Sign in required.")
    try:
        return verifier.verify(credentials.credentials)
    except InvalidTokenError as exc:
        logger.info("rejected id token", extra={"reason": str(exc)})
        raise _unauthorized(
            "Your session is invalid or has expired. Please sign in again."
        ) from exc


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]

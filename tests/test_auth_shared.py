import time
from unittest import mock

import pytest

from routes.auth_shared import (
    _build_oauth_flow_token,
    _generate_signed_state,
    _verify_oauth_flow_token,
    _verify_signed_state,
)


def test_generate_and_verify_signed_state():
    state = _generate_signed_state()
    assert state is not None
    assert isinstance(state, str)
    assert len(state.split(":")) == 3
    
    assert _verify_signed_state(state) is True


def test_verify_signed_state_tampered():
    state = _generate_signed_state()
    parts = state.split(":")
    
    # Tamper with the nonce
    tampered_nonce = parts[0] + "a"
    tampered_state1 = f"{tampered_nonce}:{parts[1]}:{parts[2]}"
    assert _verify_signed_state(tampered_state1) is False
    
    # Tamper with the signature
    tampered_sig = parts[2][:-1] + "a" if parts[2][-1] != "a" else parts[2][:-1] + "b"
    tampered_state2 = f"{parts[0]}:{parts[1]}:{tampered_sig}"
    assert _verify_signed_state(tampered_state2) is False


def test_verify_signed_state_expired():
    state = _generate_signed_state()
    parts = state.split(":")
    
    # Simulate a state that is 601 seconds old (expiry is 600)
    old_time = str(int(time.time()) - 601)
    
    # We need to compute the correct signature for this old time to bypass the signature check
    # and only fail on the expiry check. However, since the secret is internal to auth_shared,
    # we can just mock time.time() during verification.
    
    with mock.patch("time.time", return_value=time.time() + 601):
        assert _verify_signed_state(state) is False


def test_oauth_flow_token_creation_and_verification():
    token = _build_oauth_flow_token(
        kind="registration",
        provider="google",
        provider_key="12345",
        email="test@example.com",
        username="tester",
        secret_hash="hash123",
    )
    
    assert token is not None
    assert "." in token
    
    payload = _verify_oauth_flow_token(token, "registration")
    assert payload is not None
    assert payload["kind"] == "registration"
    assert payload["provider"] == "google"
    assert payload["provider_key"] == "12345"
    assert payload["email"] == "test@example.com"
    assert payload["username"] == "tester"
    assert payload["secret_hash"] == "hash123"


def test_oauth_flow_token_wrong_kind():
    token = _build_oauth_flow_token(
        kind="registration",
        provider="google",
        provider_key="12345",
        email="test@example.com",
        username=None,
        secret_hash=None,
    )
    
    # Try to verify a registration token as a link token
    payload = _verify_oauth_flow_token(token, "link")
    assert payload is None


def test_oauth_flow_token_expired():
    token = _build_oauth_flow_token(
        kind="link",
        provider="discord",
        provider_key="9876",
        email="discord@example.com",
        username=None,
        secret_hash=None,
    )
    
    # Fast forward time to beyond expiry (1800 seconds)
    with mock.patch("time.time", return_value=time.time() + 1801):
        payload = _verify_oauth_flow_token(token, "link")
        assert payload is None


def test_oauth_flow_token_tampered():
    token = _build_oauth_flow_token(
        kind="link",
        provider="discord",
        provider_key="9876",
        email="discord@example.com",
        username=None,
        secret_hash=None,
    )
    
    payload_part, signature = token.split(".")
    
    # Tamper with the signature
    tampered_sig = signature[:-1] + "a" if signature[-1] != "a" else signature[:-1] + "b"
    tampered_token = f"{payload_part}.{tampered_sig}"
    
    assert _verify_oauth_flow_token(tampered_token, "link") is None

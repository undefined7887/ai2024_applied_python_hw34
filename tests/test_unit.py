import string
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from jose import jwt

from app.main import get_user_id
from app.utils import generate_short_code


# Test cases for the generate_short_code function

def test_generate_short_code_length():
    """Test that generate_short_code() returns a string of the correct length"""
    assert len(generate_short_code(k=5)) == 5
    assert len(generate_short_code(k=10)) == 10
    assert len(generate_short_code(k=15)) == 15


def test_generate_short_code_characters():
    """Test that generate_short_code() only contains valid characters"""
    valid_chars = set(string.ascii_letters + string.digits)
    short_code = generate_short_code(k=100)

    assert all(char in valid_chars for char in short_code)


def test_generate_short_code_randomness():
    """Test that generate_short_code() produces different outputs"""
    codes = {generate_short_code(k=10) for _ in range(100)}

    # Ensure that we have unique codes
    assert len(codes) == 100


# Test cases for get_user_id function

JWT_SECRET_KEY = "test_secret"
JWT_ALGORITHM = "HS256"


def test_get_user_id_valid_token():
    """Test get_user_id() with a valid token"""
    token = jwt.encode({"sub": "user123"}, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    request = MagicMock()
    request.headers = {"Authorization": f"Bearer {token}"}

    user_id = get_user_id(request, jwt_secret_key=JWT_SECRET_KEY, jwt_algorithm=JWT_ALGORITHM)

    assert user_id == "user123"


def test_get_user_id_missing_header():
    """Test get_user_id() when Authorization header is missing"""
    request = MagicMock()
    request.headers = {}

    user_id = get_user_id(request)

    assert user_id is None


def test_get_user_id_invalid_format():
    """Test get_user_id() when Authorization header is incorrectly formatted"""
    request = MagicMock()
    request.headers = {"Authorization": "InvalidFormatToken"}

    user_id = get_user_id(request)

    assert user_id is None


def test_get_user_id_invalid_token():
    """Test get_user_id() when token is invalid"""
    request = MagicMock()
    request.headers = {"Authorization": "Bearer ababab"}

    with pytest.raises(HTTPException) as exc_info:
        get_user_id(request)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Access token malformed"

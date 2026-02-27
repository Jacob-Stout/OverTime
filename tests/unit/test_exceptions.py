"""Tests for exception classes."""

from overtime.utils.exceptions import ConfigurationError, OvertimeError


def test_overtime_error_with_details():
    """Test exception with details."""
    error = OvertimeError("Main message", details="Additional details")
    error_str = str(error)

    assert "Main message" in error_str
    assert "Additional details" in error_str


def test_overtime_error_without_details():
    """Test exception without details."""
    error = OvertimeError("Main message")
    error_str = str(error)

    assert error_str == "Main message"
    assert "Details:" not in error_str


def test_configuration_error():
    """Test ConfigurationError inherits from OvertimeError."""
    error = ConfigurationError("Config invalid")

    assert isinstance(error, OvertimeError)
    assert str(error) == "Config invalid"


def test_configuration_error_with_details():
    """Test ConfigurationError with details."""
    error = ConfigurationError("Config invalid", details="Missing field: name")

    assert isinstance(error, OvertimeError)
    assert "Config invalid" in str(error)
    assert "Missing field: name" in str(error)

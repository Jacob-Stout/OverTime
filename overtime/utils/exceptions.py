"""Custom exception classes for OverTime."""


class OvertimeError(Exception):
    """Base exception for all OverTime errors."""

    def __init__(self, message: str, details: str = None):
        self.message = message
        self.details = details
        super().__init__(self.message)

    def __str__(self):
        if self.details:
            return f"{self.message}\nDetails: {self.details}"
        return self.message


class ConfigurationError(OvertimeError):
    """Configuration file is invalid or missing required fields."""
    pass


class TerraformError(OvertimeError):
    """Terraform operation failed."""
    pass


class SecretError(OvertimeError):
    """Secret management operation failed."""
    pass



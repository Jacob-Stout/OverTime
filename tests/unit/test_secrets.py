"""Tests for secret management."""

import pytest
from unittest.mock import patch, MagicMock

from overtime.secrets.backends.envvars import EnvVarsBackend
from overtime.secrets.backends.dotenv import DotEnvBackend
from overtime.secrets.backends.onepassword import OnePasswordBackend
from overtime.secrets.manager import SecretManager
from overtime.utils.exceptions import SecretError


# ---------------------------------------------------------------------------
# EnvVarsBackend
# ---------------------------------------------------------------------------

class TestEnvVarsBackend:
    """Tests for environment variables backend."""

    def test_get_secret_from_env(self, monkeypatch):
        """Test reading secret from environment."""
        monkeypatch.setenv('OVERTIME_SECRET_TEST_KEY', 'test_value')

        backend = EnvVarsBackend()
        assert backend.get_secret('test_key') == 'test_value'

    def test_get_secret_not_found(self):
        """Test getting non-existent secret returns None."""
        backend = EnvVarsBackend()
        assert backend.get_secret('nonexistent_key_xyz') is None

    def test_set_secret_raises(self):
        """Test that set raises NotImplementedError."""
        backend = EnvVarsBackend()
        with pytest.raises(NotImplementedError):
            backend.set_secret('key', 'value')

    def test_delete_secret_raises(self):
        """Test that delete raises NotImplementedError."""
        backend = EnvVarsBackend()
        with pytest.raises(NotImplementedError):
            backend.delete_secret('key')

    def test_list_secrets(self, monkeypatch):
        """Test listing only OVERTIME_SECRET_ prefixed vars."""
        monkeypatch.setenv('OVERTIME_SECRET_KEY1', 'value1')
        monkeypatch.setenv('OVERTIME_SECRET_KEY2', 'value2')
        monkeypatch.setenv('OTHER_VAR', 'value')

        backend = EnvVarsBackend()
        secrets = backend.list_secrets()

        assert 'key1' in secrets
        assert 'key2' in secrets
        assert 'other_var' not in secrets


# ---------------------------------------------------------------------------
# DotEnvBackend
# ---------------------------------------------------------------------------

class TestDotEnvBackend:
    """Tests for .env file backend."""

    def test_set_and_get(self, tmp_path):
        """Test storing and retrieving a secret."""
        backend = DotEnvBackend(str(tmp_path / '.env'))
        backend.set_secret('db_password', 'secret123')

        assert backend.get_secret('db_password') == 'secret123'

    def test_get_nonexistent(self, tmp_path):
        """Test getting a key that doesn't exist returns None."""
        backend = DotEnvBackend(str(tmp_path / '.env'))
        assert backend.get_secret('nope') is None

    def test_get_from_missing_file(self, tmp_path):
        """Test getting from a nonexistent .env file returns None (no crash)."""
        backend = DotEnvBackend(str(tmp_path / 'missing.env'))
        assert backend.get_secret('key') is None

    def test_list_secrets(self, tmp_path):
        """Test listing all keys."""
        backend = DotEnvBackend(str(tmp_path / '.env'))
        backend.set_secret('alpha', '1')
        backend.set_secret('beta', '2')

        assert backend.list_secrets() == ['alpha', 'beta']

    def test_list_empty(self, tmp_path):
        """Test listing when .env doesn't exist."""
        backend = DotEnvBackend(str(tmp_path / '.env'))
        assert backend.list_secrets() == []

    def test_delete_secret(self, tmp_path):
        """Test deleting a secret removes it."""
        backend = DotEnvBackend(str(tmp_path / '.env'))
        backend.set_secret('temp', 'value')
        backend.delete_secret('temp')

        assert backend.get_secret('temp') is None

    def test_delete_nonexistent_no_crash(self, tmp_path):
        """Test deleting a key that doesn't exist doesn't crash."""
        backend = DotEnvBackend(str(tmp_path / '.env'))
        backend.set_secret('other', 'value')
        backend.delete_secret('nonexistent')  # should just warn, not raise

    def test_file_created_with_secure_permissions(self, tmp_path):
        """Test that .env is created with 0600 permissions."""
        env_path = tmp_path / '.env'
        backend = DotEnvBackend(str(env_path))
        backend.set_secret('key', 'value')

        assert env_path.exists()
        import stat
        mode = env_path.stat().st_mode & 0o777
        assert mode == 0o600

    def test_empty_value_returns_none(self, tmp_path):
        """An empty value (KEY=) in .env is treated as missing."""
        env_path = tmp_path / '.env'
        env_path.write_text("ANSIBLE_PASSWORD=\n")
        backend = DotEnvBackend(str(env_path))
        assert backend.get_secret('ANSIBLE_PASSWORD') is None

    def test_persistence_across_instances(self, tmp_path):
        """Test that secrets written by one instance are readable by another."""
        path = str(tmp_path / '.env')

        b1 = DotEnvBackend(path)
        b1.set_secret('persistent_key', 'persistent_value')

        b2 = DotEnvBackend(path)
        assert b2.get_secret('persistent_key') == 'persistent_value'


# ---------------------------------------------------------------------------
# OnePasswordBackend
# ---------------------------------------------------------------------------

class TestOnePasswordBackend:
    """Tests for 1Password backend (mocked — does not require op CLI)."""

    @patch('overtime.secrets.backends.onepassword.shutil.which', side_effect=lambda name: 'op' if name == 'op' else None)
    @patch('overtime.secrets.backends.onepassword.subprocess.run')
    def test_init_verifies_op(self, mock_run, mock_which):
        """Test that __init__ calls op --version."""
        mock_run.return_value = MagicMock(returncode=0)

        OnePasswordBackend()

        mock_run.assert_called_once_with(
            ['op', '--version'], capture_output=True, check=True,
            timeout=OnePasswordBackend.OP_VERIFY_TIMEOUT
        )

    @patch('overtime.secrets.backends.onepassword.shutil.which', return_value=None)
    def test_init_raises_when_op_missing(self, mock_which):
        """Test that missing op CLI raises SecretError."""
        with pytest.raises(SecretError, match="not found in PATH"):
            OnePasswordBackend()

    @patch('overtime.secrets.backends.onepassword.subprocess.run')
    def test_get_secret(self, mock_run):
        """Test successful secret retrieval."""
        # First call: op --version (init check)
        # Second call: op read
        mock_run.side_effect = [
            MagicMock(returncode=0),                              # --version
            MagicMock(stdout='my-secret-value\n', returncode=0)   # read
        ]

        backend = OnePasswordBackend()
        value = backend.get_secret('op://Dev/TestItem/password')

        assert value == 'my-secret-value'

    @patch('overtime.secrets.backends.onepassword.subprocess.run')
    def test_get_secret_not_found(self, mock_run):
        """Test that op read failure raises SecretError."""
        import subprocess

        mock_run.side_effect = [
            MagicMock(returncode=0),  # --version
            subprocess.CalledProcessError(1, 'op', stderr='item not found')  # read
        ]

        backend = OnePasswordBackend()
        with pytest.raises(SecretError, match="failed to read"):
            backend.get_secret('op://Dev/Missing/password')

    @patch('overtime.secrets.backends.onepassword.subprocess.run')
    def test_set_raises(self, mock_run):
        """Test that set raises NotImplementedError."""
        mock_run.return_value = MagicMock(returncode=0)

        backend = OnePasswordBackend()
        with pytest.raises(NotImplementedError):
            backend.set_secret('op://Dev/X/y', 'value')

    @patch('overtime.secrets.backends.onepassword.subprocess.run')
    def test_delete_raises(self, mock_run):
        """Test that delete raises NotImplementedError."""
        mock_run.return_value = MagicMock(returncode=0)

        backend = OnePasswordBackend()
        with pytest.raises(NotImplementedError):
            backend.delete_secret('op://Dev/X/y')


# ---------------------------------------------------------------------------
# SecretManager (routing + fallback)
# ---------------------------------------------------------------------------

class TestSecretManager:
    """Tests for secret manager routing and fallback logic."""

    def test_default_backend_is_dotenv(self, tmp_path, monkeypatch):
        """Test that manager defaults to dotenv backend."""
        monkeypatch.chdir(tmp_path)
        manager = SecretManager()
        assert 'DotEnv' in manager.backend_name()

    def test_dotenv_set_and_get(self, tmp_path):
        """Test set and get through the manager with dotenv."""
        manager = SecretManager({'backend': 'dotenv', 'dotenv_path': str(tmp_path / '.env')})
        manager.set('key1', 'value1')

        assert manager.get('key1') == 'value1'

    def test_env_var_fallback(self, tmp_path, monkeypatch):
        """Test fallback to plain env var when key not in .env."""
        monkeypatch.setenv('MY_SECRET', 'from_env')
        manager = SecretManager({'backend': 'dotenv', 'dotenv_path': str(tmp_path / '.env')})

        # Key not in .env, should fall back to MY_SECRET env var
        assert manager.get('my_secret') == 'from_env'

    def test_default_value(self, tmp_path):
        """Test default value returned when secret not found anywhere."""
        manager = SecretManager({'backend': 'dotenv', 'dotenv_path': str(tmp_path / '.env')})

        assert manager.get('nonexistent', default='fallback') == 'fallback'

    def test_default_none_when_missing(self, tmp_path):
        """Test None returned when no default and secret not found."""
        manager = SecretManager({'backend': 'dotenv', 'dotenv_path': str(tmp_path / '.env')})

        assert manager.get('nonexistent') is None

    @patch('overtime.secrets.backends.onepassword.subprocess.run')
    def test_op_routing(self, mock_run, tmp_path):
        """Test that op:// keys are routed to 1Password."""
        mock_run.side_effect = [
            MagicMock(returncode=0),                              # --version
            MagicMock(stdout='1password-secret\n', returncode=0)  # read
        ]

        manager = SecretManager({'backend': 'dotenv', 'dotenv_path': str(tmp_path / '.env')})
        value = manager.get('op://Dev/TestItem/password')

        assert value == '1password-secret'

    def test_set_op_key_raises(self, tmp_path):
        """Test that trying to set an op:// key raises SecretError."""
        manager = SecretManager({'backend': 'dotenv', 'dotenv_path': str(tmp_path / '.env')})

        with pytest.raises(SecretError, match="Cannot write to 1Password"):
            manager.set('op://Dev/X/y', 'value')

    def test_delete_op_key_raises(self, tmp_path):
        """Test that trying to delete an op:// key raises SecretError."""
        manager = SecretManager({'backend': 'dotenv', 'dotenv_path': str(tmp_path / '.env')})

        with pytest.raises(SecretError, match="Cannot delete from 1Password"):
            manager.delete('op://Dev/X/y')

    def test_unknown_backend_raises(self):
        """Test that an unknown backend type raises SecretError."""
        with pytest.raises(SecretError, match="Unknown secret backend"):
            SecretManager({'backend': 'unknown_backend'})


# ---------------------------------------------------------------------------
# Secret resolution in config loader
# ---------------------------------------------------------------------------

class TestSecretResolution:
    """Tests for ${secret:key} resolution in config data."""

    def test_resolve_plain_key(self, tmp_path):
        """Test resolving a plain ${secret:key} from .env."""
        from overtime.config.loader import _resolve_secrets

        env_path = str(tmp_path / '.env')
        manager = SecretManager({'backend': 'dotenv', 'dotenv_path': env_path})
        manager.set('pm_password', 'resolved_password')

        data = {'proxmox': {'pm_password': '${secret:pm_password}'}}
        result = _resolve_secrets(data, manager)

        assert result['proxmox']['pm_password'] == 'resolved_password'

    @patch('overtime.secrets.backends.onepassword.subprocess.run')
    def test_resolve_op_key(self, mock_run, tmp_path):
        """Test resolving an op:// ${secret:} reference."""
        from overtime.config.loader import _resolve_secrets

        mock_run.side_effect = [
            MagicMock(returncode=0),                              # --version
            MagicMock(stdout='op_secret_value\n', returncode=0)   # read
        ]

        manager = SecretManager({'backend': 'dotenv', 'dotenv_path': str(tmp_path / '.env')})

        data = {'proxmox': {'pm_password': '${secret:op://Dev/Proxmox/password}'}}
        result = _resolve_secrets(data, manager)

        assert result['proxmox']['pm_password'] == 'op_secret_value'

    def test_resolve_missing_secret_raises(self, tmp_path):
        """Test that a missing secret raises ConfigurationError."""
        from overtime.config.loader import _resolve_secrets
        from overtime.utils.exceptions import ConfigurationError

        manager = SecretManager({'backend': 'dotenv', 'dotenv_path': str(tmp_path / '.env')})
        data = {'proxmox': {'pm_password': '${secret:missing_key}'}}

        with pytest.raises(ConfigurationError, match="Secret not found"):
            _resolve_secrets(data, manager)

    def test_non_secret_strings_untouched(self, tmp_path):
        """Test that regular strings are not modified."""
        from overtime.config.loader import _resolve_secrets

        manager = SecretManager({'backend': 'dotenv', 'dotenv_path': str(tmp_path / '.env')})
        data = {'proxmox': {'pm_api_url': 'https://192.168.0.100:8006'}}
        result = _resolve_secrets(data, manager)

        assert result['proxmox']['pm_api_url'] == 'https://192.168.0.100:8006'

    def test_nested_resolution(self, tmp_path):
        """Test that resolution works at any nesting depth."""
        from overtime.config.loader import _resolve_secrets

        env_path = str(tmp_path / '.env')
        manager = SecretManager({'backend': 'dotenv', 'dotenv_path': env_path})
        manager.set('deep_secret', 'deep_value')

        data = {'level1': {'level2': {'level3': '${secret:deep_secret}'}}}
        result = _resolve_secrets(data, manager)

        assert result['level1']['level2']['level3'] == 'deep_value'

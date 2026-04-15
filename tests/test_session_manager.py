#======================================================================================================
# Tests for the SessionManager
#======================================================================================================

from __future__ import annotations

import pytest

from backend.src.managers.session_manager import SessionManager, _selector_to_field_name


class TestSessionManagerUtils:

    def test_extract_domain_simple(self):
        """Extracts domain from a standard URL."""
        mgr = SessionManager.__new__(SessionManager)
        assert mgr._extract_domain("https://example.com/page") == "example.com"

    def test_extract_domain_with_port(self):
        """Strips port number from domain."""
        mgr = SessionManager.__new__(SessionManager)
        assert mgr._extract_domain("https://example.com:8080/page") == "example.com"

    def test_extract_domain_with_subdomain(self):
        """Preserves subdomains."""
        mgr = SessionManager.__new__(SessionManager)
        assert mgr._extract_domain("https://api.example.com/v1") == "api.example.com"

    def test_extract_domain_lowercases(self):
        """Domain is always lowercased."""
        mgr = SessionManager.__new__(SessionManager)
        assert mgr._extract_domain("https://EXAMPLE.COM/page") == "example.com"


class TestSelectorToFieldName:

    def test_name_attribute_double_quotes(self):
        """Extracts field name from name="..." selector."""
        assert _selector_to_field_name('input[name="email"]', "default") == "email"

    def test_name_attribute_single_quotes(self):
        """Extracts field name from name='...' selector."""
        assert _selector_to_field_name("input[name='user_id']", "default") == "user_id"

    def test_id_selector(self):
        """Extracts field name from #id selector."""
        assert _selector_to_field_name("#login-email", "default") == "login-email"

    def test_id_with_suffix(self):
        """Strips attribute selectors from #id."""
        assert _selector_to_field_name("#password[type='password']", "default") == "password"

    def test_default_fallback(self):
        """Returns default when selector can't be parsed."""
        assert _selector_to_field_name("div.form-control", "username") == "username"

    def test_none_returns_default(self):
        """Returns default when selector is None."""
        assert _selector_to_field_name(None, "password") == "password"

    def test_empty_returns_default(self):
        """Returns default when selector is empty string."""
        assert _selector_to_field_name("", "password") == "password"

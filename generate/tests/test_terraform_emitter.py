"""Tests for the Terraform emitter: field view building and default validation."""

from __future__ import annotations

import pytest

from generate.emitter.terraform_emitter import _build_field_views, _is_sensitive_field
from generate.model.ir import ModelField, ModelItem


def _make_item(fields: list[ModelField], name: str = "test_item") -> ModelItem:
    return ModelItem(
        name=name,
        go_name=name.capitalize(),
        container_name=name + "s",
        fields=fields,
    )


def _make_field(
    name: str,
    *,
    required: bool = True,
    default: str | None = None,
    options: list[str] | None = None,
    volatile: bool = False,
    go_type: str = "string",
) -> ModelField:
    return ModelField(
        name=name,
        field_type="OptionField" if options else "TextField",
        go_name=name.capitalize(),
        json_name=name,
        required=required,
        default=default,
        volatile=volatile,
        options=options or [],
        go_type=go_type,
    )


class TestBuildFieldViewsDefaultValidation:
    def test_valid_default_in_options_passes(self):
        field = _make_field("type", required=True, default="host", options=["host", "network", "port"])
        views = _build_field_views(_make_item([field]))
        assert len(views) == 1
        assert views[0].default_value == "host"

    def test_invalid_default_not_in_options_raises(self):
        """Unknown item + unknown default that is not in options raises."""
        field = _make_field("kind", required=True, default="bad", options=["good", "better"])
        with pytest.raises(ValueError, match="default value 'bad' is not in options"):
            _build_field_views(_make_item([field]))

    def test_alias_type_default_alert_is_corrected(self):
        """alias.type default='alert' must be corrected to 'host' via _DEFAULT_CORRECTIONS."""
        alias_options = [
            "host", "network", "port", "url", "urltable", "urljson",
            "geoip", "networkgroup", "mac", "asn", "dynipv6host",
            "authgroup", "internal", "external",
        ]
        field = _make_field("type", required=True, default="alert", options=alias_options)
        views = _build_field_views(_make_item([field], name="alias"))
        assert len(views) == 1
        assert views[0].default_value == "host"

    def test_unknown_item_alias_type_alert_still_raises(self):
        """Non-alias item with type=alert is NOT corrected — should still raise."""
        alias_options = [
            "host", "network", "port", "url", "urltable", "urljson",
            "geoip", "networkgroup", "mac", "asn", "dynipv6host",
            "authgroup", "internal", "external",
        ]
        field = _make_field("type", required=True, default="alert", options=alias_options)
        with pytest.raises(ValueError, match="default value 'alert' is not in options"):
            _build_field_views(_make_item([field], name="rule"))

    def test_vlan_pcp_default_zero_raises_without_correction(self):
        """pcp with old tag-name options (pcp0, pcp1...) raises when default='0'."""
        pcp_options = ["pcp1", "pcp0", "pcp2", "pcp3", "pcp4", "pcp5", "pcp6", "pcp7"]
        field = _make_field("pcp", required=True, default="0", options=pcp_options)
        with pytest.raises(ValueError, match="default value '0' is not in options"):
            _build_field_views(_make_item([field]))

    def test_vlan_pcp_default_zero_passes_with_value_attr_options(self):
        """After the XML parser fix, pcp options are value-attr based (0,1,2...)."""
        pcp_options = ["1", "0", "2", "3", "4", "5", "6", "7"]
        field = _make_field("pcp", required=True, default="0", options=pcp_options)
        views = _build_field_views(_make_item([field]))
        assert len(views) == 1
        assert views[0].default_value == "0"

    def test_default_without_options_is_not_validated(self):
        """Defaults on free-text fields (no options) should not be validated."""
        field = _make_field("description", required=True, default="my default")
        views = _build_field_views(_make_item([field]))
        assert len(views) == 1
        assert views[0].default_value == "my default"

    def test_optional_field_default_ignored_by_validator(self):
        """Optional fields have default_value=None; the check is never reached."""
        field = _make_field("type", required=False, default="alert", options=["host", "network"])
        views = _build_field_views(_make_item([field]))
        assert len(views) == 1
        assert views[0].default_value is None

    def test_volatile_field_default_ignored(self):
        """Volatile fields are always computed; their default is not emitted."""
        field = _make_field("status", required=True, default="alert", volatile=True, options=["host", "network"])
        views = _build_field_views(_make_item([field]))
        assert len(views) == 1
        assert views[0].default_value is None

    def test_error_message_includes_field_and_item_name(self):
        """Error message must identify which item and field is broken."""
        field = _make_field("kind", required=True, default="bad", options=["good"])
        item = ModelItem(name="widget", go_name="Widget", container_name="widgets", fields=[field])
        with pytest.raises(ValueError, match=r"Field 'widget\.kind'"):
            _build_field_views(item)

    def test_multiple_field_csv_default_not_validated(self):
        """Multiple=Y fields have CSV defaults; skip single-value validation."""
        field = _make_field("protocols", required=True, default="h1,h2", options=["h1", "h2", "h3"])
        field.multiple = True
        views = _build_field_views(_make_item([field]))
        assert len(views) == 1
        assert views[0].default_value == "h1,h2"


class TestSensitiveFieldDetection:
    def test_password_is_sensitive(self):
        assert _is_sensitive_field("user", "password") is True

    def test_psk_is_sensitive(self):
        assert _is_sensitive_field("client", "psk") is True

    def test_secret_is_sensitive(self):
        assert _is_sensitive_field("server", "secret") is True

    def test_privkey_is_sensitive(self):
        assert _is_sensitive_field("wireguard_server", "privkey") is True

    def test_private_key_camel_is_sensitive(self):
        assert _is_sensitive_field("keypair", "privateKey") is True

    def test_tunnel_password_is_sensitive(self):
        assert _is_sensitive_field("user", "tunnel_password") is True

    def test_key_in_openvpn_context_is_sensitive(self):
        """A field named 'key' in a non-excluded context must be sensitive."""
        assert _is_sensitive_field("statickey", "key") is True

    def test_key_in_ipsec_psk_context_is_sensitive(self):
        assert _is_sensitive_field("psk", "Key") is True

    def test_key_in_zabbix_alias_is_not_sensitive(self):
        """zabbixagent alias key is a metric identifier, not a credential."""
        assert _is_sensitive_field("alias", "key") is False

    def test_key_in_zabbix_userparameter_is_not_sensitive(self):
        assert _is_sensitive_field("userparameter", "key") is False

    def test_name_field_is_not_sensitive(self):
        assert _is_sensitive_field("user", "name") is False

    def test_description_is_not_sensitive(self):
        assert _is_sensitive_field("server", "description") is False

    def test_enabled_is_not_sensitive(self):
        assert _is_sensitive_field("server", "enabled") is False

    def test_sensitive_field_sets_view_sensitive_true(self):
        """_build_field_views must propagate sensitivity to TFFieldView."""
        field = _make_field("password", required=False)
        views = _build_field_views(_make_item([field]))
        assert len(views) == 1
        assert views[0].sensitive is True

    def test_non_sensitive_field_sets_view_sensitive_false(self):
        field = _make_field("description", required=False)
        views = _build_field_views(_make_item([field]))
        assert len(views) == 1
        assert views[0].sensitive is False

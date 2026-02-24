"""Tests for generate.parser.endpoint_resolver module."""

from __future__ import annotations

import pytest

from generate.model.ir import (
    Controller,
    Endpoint,
    Model,
    ModelField,
    ModelItem,
    Module,
)
from generate.parser.endpoint_resolver import (
    _match_item,
    _match_item_suffix,
    _parse_crud,
    resolve_endpoints,
)


# ---------------------------------------------------------------------------
# Helpers: synthetic model objects
# ---------------------------------------------------------------------------

def _make_item(name: str, container: str = "", fields: list[ModelField] | None = None) -> ModelItem:
    """Create a synthetic ModelItem for testing."""
    return ModelItem(
        name=name,
        go_name=name[0].upper() + name[1:],
        container_name=container or (name + "s"),
        fields=fields or [],
    )


def _make_field(name: str, field_type: str = "text") -> ModelField:
    """Create a synthetic ModelField for testing."""
    return ModelField(
        name=name,
        field_type=field_type,
        go_name=name[0].upper() + name[1:],
        json_name=name,
    )


def _make_endpoint(
    command: str,
    controller: str = "alias",
    module: str = "firewall",
) -> Endpoint:
    """Create a synthetic Endpoint for testing."""
    return Endpoint(
        methods=["POST"],
        module=module,
        controller=controller,
        command=command,
        command_camel=command,
        url_path=f"/api/{module}/{controller}/{command}",
        go_method_name=f"{controller.title()}{command.title()}",
    )


# ---------------------------------------------------------------------------
# _parse_crud
# ---------------------------------------------------------------------------

class TestParseCrud:
    """Tests for _parse_crud which splits a command into (verb, suffix)."""

    def test_add_item(self):
        assert _parse_crud("add_item") == ("add", "item")

    def test_set_alias(self):
        assert _parse_crud("set_alias") == ("set", "alias")

    def test_get_rule(self):
        assert _parse_crud("get_rule") == ("get", "rule")

    def test_del_acl(self):
        assert _parse_crud("del_acl") == ("del", "acl")

    def test_search_host(self):
        assert _parse_crud("search_host") == ("search", "host")

    def test_toggle_entry(self):
        assert _parse_crud("toggle_entry") == ("toggle", "entry")

    def test_no_crud_prefix(self):
        """Commands without CRUD prefix return empty tuple."""
        assert _parse_crud("reconfigure") == ("", "")

    def test_prefix_without_suffix(self):
        """A bare CRUD prefix with trailing underscore but no suffix returns empty."""
        assert _parse_crud("add_") == ("", "")

    def test_non_crud_prefix(self):
        assert _parse_crud("flush_rules") == ("", "")

    def test_multi_word_suffix(self):
        assert _parse_crud("add_host_alias") == ("add", "host_alias")

    def test_del_underscore_only(self):
        assert _parse_crud("del_") == ("", "")

    def test_search_multi_word(self):
        assert _parse_crud("search_layer4_openvpn") == ("search", "layer4_openvpn")

    def test_set_single_char_suffix(self):
        assert _parse_crud("set_x") == ("set", "x")


# ---------------------------------------------------------------------------
# _match_item - exact match
# ---------------------------------------------------------------------------

class TestMatchItemExact:
    """Tests for _match_item: exact name match (priority 2)."""

    def test_exact_match_by_name(self):
        alias = _make_item("alias", "aliases")
        result = _match_item("alias", "somectrl", [alias])
        assert result is alias

    def test_exact_match_case_insensitive(self):
        alias = _make_item("Alias", "aliases")
        result = _match_item("alias", "somectrl", [alias])
        assert result is alias

    def test_no_match_returns_none(self):
        alias = _make_item("alias", "aliases")
        result = _match_item("rule", "somectrl", [alias])
        assert result is None

    def test_exact_match_preferred_over_container(self):
        """When item name matches, it should be preferred over container match."""
        alias = _make_item("alias", "rules")
        rule = _make_item("rule", "alias")
        result = _match_item("alias", "somectrl", [alias, rule])
        assert result is alias


# ---------------------------------------------------------------------------
# _match_item - container match
# ---------------------------------------------------------------------------

class TestMatchItemContainer:
    """Tests for _match_item: container name match (priority 3)."""

    def test_container_match(self):
        alias = _make_item("alias", "myaliases")
        result = _match_item("myaliases", "somectrl", [alias])
        assert result is alias

    def test_container_match_case_insensitive(self):
        alias = _make_item("alias", "MyAliases")
        result = _match_item("myaliases", "somectrl", [alias])
        assert result is alias


# ---------------------------------------------------------------------------
# _match_item - normalized match
# ---------------------------------------------------------------------------

class TestMatchItemNormalized:
    """Tests for _match_item: normalized match (priority 4)."""

    def test_normalized_name_match(self):
        """Underscores and case are stripped for comparison."""
        item = _make_item("key_pair", "keypairs")
        result = _match_item("keypair", "somectrl", [item])
        assert result is item

    def test_normalized_container_match(self):
        item = _make_item("something", "key_pairs")
        result = _match_item("keypairs", "somectrl", [item])
        assert result is item


# ---------------------------------------------------------------------------
# _match_item - plural forms
# ---------------------------------------------------------------------------

class TestMatchItemPlural:
    """Tests for _match_item: plural matching (priority 5)."""

    def test_plural_s_name_match(self):
        """relay -> relays (item name)."""
        relays = _make_item("relays", "relaycontainer")
        result = _match_item("relay", "somectrl", [relays])
        assert result is relays

    def test_plural_s_container_match(self):
        """relay -> relays (container name)."""
        item = _make_item("myrelay", "relays")
        result = _match_item("relay", "somectrl", [item])
        assert result is item

    def test_plural_ies_name_match(self):
        """entry -> entries (item name)."""
        entries = _make_item("entries", "entrycontainer")
        result = _match_item("entry", "somectrl", [entries])
        assert result is entries

    def test_plural_ies_container_match(self):
        """entry -> entries (container name)."""
        item = _make_item("myentry", "entries")
        result = _match_item("entry", "somectrl", [item])
        assert result is item

    def test_no_false_ies_for_non_y_suffix(self):
        """Words not ending in 'y' should not try -ies form.

        Note: 'alia' does not end in 'y' so 'aliaies' won't be tried as a
        plural, but the startswith fallback will match 'aliaies' because
        'aliaies'.startswith('alia') is True and len('alia') >= 3.

        To isolate the -ies behavior, use a suffix shorter than 3 chars
        so startswith is blocked, or use items that don't match startswith.
        """
        # Use a 2-char suffix so startswith (>= 3 chars required) is blocked
        item = _make_item("abies", "container")
        result = _match_item("ab", "somectrl", [item])
        # "ab" doesn't end in "y", so "abies" is not tried as plural.
        # "ab" is < 3 chars so startswith is also blocked.
        assert result is None


# ---------------------------------------------------------------------------
# _match_item - suffix + "ing"
# ---------------------------------------------------------------------------

class TestMatchItemSuffixIng:
    """Tests for _match_item: suffix + 'ing' (priority 6)."""

    def test_forward_to_forwarding(self):
        forwarding = _make_item("forwarding", "forwardings")
        result = _match_item("forward", "somectrl", [forwarding])
        assert result is forwarding

    def test_no_false_ing(self):
        item = _make_item("notrelated", "container")
        result = _match_item("forward", "somectrl", [item])
        assert result is None


# ---------------------------------------------------------------------------
# _match_item - endswith
# ---------------------------------------------------------------------------

class TestMatchItemEndsWith:
    """Tests for _match_item: item name ends with suffix."""

    def test_endswith_name(self):
        """boot -> dhcp_boot (item name endswith 'boot')."""
        dhcp_boot = _make_item("dhcp_boot", "boots")
        result = _match_item("boot", "somectrl", [dhcp_boot])
        assert result is dhcp_boot

    def test_endswith_container(self):
        item = _make_item("something", "dhcp_boot")
        result = _match_item("boot", "somectrl", [item])
        assert result is item

    def test_endswith_plural(self):
        """tag -> dhcp_tags (container endswith 'tags')."""
        item = _make_item("dhcp_tag", "dhcp_tags")
        result = _match_item("tag", "somectrl", [item])
        # Exact endswith on name: "dhcptag" endswith "tag"? Yes.
        assert result is item

    def test_endswith_requires_longer_name(self):
        """The item name must be longer than the suffix (not equal)."""
        item = _make_item("boot", "boots")
        # "boot" exact match should be found earlier than endswith
        result = _match_item("boot", "somectrl", [item])
        assert result is item  # matched by exact, not endswith


# ---------------------------------------------------------------------------
# _match_item - _item suffix stripping
# ---------------------------------------------------------------------------

class TestMatchItemStripItemSuffix:
    """Tests for _match_item: stripping '_item' from item names."""

    def test_gateway_to_gateway_item(self):
        gw_item = _make_item("gateway_item", "gateways")
        result = _match_item("gateway", "somectrl", [gw_item])
        assert result is gw_item


# ---------------------------------------------------------------------------
# _match_item - compound suffix (last word, first word)
# ---------------------------------------------------------------------------

class TestMatchItemCompound:
    """Tests for _match_item: compound suffix strategies."""

    def test_compound_last_word(self):
        """host_alias -> tries 'alias' (last word)."""
        alias = _make_item("alias", "aliases")
        result = _match_item("host_alias", "somectrl", [alias])
        assert result is alias

    def test_compound_first_word(self):
        """reverse_proxy -> tries 'reverse' (first word)."""
        reverse = _make_item("reverse", "reverses")
        result = _match_item("reverse_proxy", "somectrl", [reverse])
        assert result is reverse

    def test_compound_concatenated(self):
        """layer4_openvpn -> tries 'layer4openvpn' (concatenated)."""
        item = _make_item("layer4openvpn", "container")
        result = _match_item("layer4_openvpn", "somectrl", [item])
        assert result is item

    def test_compound_last_word_preferred_over_first(self):
        """Last word is tried before first word."""
        first_item = _make_item("host", "hosts")
        last_item = _make_item("alias", "aliases")
        result = _match_item("host_alias", "somectrl", [first_item, last_item])
        assert result is last_item


# ---------------------------------------------------------------------------
# _match_item - startswith fallback
# ---------------------------------------------------------------------------

class TestMatchItemStartsWith:
    """Tests for _match_item: startswith fallback."""

    def test_startswith_name(self):
        """dest -> destinations (item name starts with 'dest')."""
        destinations = _make_item("destinations", "destcontainer")
        result = _match_item("dest", "somectrl", [destinations])
        assert result is destinations

    def test_startswith_container(self):
        item = _make_item("something", "destinations")
        result = _match_item("dest", "somectrl", [item])
        assert result is item

    def test_startswith_requires_min_3_chars(self):
        """Suffix must be >= 3 chars for startswith to apply."""
        item = _make_item("details", "detailcontainer")
        result = _match_item("de", "somectrl", [item])
        # "de" is only 2 chars, so startswith should not apply.
        # No other match strategy works either.
        assert result is None

    def test_startswith_exactly_3_chars(self):
        item = _make_item("destinations", "container")
        result = _match_item("des", "somectrl", [item])
        assert result is item

    def test_startswith_does_not_match_equal_length(self):
        """startswith requires item name to be strictly longer."""
        item = _make_item("dest", "container")
        # "dest" startswith "dest" but lengths are equal, so no startswith match.
        # But exact match catches it.
        result = _match_item("dest", "somectrl", [item])
        assert result is item  # found by exact match


# ---------------------------------------------------------------------------
# _match_item - manual overrides
# ---------------------------------------------------------------------------

class TestMatchItemManualOverrides:
    """Tests for _match_item: manual override map."""

    def test_clamav_url_override(self):
        """Override: ('clamav', 'url', 'url') -> 'list'."""
        url_item = _make_item("url", "urls")
        list_item = _make_item("list", "lists")
        result = _match_item("url", "url", [url_item, list_item], module_name="clamav")
        assert result is list_item

    def test_wol_host_override(self):
        """Override: ('wol', 'wol', 'host') -> 'wolentry'."""
        host_item = _make_item("host", "hosts")
        wol_item = _make_item("wolentry", "wolentries")
        result = _match_item("host", "wol", [host_item, wol_item], module_name="wol")
        assert result is wol_item

    def test_override_not_applied_for_different_module(self):
        """Override should not apply when module does not match."""
        url_item = _make_item("url", "urls")
        list_item = _make_item("list", "lists")
        result = _match_item("url", "url", [url_item, list_item], module_name="other")
        # No override, exact match on "url" item name
        assert result is url_item


# ---------------------------------------------------------------------------
# _match_item - "item" suffix delegation
# ---------------------------------------------------------------------------

class TestMatchItemItemSuffix:
    """Tests for _match_item when suffix == 'item' (delegates to _match_item_suffix)."""

    def test_item_suffix_matches_controller_name(self):
        alias = _make_item("alias", "aliases")
        result = _match_item("item", "alias", [alias])
        assert result is alias

    def test_item_suffix_single_item_fallback(self):
        """When suffix is 'item' and only one item exists, it is returned as fallback."""
        only_item = _make_item("something", "somethings")
        result = _match_item("item", "unrelated_ctrl", [only_item])
        assert result is only_item

    def test_item_suffix_no_match_multiple_items(self):
        """When multiple items exist and none match, return None."""
        item_a = _make_item("alpha", "alphas")
        item_b = _make_item("beta", "betas")
        result = _match_item("item", "unrelated", [item_a, item_b])
        assert result is None


# ---------------------------------------------------------------------------
# _match_item_suffix
# ---------------------------------------------------------------------------

class TestMatchItemSuffix:
    """Tests for _match_item_suffix which matches using controller name."""

    def test_exact_match(self):
        alias = _make_item("alias", "aliases")
        result = _match_item_suffix("alias", [alias])
        assert result is alias

    def test_exact_match_case_insensitive(self):
        alias = _make_item("Alias", "aliases")
        result = _match_item_suffix("alias", [alias])
        assert result is alias

    def test_normalized_match(self):
        """key_pairs controller matches keypair or key_pair item."""
        item = _make_item("key_pair", "keypairs")
        result = _match_item_suffix("key_pairs", [item])
        # _normalize("key_pairs") == "keypairs"
        # _normalize("key_pair") == "keypair"
        # These don't match by normalize, but container_norm "keypairs" == "keypairs"
        assert result is item

    def test_container_match(self):
        item = _make_item("something", "mycontroller")
        result = _match_item_suffix("mycontroller", [item])
        assert result is item

    def test_single_item_fallback(self):
        """When only one item exists and nothing else matches, return it."""
        only = _make_item("unrelated", "container")
        result = _match_item_suffix("nomatch", [only])
        assert result is only

    def test_no_match_multiple_items(self):
        """No fallback when multiple items exist."""
        a = _make_item("alpha", "alphas")
        b = _make_item("beta", "betas")
        result = _match_item_suffix("gamma", [a, b])
        assert result is None

    def test_startswith_match(self):
        """Controller 'tls' matches item 'tlsConfig' via startswith."""
        item = _make_item("tlsConfig", "configs")
        result = _match_item_suffix("tls", [item])
        # _normalize("tls") = "tls", _normalize("tlsConfig") = "tlsconfig"
        # "tlsconfig".startswith("tls") and len differs
        assert result is item

    def test_startswith_requires_min_3_chars(self):
        """startswith requires controller_norm >= 3 chars."""
        item = _make_item("abcdef", "container")
        result_short = _match_item_suffix("ab", [item, _make_item("other", "others")])
        # "ab" is only 2 chars; startswith won't apply. Multiple items -> no fallback.
        assert result_short is None


# ---------------------------------------------------------------------------
# resolve_endpoints - integration test
# ---------------------------------------------------------------------------

class TestResolveEndpoints:
    """Integration tests for resolve_endpoints using synthetic objects."""

    def _build_module(
        self,
        module_name: str = "firewall",
        controller_name: str = "alias",
        items: list[ModelItem] | None = None,
        endpoints: list[Endpoint] | None = None,
    ) -> Module:
        """Build a synthetic Module with one Controller for testing."""
        if items is None:
            items = [_make_item("alias", "aliases")]
        if endpoints is None:
            endpoints = [
                _make_endpoint("add_item", controller=controller_name, module=module_name),
                _make_endpoint("get_item", controller=controller_name, module=module_name),
                _make_endpoint("set_item", controller=controller_name, module=module_name),
                _make_endpoint("del_item", controller=controller_name, module=module_name),
                _make_endpoint("search_item", controller=controller_name, module=module_name),
                _make_endpoint("reconfigure", controller=controller_name, module=module_name),
            ]

        model = Model(
            mount=f"OPNsense.{module_name.title()}",
            xml_url="https://example.com/model.xml",
            items=items,
        )
        ctrl = Controller(
            name=f"{controller_name.title()}Controller",
            php_file=f"{controller_name.title()}Controller.php",
            endpoints=endpoints,
            model=model,
        )
        return Module(name=module_name, category="core", controllers=[ctrl])

    def test_crud_endpoints_resolved(self):
        """CRUD endpoints (add/get/set/del/search) should be resolved."""
        module = self._build_module()
        resolve_endpoints([module])

        ctrl = module.controllers[0]
        crud_eps = [ep for ep in ctrl.endpoints if ep.crud_verb]
        assert len(crud_eps) == 5  # add, get, set, del, search

        for ep in crud_eps:
            assert ep.model_item is not None
            assert ep.model_item.name == "alias"
            assert ep.item_json_key == "alias"

    def test_non_crud_endpoint_not_resolved(self):
        """Non-CRUD endpoints (like reconfigure) should not be resolved."""
        module = self._build_module()
        resolve_endpoints([module])

        ctrl = module.controllers[0]
        reconf = [ep for ep in ctrl.endpoints if ep.command == "reconfigure"][0]
        assert reconf.crud_verb == ""
        assert reconf.model_item is None

    def test_controller_without_model_skipped(self):
        """Controllers without a model should be skipped."""
        module = self._build_module()
        module.controllers[0].model = None
        resolve_endpoints([module])

        for ep in module.controllers[0].endpoints:
            assert ep.crud_verb == ""
            assert ep.model_item is None

    def test_controller_with_empty_model_items_skipped(self):
        """Controllers with an empty items list should be skipped."""
        module = self._build_module(items=[])
        resolve_endpoints([module])

        for ep in module.controllers[0].endpoints:
            assert ep.crud_verb == ""

    def test_direct_suffix_match(self):
        """Endpoints with a direct suffix (not 'item') should match by name."""
        alias = _make_item("alias", "aliases")
        ep = _make_endpoint("add_alias", controller="alias", module="firewall")
        module = self._build_module(items=[alias], endpoints=[ep])
        resolve_endpoints([module])

        assert ep.crud_verb == "add"
        assert ep.model_item is alias

    def test_multiple_items_correct_match(self):
        """With multiple items, the correct one should be matched."""
        alias = _make_item("alias", "aliases")
        rule = _make_item("rule", "rules")

        ep_alias = _make_endpoint("add_alias", controller="test", module="firewall")
        ep_rule = _make_endpoint("del_rule", controller="test", module="firewall")

        module = self._build_module(
            controller_name="test",
            items=[alias, rule],
            endpoints=[ep_alias, ep_rule],
        )
        resolve_endpoints([module])

        assert ep_alias.model_item is alias
        assert ep_rule.model_item is rule

    def test_manual_override_integration(self):
        """Manual overrides should work end-to-end through resolve_endpoints."""
        url_item = _make_item("url", "urls")
        list_item = _make_item("list", "lists")

        ep = _make_endpoint("add_url", controller="url", module="clamav")

        module = self._build_module(
            module_name="clamav",
            controller_name="url",
            items=[url_item, list_item],
            endpoints=[ep],
        )
        resolve_endpoints([module])

        assert ep.crud_verb == "add"
        assert ep.model_item is list_item
        assert ep.item_json_key == "list"

    def test_multiple_modules(self):
        """resolve_endpoints should iterate through all modules."""
        mod1 = self._build_module(module_name="firewall", controller_name="alias")
        mod2 = self._build_module(module_name="proxy", controller_name="proxy")

        # Replace mod2 items with proxy-specific item
        mod2.controllers[0].model.items = [_make_item("proxy", "proxies")]

        resolve_endpoints([mod1, mod2])

        # Both modules should have their CRUD endpoints resolved
        for mod in [mod1, mod2]:
            crud_eps = [ep for ep in mod.controllers[0].endpoints if ep.crud_verb]
            assert len(crud_eps) == 5

    def test_unmatched_suffix_stays_untyped(self):
        """When no item matches the suffix, the endpoint stays untyped."""
        alias = _make_item("alias", "aliases")
        ep = _make_endpoint("add_nonexistent", controller="test", module="firewall")

        module = self._build_module(
            controller_name="test",
            items=[alias],
            endpoints=[ep],
        )
        resolve_endpoints([module])

        assert ep.crud_verb == ""
        assert ep.model_item is None

    def test_toggle_verb(self):
        """toggle_ prefix should also be resolved."""
        alias = _make_item("alias", "aliases")
        ep = _make_endpoint("toggle_alias", controller="test", module="firewall")

        module = self._build_module(
            controller_name="test",
            items=[alias],
            endpoints=[ep],
        )
        resolve_endpoints([module])

        assert ep.crud_verb == "toggle"
        assert ep.model_item is alias

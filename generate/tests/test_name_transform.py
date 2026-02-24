"""Tests for generate.parser.name_transform module."""

from __future__ import annotations

import pytest

from generate.parser.name_transform import (
    _group_single_chars,
    controller_to_go_name,
    field_to_go_name,
    go_method_name,
    module_to_package,
    snake_to_camel,
    snake_to_pascal,
)


# ---------------------------------------------------------------------------
# _group_single_chars
# ---------------------------------------------------------------------------

class TestGroupSingleChars:
    """Tests for the internal _group_single_chars helper."""

    def test_no_single_chars(self):
        assert _group_single_chars(["get", "alias"]) == ["get", "alias"]

    def test_trailing_single_chars(self):
        assert _group_single_chars(["get", "alias", "u", "u", "i", "d"]) == [
            "get", "alias", "UUID",
        ]

    def test_middle_single_chars(self):
        assert _group_single_chars(["get", "c", "p", "u", "type"]) == [
            "get", "CPU", "type",
        ]

    def test_only_single_chars(self):
        assert _group_single_chars(["a", "b", "c"]) == ["ABC"]

    def test_single_char_at_start(self):
        assert _group_single_chars(["x", "value"]) == ["X", "value"]

    def test_multiple_groups(self):
        assert _group_single_chars(["a", "b", "word", "c", "d"]) == [
            "AB", "word", "CD",
        ]

    def test_empty_list(self):
        assert _group_single_chars([]) == []

    def test_single_element(self):
        assert _group_single_chars(["hello"]) == ["hello"]

    def test_single_char_alone(self):
        assert _group_single_chars(["z"]) == ["Z"]


# ---------------------------------------------------------------------------
# snake_to_camel
# ---------------------------------------------------------------------------

class TestSnakeToCamel:
    """Tests for snake_to_camel conversion."""

    def test_simple_two_word(self):
        assert snake_to_camel("add_item") == "addItem"

    def test_three_words(self):
        assert snake_to_camel("get_all_items") == "getAllItems"

    def test_no_underscores_passthrough(self):
        assert snake_to_camel("getOptions") == "getOptions"

    def test_leading_underscore_stripped(self):
        assert snake_to_camel("_rolling") == "rolling"

    def test_multiple_leading_underscores(self):
        assert snake_to_camel("__hidden_field") == "hiddenField"

    def test_single_char_acronym_grouping(self):
        assert snake_to_camel("get_alias_u_u_i_d") == "getAliasUUID"

    def test_cpu_acronym(self):
        assert snake_to_camel("get_c_p_u_type") == "getCPUType"

    def test_known_acronym_full_word(self):
        # Known acronyms in _KNOWN_ACRONYMS are stored lowercase, but the
        # check uses word.upper(), so full words like "url" are capitalized
        # normally (not uppercased to "URL"). Only grouped single chars
        # (e.g., u_u_i_d -> UUID) get full uppercasing.
        assert snake_to_camel("get_url") == "getUrl"

    def test_known_acronym_dns(self):
        assert snake_to_camel("set_dns") == "setDns"

    def test_known_acronym_id(self):
        assert snake_to_camel("get_id") == "getId"

    def test_single_word_with_underscore_prefix(self):
        assert snake_to_camel("_status") == "status"

    def test_empty_string(self):
        assert snake_to_camel("") == ""

    def test_single_word_no_underscore(self):
        assert snake_to_camel("reconfigure") == "reconfigure"

    def test_all_lowercase_parts(self):
        assert snake_to_camel("search_alias") == "searchAlias"

    def test_full_word_acronym_capitalized_normally(self):
        # Full words are not in the acronym check path (word.upper() != lowercase set entry)
        assert snake_to_camel("get_http_proxy") == "getHttpProxy"

    def test_acronym_at_start(self):
        # First word always lowercase in camelCase
        assert snake_to_camel("http_request") == "httpRequest"

    def test_full_word_acl(self):
        assert snake_to_camel("get_acl") == "getAcl"


# ---------------------------------------------------------------------------
# snake_to_pascal
# ---------------------------------------------------------------------------

class TestSnakeToPascal:
    """Tests for snake_to_pascal conversion."""

    def test_simple_two_word(self):
        assert snake_to_pascal("add_item") == "AddItem"

    def test_three_words(self):
        assert snake_to_pascal("get_all_items") == "GetAllItems"

    def test_no_underscores(self):
        assert snake_to_pascal("reconfigure") == "Reconfigure"

    def test_leading_underscore(self):
        assert snake_to_pascal("_carp_status") == "CarpStatus"

    def test_single_char_acronym(self):
        assert snake_to_pascal("get_alias_u_u_i_d") == "GetAliasUUID"

    def test_full_word_acronym_capitalized_normally(self):
        # Same as camelCase: full words like "url" are not matched by the
        # acronym check (word.upper() vs lowercase set), so they get normal
        # capitalization.
        assert snake_to_pascal("get_url") == "GetUrl"

    def test_full_word_dns_capitalized_normally(self):
        assert snake_to_pascal("set_dns") == "SetDns"

    def test_cpu_acronym(self):
        assert snake_to_pascal("get_c_p_u_type") == "GetCPUType"

    def test_empty_string(self):
        assert snake_to_pascal("") == ""

    def test_single_word(self):
        assert snake_to_pascal("service") == "Service"

    def test_already_pascal(self):
        # No underscores: first char uppercased, rest kept
        assert snake_to_pascal("AliasUtil") == "AliasUtil"

    def test_d_nat(self):
        assert snake_to_pascal("d_nat") == "DNat"


# ---------------------------------------------------------------------------
# controller_to_go_name
# ---------------------------------------------------------------------------

class TestControllerToGoName:
    """Tests for controller_to_go_name (delegates to snake_to_pascal)."""

    def test_alias_util(self):
        assert controller_to_go_name("alias_util") == "AliasUtil"

    def test_d_nat(self):
        assert controller_to_go_name("d_nat") == "DNat"

    def test_filter_base(self):
        assert controller_to_go_name("filter_base") == "FilterBase"

    def test_simple_name(self):
        assert controller_to_go_name("service") == "Service"


# ---------------------------------------------------------------------------
# module_to_package
# ---------------------------------------------------------------------------

class TestModuleToPackage:
    """Tests for module_to_package."""

    def test_simple_name(self):
        assert module_to_package("firewall") == "firewall"

    def test_no_change_needed(self):
        assert module_to_package("opncentral") == "opncentral"

    def test_uppercase_converted(self):
        assert module_to_package("Firewall") == "firewall"

    def test_underscores_removed(self):
        assert module_to_package("my_module") == "mymodule"

    def test_mixed_case_and_underscores(self):
        assert module_to_package("My_Module") == "mymodule"


# ---------------------------------------------------------------------------
# field_to_go_name
# ---------------------------------------------------------------------------

class TestFieldToGoName:
    """Tests for field_to_go_name."""

    def test_simple_lowercase(self):
        assert field_to_go_name("enabled") == "Enabled"

    def test_simple_word(self):
        assert field_to_go_name("proto") == "Proto"

    def test_no_separators(self):
        assert field_to_go_name("updatefreq") == "Updatefreq"

    def test_hyphenated(self):
        assert field_to_go_name("state-policy") == "StatePolicy"

    def test_multi_hyphenated(self):
        assert field_to_go_name("max-src-nodes") == "MaxSrcNodes"

    def test_underscored(self):
        assert field_to_go_name("source_net") == "SourceNet"

    def test_empty_string(self):
        assert field_to_go_name("") == ""

    def test_hyphen_with_acronym_word(self):
        # "dns" as a full word is not matched by the acronym check
        assert field_to_go_name("dns-server") == "DnsServer"

    def test_single_char(self):
        assert field_to_go_name("x") == "X"


# ---------------------------------------------------------------------------
# go_method_name
# ---------------------------------------------------------------------------

class TestGoMethodName:
    """Tests for go_method_name."""

    def test_alias_add_item(self):
        assert go_method_name("alias", "add_item") == "AliasAddItem"

    def test_alias_util_add(self):
        assert go_method_name("alias_util", "add") == "AliasUtilAdd"

    def test_service_reconfigure(self):
        assert go_method_name("service", "reconfigure") == "ServiceReconfigure"

    def test_d_nat_with_command(self):
        assert go_method_name("d_nat", "get_rule") == "DNatGetRule"

    def test_controller_with_acronym_word_command(self):
        assert go_method_name("service", "get_url") == "ServiceGetUrl"

"""Tests for the CLI emitter: resource derivation, verb mapping, column selection."""

from __future__ import annotations

import pytest

from generate.emitter.cli_emitter import (
    _build_verb_view,
    _cli_verb_from_endpoint,
    _columns_for_item,
    _resource_name_from_endpoint,
    _to_go_ident,
)
from generate.model.ir import Endpoint, ModelField, ModelItem, Parameter


def _make_endpoint(
    controller: str,
    command: str,
    crud_verb: str = "",
    methods: list[str] | None = None,
    parameters: list[Parameter] | None = None,
    model_item: ModelItem | None = None,
) -> Endpoint:
    """Helper to build an Endpoint for testing."""
    return Endpoint(
        methods=methods or ["GET"],
        module="test",
        controller=controller,
        command=command,
        command_camel=command,
        url_path=f"/api/test/{controller}/{command}",
        go_method_name=f"{controller.title()}{command.title()}",
        parameters=parameters or [],
        crud_verb=crud_verb,
        model_item=model_item,
    )


# ─── Resource name derivation ───────────────────────────────────────────────

class TestResourceNameDerivation:
    def test_crud_item_suffix_uses_controller(self):
        ep = _make_endpoint("alias", "add_item", crud_verb="add")
        assert _resource_name_from_endpoint(ep) == "alias"

    def test_crud_named_suffix_uses_suffix(self):
        ep = _make_endpoint("settings", "search_acl", crud_verb="search")
        assert _resource_name_from_endpoint(ep) == "acl"

    def test_crud_named_suffix_with_underscores(self):
        ep = _make_endpoint("settings", "add_tag_list", crud_verb="add")
        assert _resource_name_from_endpoint(ep) == "tag-list"

    def test_non_crud_uses_controller(self):
        ep = _make_endpoint("service", "reconfigure")
        assert _resource_name_from_endpoint(ep) == "service"

    def test_non_crud_get_uses_controller(self):
        ep = _make_endpoint("alias", "export")
        assert _resource_name_from_endpoint(ep) == "alias"


# ─── CLI verb mapping ────────────────────────────────────────────────────────

class TestCLIVerbMapping:
    def test_search_maps_to_list(self):
        ep = _make_endpoint("alias", "search_item", crud_verb="search")
        assert _cli_verb_from_endpoint(ep) == "list"

    def test_add_maps_to_create(self):
        ep = _make_endpoint("alias", "add_item", crud_verb="add")
        assert _cli_verb_from_endpoint(ep) == "create"

    def test_set_maps_to_update(self):
        ep = _make_endpoint("alias", "set_item", crud_verb="set")
        assert _cli_verb_from_endpoint(ep) == "update"

    def test_del_maps_to_delete(self):
        ep = _make_endpoint("alias", "del_item", crud_verb="del")
        assert _cli_verb_from_endpoint(ep) == "delete"

    def test_get_maps_to_get(self):
        ep = _make_endpoint("alias", "get_item", crud_verb="get")
        assert _cli_verb_from_endpoint(ep) == "get"

    def test_toggle_stays_toggle(self):
        ep = _make_endpoint("alias", "toggle_item", crud_verb="toggle")
        assert _cli_verb_from_endpoint(ep) == "toggle"

    def test_non_crud_uses_command_name(self):
        ep = _make_endpoint("service", "reconfigure")
        assert _cli_verb_from_endpoint(ep) == "reconfigure"

    def test_underscore_command_becomes_hyphen(self):
        ep = _make_endpoint("alias", "list_categories")
        assert _cli_verb_from_endpoint(ep) == "list-categories"


# ─── Column selection ─────────────────────────────────────────────────────────

def _make_field(json_name: str, go_name: str | None = None) -> ModelField:
    return ModelField(
        name=json_name,
        field_type="TextField",
        go_name=go_name or json_name.title(),
        json_name=json_name,
    )


class TestColumnSelection:
    def test_preferred_columns_come_first(self):
        item = ModelItem(
            name="alias",
            go_name="Alias",
            container_name="aliases",
            fields=[
                _make_field("description"),
                _make_field("type"),
                _make_field("name"),
                _make_field("enabled"),
            ],
        )
        cols = _columns_for_item(item)
        headers = [c["header"] for c in cols]
        # name and enabled should appear before description and type
        assert headers.index("NAME") < headers.index("DESCRIPTION")
        assert headers.index("ENABLED") < headers.index("DESCRIPTION")

    def test_at_most_8_columns(self):
        item = ModelItem(
            name="big",
            go_name="Big",
            container_name="bigs",
            fields=[_make_field(f"field{i}") for i in range(20)],
        )
        cols = _columns_for_item(item)
        assert len(cols) <= 8

    def test_empty_fields(self):
        item = ModelItem(name="empty", go_name="Empty", container_name="empties")
        cols = _columns_for_item(item)
        assert cols == []

    def test_header_uppercased(self):
        item = ModelItem(
            name="x",
            go_name="X",
            container_name="xs",
            fields=[_make_field("my_field", "MyField")],
        )
        cols = _columns_for_item(item)
        assert cols[0]["header"] == "MY FIELD"


# ─── Verb view construction ───────────────────────────────────────────────────

class TestBuildVerbView:
    def test_search_with_post_body(self):
        ep = _make_endpoint("alias", "search_item", crud_verb="search", methods=["POST"])
        view = _build_verb_view(ep, "list")
        assert view.is_search is True
        assert view.search_needs_body is True

    def test_search_without_body_for_get(self):
        ep = _make_endpoint("alias", "search_item", crud_verb="search", methods=["GET"])
        view = _build_verb_view(ep, "list")
        assert view.is_search is True
        assert view.search_needs_body is False

    def test_typed_add_sets_data_flag(self):
        item = ModelItem(name="alias", go_name="Alias", container_name="aliases")
        ep = _make_endpoint("alias", "add_item", crud_verb="add", methods=["POST"],
                            model_item=item)
        view = _build_verb_view(ep, "create")
        assert view.has_data_flag is True
        assert view.is_typed is True

    def test_required_params_become_positional(self):
        ep = _make_endpoint(
            "alias", "del_item", crud_verb="del",
            parameters=[Parameter(name="uuid", required=True)],
        )
        view = _build_verb_view(ep, "delete")
        assert view.positional_params == ["uuid"]

    def test_multiple_required_params(self):
        ep = _make_endpoint(
            "voucher", "drop_expired_vouchers",
            parameters=[
                Parameter(name="provider", required=True),
                Parameter(name="group", required=True),
            ],
            methods=["POST"],
        )
        view = _build_verb_view(ep, "drop-expired-vouchers")
        assert view.positional_params == ["provider", "group"]
        assert view.has_body_arg is True

    def test_untyped_post_sets_body_arg(self):
        ep = _make_endpoint("service", "reconfigure", methods=["POST"])
        view = _build_verb_view(ep, "reconfigure")
        assert view.has_body_arg is True
        assert view.has_data_flag is False

    def test_reserved_type_name_renamed(self):
        item = ModelItem(name="client", go_name="Client", container_name="clients")
        ep = _make_endpoint("client", "add_client", crud_verb="add", methods=["POST"],
                            model_item=item)
        view = _build_verb_view(ep, "create")
        assert view.item_type == "ClientConfig"


# ─── Go identifier conversion ─────────────────────────────────────────────────

class TestToGoIdent:
    def test_simple(self):
        assert _to_go_ident("alias") == "Alias"

    def test_hyphenated(self):
        assert _to_go_ident("tag-list") == "TagList"

    def test_multi_word(self):
        assert _to_go_ident("alias-util") == "AliasUtil"

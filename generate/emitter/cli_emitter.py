"""Emit Go CLI source files (internal/cli/gen/) from the parsed IR."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from generate.model.ir import APISpec, Endpoint, ModelItem, Module
from generate.parser.name_transform import _group_single_chars, module_to_package

# Go type names that conflict with generated code — must be renamed
_RESERVED_TYPE_NAMES = {"Client", "NewClient"}


def _safe_go_name(name: str) -> str:
    """Rename reserved type names to avoid conflicts (e.g., Client → ClientConfig)."""
    if name in _RESERVED_TYPE_NAMES:
        return name + "Config"
    return name

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
_CLI_OUTPUT_DIR = Path("internal/cli/gen")

# Preferred column order for table display
_PREFERRED_COLS = ["name", "enabled", "description", "type", "address", "port",
                   "interface", "proto", "content", "status"]

# CRUD verb -> CLI verb mapping
_CRUD_TO_CLI_VERB = {
    "search": "list",
    "get": "get",
    "add": "create",
    "set": "update",
    "del": "delete",
    "toggle": "toggle",
}


@dataclass
class CLIVerbView:
    """Template-friendly view of a single CLI verb (leaf command)."""
    cli_verb: str               # "list", "get", "create", etc.
    go_method: str              # Go SDK method name (e.g., "AliasSearchItem")
    crud_verb: str              # Original IR crud verb
    positional_params: list[str]  # required path param names, in order → args[i]
    has_data_flag: bool         # True if command takes --data JSON flag (typed add/set)
    has_body_arg: bool          # True if untyped POST endpoint (pass nil body)
    has_optional_params: bool   # True if SDK method has variadic opts (not used by CLI)
    item_type: str              # Go type name if typed, else ""
    is_typed: bool              # True if there's a model item
    is_search: bool             # True if crud_verb == "search"
    search_needs_body: bool     # True if search is POST (pass rowCount body)
    primary_method: str         # "GET" or "POST"
    url_path: str               # raw URL path for untyped


@dataclass
class CLIResourceView:
    """A named resource grouping one or more verbs."""
    resource: str           # CLI resource name (e.g., "alias", "acl")
    go_ident: str           # Go identifier fragment (e.g., "Alias", "TagList2")
    package_path: str       # Import path suffix (e.g., "firewall")
    item_type: str          # Go type used for columns (e.g., "Alias"), "" if mixed
    columns: list[dict[str, str]]  # [{header, field_name, extractor}]
    verbs: list[CLIVerbView]
    suggest_for: list[str] = field(default_factory=list)
    # Common prefix shared with sibling resources (e.g. "host" for host-override/host-alias)


@dataclass
class CLIModuleView:
    """Template-friendly view of one module."""
    module_name: str        # e.g. "firewall"
    cli_name: str           # cobra Use name; may differ from module_name if disambiguated
    package_name: str       # Go package name (e.g. "firewall")
    go_file_ident: str      # Identifier for the Go file and func (e.g. "Firewall")
    sdk_package: str        # Full import path (e.g. "github.com/.../opnsense/firewall")
    resources: list[CLIResourceView]


def _normalize_kebab(raw: str) -> str:
    """Apply acronym grouping to a snake_case string and return kebab-case.

    Consecutive single-char segments are collapsed into acronyms:
      c_p_u_type  -> cpu-type
      p_a_c_rule  -> pac-rule
      tag_list    -> tag-list
      acl         -> acl
    """
    parts = raw.split("_")
    grouped = _group_single_chars(parts)
    return "-".join(p.lower() for p in grouped if p)


def _resource_name_from_endpoint(ep: Endpoint) -> str:
    """Derive the CLI resource name from an endpoint.

    Rules:
    - CRUD suffix: add_item, get_item, set_item, del_item, search_item -> resource = controller name
    - CRUD suffix variant: search_acl, add_backend, etc. -> resource = normalized suffix
    - Non-CRUD: resource = controller name, verb = command as-is
    """
    cmd = ep.command
    # CRUD pattern with _item suffix
    if re.match(r'^(add|get|set|del|search|toggle)_item$', cmd):
        return ep.controller.lower().replace("_", "-")
    # CRUD pattern with named suffix (e.g., search_acl, add_p_a_c_rule)
    m = re.match(r'^(add|get|set|del|search|toggle)_(.+)$', cmd)
    if m:
        return _normalize_kebab(m.group(2))
    # Non-CRUD: use controller name
    return ep.controller.lower().replace("_", "-")


def _cli_verb_from_endpoint(ep: Endpoint) -> str:
    """Derive the CLI verb (leaf command name) from an endpoint."""
    cmd = ep.command
    if ep.crud_verb:
        return _CRUD_TO_CLI_VERB.get(ep.crud_verb) or ep.crud_verb
    return _normalize_kebab(cmd)


def _columns_for_item(item: ModelItem) -> list[dict[str, str]]:
    """Select up to 8 display columns from a ModelItem, prioritising key fields."""
    fields = {f.json_name: f for f in item.fields}
    ordered = []

    # First: preferred columns in order
    for pref in _PREFERRED_COLS:
        if pref in fields:
            ordered.append(fields[pref])
        if len(ordered) == 8:
            break

    # Then: fill remaining slots with other fields
    if len(ordered) < 8:
        for f in item.fields:
            if f not in ordered:
                ordered.append(f)
            if len(ordered) == 8:
                break

    result = []
    for f in ordered:
        # Mirror go_emitter pointer logic: optional non-string fields use *Type
        omitempty = not f.required or f.volatile
        go_type = f.go_type
        if omitempty and go_type != "string":
            go_type = "*" + go_type
        result.append({
            "header": f.json_name.upper().replace("_", " "),
            "field_name": f.go_name,
            "go_type": go_type,
        })
    return result


def _build_verb_view(ep: Endpoint, cli_verb: str) -> CLIVerbView:
    """Build a CLIVerbView from an Endpoint."""
    # All required parameters become positional CLI args
    positional_params = [p.name for p in ep.parameters if p.required]
    has_optional_params = any(not p.required for p in ep.parameters)

    primary = ep.methods[-1] if len(ep.methods) > 1 else ep.methods[0]
    has_body = primary == "POST"
    is_typed = bool(ep.model_item)

    has_data_flag = ep.crud_verb in ("add", "set") and is_typed
    is_search = ep.crud_verb == "search"
    # For search, pass rowCount body only if the SDK method accepts a body (POST)
    search_needs_body = is_search and has_body

    return CLIVerbView(
        cli_verb=cli_verb,
        go_method=ep.go_method_name,
        crud_verb=ep.crud_verb,
        positional_params=positional_params,
        has_data_flag=has_data_flag,
        has_body_arg=has_body and not is_typed and not is_search,
        has_optional_params=has_optional_params,
        item_type=_safe_go_name(ep.model_item.go_name) if ep.model_item else "",
        is_typed=is_typed,
        is_search=is_search,
        search_needs_body=search_needs_body,
        primary_method=primary,
        url_path=ep.url_path,
    )


def _to_go_ident(name: str) -> str:
    """Convert a kebab/snake resource name to a PascalCase Go identifier fragment."""
    return name.replace("-", " ").replace("_", " ").title().replace(" ", "")


def _collect_resources(module: Module) -> list[CLIResourceView]:
    """Group endpoints into CLIResourceViews."""
    # resource_name -> list of (ep, cli_verb)
    resource_eps: dict[str, list[tuple[Endpoint, str]]] = {}

    for ctrl in module.controllers:
        if ctrl.is_abstract:
            continue
        seen_methods: set[str] = set()
        for ep in ctrl.endpoints:
            if ep.go_method_name in seen_methods:
                continue
            seen_methods.add(ep.go_method_name)
            res = _resource_name_from_endpoint(ep)
            cli_verb = _cli_verb_from_endpoint(ep)
            resource_eps.setdefault(res, []).append((ep, cli_verb))

    # Merge plural resource names into their singular form.
    # OPNsense often uses searchAcls (plural) alongside addAcl/delAcl (singular).
    # After acronym normalization the plural is e.g. "acls" vs singular "acl".
    for res in list(resource_eps.keys()):
        singular = res[:-1] if res.endswith("s") and len(res) > 2 else None
        if singular and singular in resource_eps:
            resource_eps[singular].extend(resource_eps.pop(res))

    pkg = module_to_package(module.name)
    raw_resources = []
    for res_name, ep_list in resource_eps.items():
        # Determine the primary item_type (from typed CRUD endpoints)
        item_type = ""
        item_model: ModelItem | None = None
        for ep, _ in ep_list:
            if ep.model_item and not item_type:
                item_type = _safe_go_name(ep.model_item.go_name)
                item_model = ep.model_item

        columns = _columns_for_item(item_model) if item_model else []

        # Deduplicate verbs: prefer typed CRUD endpoints over untyped for same cli_verb.
        # Key = cli_verb, value = (ep, score) where higher score wins.
        best: dict[str, tuple[Endpoint, int]] = {}
        for ep, cli_verb in ep_list:
            # Score: typed CRUD > untyped CRUD > plain
            score = 0
            if ep.crud_verb and ep.model_item:
                score = 2
            elif ep.crud_verb:
                score = 1
            prev = best.get(cli_verb)
            if prev is None or score > prev[1]:
                best[cli_verb] = (ep, score)

        verbs = []
        for cli_verb, (ep, _) in best.items():
            verb_view = _build_verb_view(ep, cli_verb)
            verbs.append(verb_view)

        raw_resources.append((res_name, item_type, columns, verbs))

    # Resolve Go identifier conflicts:
    # container: new{Module}{res_go}Cmd, verb: new{Module}{res_go}{verb_go}Cmd
    # Conflict when res_A.go_ident == res_B.go_ident + verb_B.go_ident
    # Strategy: assign go_idents and re-assign with numeric suffix for conflicts.
    ident_counts: dict[str, int] = {}
    resolved: list[CLIResourceView] = []

    for res_name, item_type, columns, verbs in raw_resources:
        base = _to_go_ident(res_name)
        if base in ident_counts:
            ident_counts[base] += 1
            go_ident = base + str(ident_counts[base])
        else:
            ident_counts[base] = 0
            go_ident = base

        resolved.append(CLIResourceView(
            resource=res_name,
            go_ident=go_ident,
            package_path=pkg,
            item_type=item_type,
            columns=columns,
            verbs=verbs,
        ))

    # Second pass: detect verb-level conflicts with resource-level names.
    # new{M}{ResGo}{VerbGo}Cmd conflicts with new{M}{ResGo2}Cmd when ResGo+VerbGo == ResGo2
    all_res_idents = {r.go_ident for r in resolved}
    for res in resolved:
        for verb in res.verbs:
            combined = res.go_ident + _to_go_ident(verb.cli_verb)
            if combined in all_res_idents:
                # Rename the conflicting resource (the one whose ident == combined)
                for other in resolved:
                    if other.go_ident == combined:
                        other.go_ident = combined + "Resource"
                        all_res_idents.discard(combined)
                        all_res_idents.add(other.go_ident)
                        break

    # Third pass: populate SuggestFor for resources sharing a common hyphen-prefix.
    # e.g. "host-override" and "host-alias" both suggest "host" when user types it.
    resource_names = {r.resource for r in resolved}
    prefix_groups: dict[str, list[CLIResourceView]] = {}
    for res in resolved:
        if "-" in res.resource:
            prefix = res.resource.split("-")[0]
            # Only hint the prefix if it is not itself an existing resource
            if prefix not in resource_names:
                prefix_groups.setdefault(prefix, []).append(res)
    for prefix, members in prefix_groups.items():
        if len(members) > 1:
            for res in members:
                res.suggest_for = [prefix]

    return resolved


def emit_cli(spec: APISpec, output_dir: str | Path | None = None) -> None:
    """Emit all CLI Go source files from the API spec."""
    out = Path(output_dir) if output_dir else _CLI_OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    module_views: list[CLIModuleView] = []
    seen_packages: set[str] = set()

    for module in spec.modules:
        # Collect endpoints and skip empty modules
        has_endpoints = any(
            not ctrl.is_abstract and ctrl.endpoints
            for ctrl in module.controllers
        )
        if not has_endpoints:
            continue

        pkg = module_to_package(module.name)
        # Handle duplicate package names (core vs plugins)
        if pkg in seen_packages:
            pkg = module.category + pkg
        seen_packages.add(pkg)

        resources = _collect_resources(module)
        if not resources:
            continue

        go_ident = module.name.replace("_", " ").title().replace(" ", "")
        # Disambiguate Go identifier if another module already used it
        # (e.g., core/diagnostics vs plugins/diagnostics → PluginsDiagnostics)
        if any(v.go_file_ident == go_ident for v in module_views):
            go_ident = module.category.title() + go_ident

        # Disambiguate the Cobra Use name independently — the Go ident conflict
        # above already handled file-level uniqueness, but two modules can still
        # register the same CLI command name (e.g. both register "diagnostics").
        cli_name = module.name
        if any(v.cli_name == cli_name for v in module_views):
            cli_name = f"{module.category}-{module.name}"

        view = CLIModuleView(
            module_name=module.name,
            cli_name=cli_name,
            package_name=pkg,
            go_file_ident=go_ident,
            sdk_package=f"github.com/jontk/opnsense-cli/opnsense/{pkg}",
            resources=resources,
        )
        module_views.append(view)

        # Emit per-module file
        template = env.get_template("cli_module.go.j2")
        content = template.render(m=view)
        (out / f"{pkg}.go").write_text(content, encoding="utf-8")

    # Emit register.go
    template = env.get_template("cli_register.go.j2")
    content = template.render(modules=sorted(module_views, key=lambda v: v.package_name))
    (out / "register.go").write_text(content, encoding="utf-8")

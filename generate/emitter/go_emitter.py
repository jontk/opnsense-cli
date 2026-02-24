"""Emit Go source files from the parsed IR."""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from generate.model.ir import APISpec, Endpoint, ModelItem, Module
from generate.parser.name_transform import module_to_package

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
_OUTPUT_DIR = Path("opnsense")

# Go reserved words — package names must avoid these
_GO_RESERVED = {
    "break", "case", "chan", "const", "continue", "default", "defer", "else",
    "fallthrough", "for", "func", "go", "goto", "if", "import", "interface",
    "map", "package", "range", "return", "select", "struct", "switch", "type",
    "var",
}


@dataclass
class EndpointView:
    """Template-friendly view of an Endpoint."""
    go_method_name: str
    methods: list[str]
    url_path: str
    primary_method: str
    has_body: bool
    required_params: list[dict[str, str]]
    optional_params: list[dict[str, str | None]]
    parameters: list[dict[str, str | bool | None]]
    path_fmt: str  # fmt.Sprintf pattern with %s placeholders
    item_type: str  # Go type name (e.g., "Alias"), empty if untyped
    item_json_key: str  # JSON wrapper key (e.g., "alias"), empty if untyped
    crud_verb: str  # "add"/"get"/"set"/"del"/"search"/"toggle"/""


@dataclass
class ModuleView:
    """Template-friendly view of a module for api.go."""
    package_name: str
    field_name: str


@dataclass
class TypeFieldView:
    """Template-friendly view of a ModelField."""
    go_name: str
    json_name: str
    omitempty: bool
    options: list[str]


@dataclass
class TypeItemView:
    """Template-friendly view of a ModelItem."""
    name: str
    go_name: str
    fields: list[TypeFieldView] = dc_field(default_factory=list)


def emit(spec: APISpec, output_dir: str | Path | None = None) -> None:
    """Emit all Go source files from the API spec."""
    out = Path(output_dir) if output_dir else _OUTPUT_DIR
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    module_views: list[ModuleView] = []
    seen_packages: set[str] = set()

    for module in spec.modules:
        # Collect all non-abstract endpoints across all controllers
        endpoints = _collect_endpoints(module)
        if not endpoints:
            continue

        pkg = module_to_package(module.name)
        if pkg in _GO_RESERVED:
            pkg += "api"

        # Handle duplicate package names (e.g. core/diagnostics + plugins/diagnostics)
        if pkg in seen_packages:
            pkg = module.category + pkg
        seen_packages.add(pkg)

        pkg_dir = out / pkg
        pkg_dir.mkdir(parents=True, exist_ok=True)

        # Emit module.go
        ep_views = [_endpoint_view(ep) for ep in endpoints]
        needs_fmt = any(ev.path_fmt for ev in ep_views)
        has_typed = any(ev.item_type for ev in ep_views)
        _emit_module(env, pkg_dir, pkg, module.name, ep_views, needs_fmt, has_typed)

        # Emit types.go if we have model items
        items = _collect_model_items(module)
        if items:
            item_views = [_type_item_view(item) for item in items]
            # Collect response wrappers needed for get_* typed endpoints
            wrappers = _collect_response_wrappers(ep_views)
            _emit_types(env, pkg_dir, pkg, item_views, wrappers)

        # Track for api.go — deduplicate by field name
        field_name = _module_field_name(module.name)
        # If field name already used, prefix with category
        existing_fields = {mv.field_name for mv in module_views}
        if field_name in existing_fields:
            field_name = module.category.title() + field_name
        module_views.append(ModuleView(package_name=pkg, field_name=field_name))

    # Emit api.go
    if module_views:
        _emit_api(env, out, module_views)


def _collect_endpoints(module: Module) -> list[Endpoint]:
    """Collect all non-abstract, non-duplicate endpoints from a module."""
    endpoints: list[Endpoint] = []
    seen: set[str] = set()

    for ctrl in module.controllers:
        if ctrl.is_abstract:
            continue
        for ep in ctrl.endpoints:
            if ep.go_method_name not in seen:
                endpoints.append(ep)
                seen.add(ep.go_method_name)

    return endpoints


# Type names that conflict with generated code in the same package
_RESERVED_TYPE_NAMES = {"Client", "NewClient"}


def _collect_model_items(module: Module) -> list[ModelItem]:
    """Collect all model items from a module's controllers."""
    items: list[ModelItem] = []
    seen: set[str] = set()

    for ctrl in module.controllers:
        if ctrl.model and ctrl.model.items:
            for item in ctrl.model.items:
                if item.go_name not in seen:
                    items.append(item)
                    seen.add(item.go_name)

    return items


def _safe_param_name(name: str) -> str:
    """Ensure a parameter name doesn't conflict with Go reserved words."""
    if name in _GO_RESERVED:
        return name + "Val"
    return name


def _endpoint_view(ep: Endpoint) -> EndpointView:
    """Convert an Endpoint to a template-friendly view."""
    required_params = [
        {"name": _safe_param_name(p.name)}
        for p in ep.parameters if p.required
    ]

    optional_params = [
        {"name": p.name, "default": p.default}
        for p in ep.parameters if not p.required
    ]

    all_params = [
        {
            "name": p.name,
            "required": p.required,
            "default": p.default,
        }
        for p in ep.parameters
    ]

    # Build path format: replace required params with %s
    path_fmt = ""
    if required_params:
        path_fmt = ep.url_path
        for _ in required_params:
            path_fmt += "/%s"

    # Determine primary HTTP method
    primary = ep.methods[-1] if len(ep.methods) > 1 else ep.methods[0]

    # POST endpoints typically accept a body
    has_body = primary == "POST"

    # Resolve typed item info
    item_type = ""
    item_json_key = ""
    crud_verb = ep.crud_verb
    if ep.model_item:
        go_name = ep.model_item.go_name
        if go_name in _RESERVED_TYPE_NAMES:
            go_name = go_name + "Config"
        item_type = go_name
        item_json_key = ep.item_json_key

    return EndpointView(
        go_method_name=ep.go_method_name,
        methods=ep.methods,
        url_path=ep.url_path,
        primary_method=primary,
        has_body=has_body,
        required_params=required_params,
        optional_params=optional_params,
        parameters=all_params,
        path_fmt=path_fmt,
        item_type=item_type,
        item_json_key=item_json_key,
        crud_verb=crud_verb,
    )


def _type_item_view(item: ModelItem) -> TypeItemView:
    """Convert a ModelItem to a template-friendly view."""
    seen_fields: set[str] = set()
    fields: list[TypeFieldView] = []
    for f in item.fields:
        go_name = f.go_name
        # Deduplicate field names within a struct
        if go_name in seen_fields:
            continue
        seen_fields.add(go_name)
        fields.append(TypeFieldView(
            go_name=go_name,
            json_name=f.json_name,
            omitempty=not f.required or f.volatile,
            options=f.options,
        ))

    go_name = item.go_name
    # Avoid conflicts with the Client type in the same package
    if go_name in _RESERVED_TYPE_NAMES:
        go_name = go_name + "Config"

    return TypeItemView(name=item.name, go_name=go_name, fields=fields)


def _collect_response_wrappers(ep_views: list[EndpointView]) -> list[dict[str, str]]:
    """Collect unique response wrapper types needed for typed get_* endpoints."""
    seen: set[str] = set()
    wrappers: list[dict[str, str]] = []
    for ev in ep_views:
        if ev.crud_verb == "get" and ev.item_type and ev.item_json_key:
            key = ev.item_json_key
            if key not in seen:
                seen.add(key)
                wrappers.append({
                    "wrapper_name": key + "GetItemResponse",
                    "field_name": ev.item_type,
                    "json_key": key,
                })
    return wrappers


def _module_field_name(module_name: str) -> str:
    """Convert module name to Go struct field name for API struct."""
    name = module_name.replace("_", " ").title().replace(" ", "")
    return name


def _emit_module(
    env: Environment,
    pkg_dir: Path,
    pkg: str,
    module_name: str,
    endpoints: list[EndpointView],
    needs_fmt: bool,
    has_typed: bool,
) -> None:
    """Emit the main module Go file."""
    template = env.get_template("module.go.j2")
    content = template.render(
        package_name=pkg,
        module_name=module_name,
        endpoints=endpoints,
        needs_fmt=needs_fmt,
        has_typed=has_typed,
    )
    (pkg_dir / f"{pkg}.go").write_text(content, encoding="utf-8")


def _emit_types(
    env: Environment,
    pkg_dir: Path,
    pkg: str,
    items: list[TypeItemView],
    wrappers: list[dict[str, str]] | None = None,
) -> None:
    """Emit the types Go file."""
    template = env.get_template("types.go.j2")
    content = template.render(
        package_name=pkg,
        items=items,
        wrappers=wrappers or [],
    )
    (pkg_dir / "types.go").write_text(content, encoding="utf-8")


def _emit_api(
    env: Environment,
    out_dir: Path,
    modules: list[ModuleView],
) -> None:
    """Emit the api.go file in the opnsense/api/ sub-package."""
    api_dir = out_dir / "api"
    api_dir.mkdir(parents=True, exist_ok=True)
    template = env.get_template("api.go.j2")
    content = template.render(modules=sorted(modules, key=lambda m: m.package_name))
    (api_dir / "api.go").write_text(content, encoding="utf-8")

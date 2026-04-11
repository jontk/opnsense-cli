"""Emit Terraform provider Go source files from the parsed IR."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from generate.model.ir import APISpec, Endpoint, ModelField, ModelItem, Module
from generate.parser.name_transform import module_to_package

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

# Go reserved words — package names must avoid these
_GO_RESERVED = {
    "break", "case", "chan", "const", "continue", "default", "defer", "else",
    "fallthrough", "for", "func", "go", "goto", "if", "import", "interface",
    "map", "package", "range", "return", "select", "struct", "switch", "type",
    "var",
}

# Go type names that conflict with generated code — must be renamed
_RESERVED_TYPE_NAMES = {"Client", "NewClient"}

# Commands that start with a CRUD prefix but are NOT CRUD operations
_NO_UNDERSCORE_CRUD_BLACKLIST = frozenset({"delete", "deletekeytab"})

# Field names that always carry credential/secret material.
_SENSITIVE_EXACT_NAMES: frozenset[str] = frozenset({
    "password", "psk", "secret", "privkey",
    "privatekey", "privateKey", "tunnel_password",
    # Caddy basicauth password (distinct from 'basicauthuser' which is not sensitive)
    "basicauthpass",
    # Net-SNMP user encryption key (8-64 char passphrase used to derive AES/DES keys)
    "enckey",
})

# Field-name suffixes that indicate credential material.
_SENSITIVE_SUFFIXES: tuple[str, ...] = (
    "_password", "_psk", "_secret", "_privkey",
)

# Fields literally named "key" or "Key" that are NOT credentials.
# Matched against item.name (the XML container element name).
_NON_SENSITIVE_KEY_CONTEXTS: frozenset[str] = frozenset({
    "alias",           # zabbixagent: metric alias key (identifier, not a secret)
    "userparameter",   # zabbixagent: user-parameter key (identifier, not a secret)
})


def _is_sensitive_field(item_name: str, field_name: str) -> bool:
    """Return True if the field carries sensitive/secret material."""
    fl = field_name.lower()
    if fl in _SENSITIVE_EXACT_NAMES:
        return True
    for suffix in _SENSITIVE_SUFFIXES:
        if fl.endswith(suffix):
            return True
    # "key" / "Key" is a credential unless the item is a known non-secret context.
    if fl == "key" and item_name.lower() not in _NON_SENSITIVE_KEY_CONTEXTS:
        return True
    return False


# Corrections for known-invalid defaults in source XML model files.
# The docs/models directory is auto-generated (gitignored) and the upstream
# XML occasionally has defaults that do not satisfy the field's own validators.
# Each entry maps (item_name, field_name) -> corrected_default_value.
# These corrections are applied before the fail-fast validator runs.
_DEFAULT_CORRECTIONS: dict[tuple[str, str], str] = {
    # Firewall/Alias.xml: upstream default "alert" is not a valid alias type.
    ("alias", "type"): "host",
    # Syslog/Syslog.xml: "udp" was renamed to "udp4" when IPv6 support was added.
    ("destination", "transport"): "udp4",
    # DynDNS/DynDNS.xml: "web_dyndns" option was removed from the upstream list.
    ("account", "checkip"): "web_icanhazip",
    # Freeradius/Proxy.xml: default "1" is a numeric placeholder; "auth" is correct.
    ("homeserver", "type"): "auth",
    # HAProxy/HAProxy.xml: default "503" uses numeric code; tag-name form is "x503".
    ("errorfile", "code"): "x503",
}


@dataclass
class TFFieldView:
    """Template-friendly view of a Terraform resource attribute."""
    tf_name: str          # Terraform attribute name (snake_case)
    go_name: str          # Go struct field name (PascalCase)
    go_type: str          # "string", "opnsense.OPNBool", etc. (from IR)
    tf_schema_type: str   # "String", "Bool", "Int64"
    tf_go_type: str       # "types.String", "types.Bool", "types.Int64"
    required: bool
    optional: bool
    computed: bool
    sensitive: bool
    omitempty: bool       # Whether SDK struct uses omitempty
    is_pointer: bool      # Whether SDK struct field is a pointer type
    default_value: str | None
    options: list[str]
    volatile: bool        # Server-computed read-only field


@dataclass
class TFReconfigureView:
    """Info about the reconfigure/apply endpoint for a resource."""
    go_method: str        # SDK method name (e.g., "AliasReconfigure")
    has_body: bool        # Whether the method takes a body arg


@dataclass
class TFResourceView:
    """Template-friendly view of a complete Terraform resource."""
    tf_type_name: str     # e.g., "firewall_alias"
    go_struct_name: str   # e.g., "FirewallAlias"
    module_name: str      # e.g., "firewall"
    package_name: str     # SDK package name (e.g., "firewall")
    sdk_import: str       # Full import path
    item_type: str        # SDK struct type (e.g., "Alias")
    item_json_key: str    # JSON wrapper key (e.g., "alias")
    fields: list[TFFieldView]
    add_method: str       # SDK method for create (e.g., "AliasAddItem")
    get_method: str       # SDK method for read (e.g., "AliasGetItem")
    set_method: str       # SDK method for update (e.g., "AliasSetItem")
    del_method: str       # SDK method for delete (e.g., "AliasDelItem")
    get_has_opts: bool    # Whether get method has variadic opts (UUID is optional)
    set_has_required_id: bool  # Whether set method has required UUID param
    del_has_required_id: bool  # Whether del method has required UUID param
    reconfigure: TFReconfigureView | None

    @property
    def has_string_validators(self) -> bool:
        return any(f.options and f.tf_schema_type == "String" for f in self.fields)

    @property
    def has_bool_defaults(self) -> bool:
        return any(f.default_value is not None and f.tf_schema_type == "Bool" for f in self.fields)

    @property
    def has_int64_defaults(self) -> bool:
        return any(f.default_value is not None and f.tf_schema_type == "Int64" for f in self.fields)

    @property
    def has_string_defaults(self) -> bool:
        return any(f.default_value is not None and f.tf_schema_type == "String" for f in self.fields)


@dataclass
class TFDataSourceView:
    """Template-friendly view of a Terraform data source."""
    tf_type_name: str
    go_struct_name: str
    module_name: str
    package_name: str
    sdk_import: str
    item_type: str
    fields: list[TFFieldView]
    get_method: str
    get_has_opts: bool


def emit_terraform(spec: APISpec, output_dir: str | Path) -> None:
    """Emit all Terraform provider Go source files from the API spec."""
    out = Path(output_dir)
    res_dir = out / "resources"
    ds_dir = out / "datasources"
    res_dir.mkdir(parents=True, exist_ok=True)
    ds_dir.mkdir(parents=True, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    all_resources: list[TFResourceView] = []
    all_datasources: list[TFDataSourceView] = []
    seen_packages: set[str] = set()

    for module in spec.modules:
        pkg = module_to_package(module.name)
        if pkg in _GO_RESERVED:
            pkg += "api"

        # Handle duplicate package names
        actual_pkg = pkg
        if pkg in seen_packages:
            actual_pkg = module.category + pkg
        seen_packages.add(actual_pkg)

        sdk_import = f"github.com/jontk/opnsense-cli/opnsense/{actual_pkg}"

        resources = _collect_tf_resources(module, actual_pkg, sdk_import)
        all_resources.extend(resources)

        # Generate data sources for each resource
        for res in resources:
            ds = _resource_to_datasource(res)
            all_datasources.append(ds)

    # Emit resource files
    res_template = env.get_template("tf_resource.go.j2")
    for res in all_resources:
        content = res_template.render(r=res)
        filename = f"{res.tf_type_name}_resource.go"
        (res_dir / filename).write_text(content, encoding="utf-8")

    # Emit data source files
    ds_template = env.get_template("tf_datasource.go.j2")
    for ds in all_datasources:
        content = ds_template.render(d=ds)
        filename = f"{ds.tf_type_name}_data_source.go"
        (ds_dir / filename).write_text(content, encoding="utf-8")

    # Emit register.go
    reg_template = env.get_template("tf_register.go.j2")
    content = reg_template.render(
        resources=sorted(all_resources, key=lambda r: r.tf_type_name),
        datasources=sorted(all_datasources, key=lambda d: d.tf_type_name),
    )
    (out / "register.go").write_text(content, encoding="utf-8")

    print(f"  Generated {len(all_resources)} resources, {len(all_datasources)} data sources")


def _collect_tf_resources(
    module: Module, pkg: str, sdk_import: str,
) -> list[TFResourceView]:
    """Collect Terraform-eligible resources from a module.

    A resource is eligible if it has at least add + get + del endpoints
    with a linked ModelItem.
    """
    # Group endpoints by resource (reuse cli_emitter logic)
    resource_eps: dict[str, list[Endpoint]] = {}

    for ctrl in module.controllers:
        if ctrl.is_abstract:
            continue
        seen_methods: set[str] = set()
        for ep in ctrl.endpoints:
            if ep.go_method_name in seen_methods:
                continue
            seen_methods.add(ep.go_method_name)
            if not ep.crud_verb or not ep.model_item:
                continue
            res_name = _resource_name_from_endpoint(ep)
            resource_eps.setdefault(res_name, []).append(ep)

    # Collect reconfigure/apply endpoints from all controllers
    reconf_by_controller: dict[str, Endpoint] = {}
    service_reconf: Endpoint | None = None
    for ctrl in module.controllers:
        if ctrl.is_abstract:
            continue
        for ep in ctrl.endpoints:
            if ep.command in ("reconfigure", "apply"):
                reconf_by_controller[ep.controller] = ep
                if ep.controller == "service":
                    service_reconf = ep

    resources: list[TFResourceView] = []

    for res_name, eps in resource_eps.items():
        # Find CRUD endpoints
        add_ep = _find_crud_ep(eps, "add")
        get_ep = _find_crud_ep(eps, "get")
        del_ep = _find_crud_ep(eps, "del")
        set_ep = _find_crud_ep(eps, "set")

        # Must have at least add + get + del
        if not add_ep or not get_ep or not del_ep:
            continue

        # Use the add endpoint's model_item for the type info
        model_item = add_ep.model_item
        if not model_item:
            continue

        item_type = _safe_go_name(model_item.go_name)

        # Build field views (excluding fields that would conflict with "id")
        fields = _build_field_views(model_item)
        if not fields:
            continue

        # Find reconfigure endpoint
        reconf: TFReconfigureView | None = None
        controller_name = add_ep.controller
        if controller_name in reconf_by_controller:
            ep = reconf_by_controller[controller_name]
            primary = ep.methods[-1] if len(ep.methods) > 1 else ep.methods[0]
            reconf = TFReconfigureView(
                go_method=ep.go_method_name,
                has_body=primary == "POST",
            )
        elif service_reconf:
            primary = service_reconf.methods[-1] if len(service_reconf.methods) > 1 else service_reconf.methods[0]
            reconf = TFReconfigureView(
                go_method=service_reconf.go_method_name,
                has_body=primary == "POST",
            )

        # Build TF type name: module_resource (e.g., firewall_alias)
        tf_type_name = f"{module.name}_{res_name}".replace("-", "_")
        go_struct_name = _to_pascal(tf_type_name)

        # Check if get has optional params (for passing UUID)
        get_has_opts = any(not p.required for p in get_ep.parameters)

        # Check if set/del methods have required UUID param
        # If they have required params, signature is (ctx, uuid, body/...)
        # If only optional params, signature is (ctx, body, opts...) or (ctx, opts...)
        set_has_required_id = bool(set_ep and any(p.required for p in set_ep.parameters))
        del_has_required_id = any(p.required for p in del_ep.parameters)

        resources.append(TFResourceView(
            tf_type_name=tf_type_name,
            go_struct_name=go_struct_name,
            module_name=module.name,
            package_name=pkg,
            sdk_import=sdk_import,
            item_type=item_type,
            item_json_key=add_ep.item_json_key,
            fields=fields,
            add_method=add_ep.go_method_name,
            get_method=get_ep.go_method_name,
            set_method=set_ep.go_method_name if set_ep else "",
            del_method=del_ep.go_method_name,
            get_has_opts=get_has_opts,
            set_has_required_id=set_has_required_id,
            del_has_required_id=del_has_required_id,
            reconfigure=reconf,
        ))

    return resources


def _resource_to_datasource(res: TFResourceView) -> TFDataSourceView:
    """Convert a TFResourceView to a TFDataSourceView."""
    return TFDataSourceView(
        tf_type_name=res.tf_type_name,
        go_struct_name=res.go_struct_name,
        module_name=res.module_name,
        package_name=res.package_name,
        sdk_import=res.sdk_import,
        item_type=res.item_type,
        fields=res.fields,
        get_method=res.get_method,
        get_has_opts=res.get_has_opts,
    )


def _resource_name_from_endpoint(ep: Endpoint) -> str:
    """Derive the resource name from an endpoint."""
    cmd = ep.command
    if re.match(r'^(add|get|set|del|search|toggle)_item$', cmd):
        return ep.controller.lower().replace("_", "-")
    m = re.match(r'^(add|get|set|del|search|toggle)_(.+)$', cmd)
    if m:
        return _normalize_kebab(m.group(2))
    if cmd not in _NO_UNDERSCORE_CRUD_BLACKLIST:
        m = re.match(r'^(add|get|set|del|search|toggle)([a-z].+)$', cmd)
        if m:
            return _normalize_kebab(m.group(2))
    return ep.controller.lower().replace("_", "-")


def _normalize_kebab(raw: str) -> str:
    """Apply acronym grouping and return kebab-case."""
    from generate.parser.name_transform import _group_single_chars
    parts = raw.split("_")
    grouped = _group_single_chars(parts)
    return "-".join(p.lower() for p in grouped if p)


def _find_crud_ep(eps: list[Endpoint], verb: str) -> Endpoint | None:
    """Find the best endpoint for a given CRUD verb."""
    typed = [ep for ep in eps if ep.crud_verb == verb and ep.model_item]
    if typed:
        return typed[0]
    untyped = [ep for ep in eps if ep.crud_verb == verb]
    return untyped[0] if untyped else None


def _build_field_views(item: ModelItem) -> list[TFFieldView]:
    """Build TFFieldView list from a ModelItem's fields."""
    views: list[TFFieldView] = []
    seen: set[str] = set()

    for f in item.fields:
        if f.go_name in seen:
            continue
        seen.add(f.go_name)

        # Compute tf_name and skip if it would conflict with the "id" attribute
        tf_name = f.json_name.replace("-", "_")
        if tf_name == "id":
            continue

        is_volatile = f.volatile
        tf_schema_type, tf_go_type = _map_field_type(f)

        omitempty = not f.required or f.volatile
        is_pointer = omitempty and f.go_type != "string"

        required = f.required and not f.volatile
        optional = not f.required and not f.volatile
        computed = f.volatile or (not f.required)

        default_value = f.default if required and f.default else None

        # Apply known corrections for defaults that are wrong in the upstream XML.
        if default_value is not None:
            corrected = _DEFAULT_CORRECTIONS.get((item.name, f.name))
            if corrected is not None:
                default_value = corrected

        # Fail fast: a default that is not in the options list will produce a
        # Terraform schema that always fails validation at plan time.
        # Multiple-valued fields accept comma-separated lists; skip single-value
        # validation for those — the individual tokens may each be valid.
        if default_value is not None and f.options and not f.multiple:
            if default_value not in f.options:
                raise ValueError(
                    f"Field '{item.name}.{f.name}': default value {default_value!r} "
                    f"is not in options {f.options!r}. "
                    f"Fix the default or the options in the XML source metadata."
                )

        views.append(TFFieldView(
            tf_name=tf_name,
            go_name=f.go_name,
            go_type=f.go_type,
            tf_schema_type=tf_schema_type,
            tf_go_type=tf_go_type,
            required=required,
            optional=optional,
            computed=computed,
            sensitive=_is_sensitive_field(item.name, f.name),
            omitempty=omitempty,
            is_pointer=is_pointer,
            default_value=default_value,
            options=f.options,
            volatile=is_volatile,
        ))

    return views


def _map_field_type(f: ModelField) -> tuple[str, str]:
    """Map IR field type to (TF schema type, TF Go type)."""
    if f.go_type == "opnsense.OPNBool":
        return "Bool", "types.Bool"
    elif f.go_type == "opnsense.OPNInt":
        return "Int64", "types.Int64"
    else:
        return "String", "types.String"


def _safe_go_name(name: str) -> str:
    """Rename reserved type names to avoid conflicts."""
    if name in _RESERVED_TYPE_NAMES:
        return name + "Config"
    return name


def _to_pascal(name: str) -> str:
    """Convert snake_case/kebab-case to PascalCase."""
    return name.replace("-", " ").replace("_", " ").title().replace(" ", "")

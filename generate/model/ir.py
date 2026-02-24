"""Intermediate representation dataclasses for the OPNsense API spec."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Parameter:
    name: str
    required: bool = True
    default: str | None = None


@dataclass
class Endpoint:
    methods: list[str]
    module: str
    controller: str
    command: str  # snake_case from docs
    command_camel: str  # camelCase for URL path
    url_path: str  # /api/{module}/{controller}/{command_camel}
    go_method_name: str  # PascalCase for Go method
    parameters: list[Parameter] = field(default_factory=list)
    crud_verb: str = ""  # "add", "get", "set", "del", "search", "toggle", or ""
    model_item: ModelItem | None = None  # linked ModelItem for typed CRUD
    item_json_key: str = ""  # JSON wrapper key (e.g., "alias")


@dataclass
class ModelField:
    name: str
    field_type: str
    go_name: str
    json_name: str
    required: bool = False
    default: str | None = None
    volatile: bool = False
    multiple: bool = False
    options: list[str] = field(default_factory=list)


@dataclass
class ModelItem:
    name: str  # XML element name (e.g. "alias")
    go_name: str  # PascalCase (e.g. "Alias")
    container_name: str  # parent container (e.g. "aliases")
    fields: list[ModelField] = field(default_factory=list)


@dataclass
class Model:
    mount: str  # e.g. "OPNsense.Firewall.Alias"
    xml_url: str
    items: list[ModelItem] = field(default_factory=list)
    version: str = ""


@dataclass
class Controller:
    name: str  # e.g. "AliasController"
    php_file: str  # e.g. "AliasController.php"
    base_class: str = ""  # e.g. "ApiMutableModelControllerBase"
    is_abstract: bool = False
    endpoints: list[Endpoint] = field(default_factory=list)
    model: Model | None = None
    model_url: str = ""  # raw GitHub XML URL


@dataclass
class Module:
    name: str  # e.g. "firewall"
    category: str  # "core", "plugins", or "be"
    controllers: list[Controller] = field(default_factory=list)


@dataclass
class APISpec:
    modules: list[Module] = field(default_factory=list)
    models: dict[str, Model] = field(default_factory=dict)  # keyed by XML URL

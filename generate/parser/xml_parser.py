"""Parse OPNsense XML model files into IR Model objects."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from generate.model.ir import Model, ModelField, ModelItem
from generate.parser.name_transform import field_to_go_name, snake_to_pascal

# XML field type tags that represent leaf fields (not containers)
_LEAF_FIELD_TYPES = {
    "BooleanField",
    "TextField",
    "DescriptionField",
    "IntegerField",
    "NumericField",
    "OptionField",
    "NetworkField",
    "PortField",
    "CSVListField",
    "ModelRelationField",
    "InterfaceField",
    "HostnameField",
    "UrlField",
    "EmailField",
    "CertificateField",
    "AuthGroupField",
    "AuthenticationServerField",
    "ConfigdActionsField",
    "CountryField",
    "LegacyLinkField",
    "JsonKeyValueStoreField",
    "UniqueIdField",
    "UpdateOnlyTextField",
    "Base64Field",
    "VirtualIPField",
}

# Field types that indicate array containers
_CONTAINER_TYPES = {"ArrayField", "ContainerField"}


def parse_all(models_dir: str | Path) -> dict[str, Model]:
    """Parse all XML models under models_dir. Returns dict keyed by XML URL pattern."""
    models_path = Path(models_dir)
    models: dict[str, Model] = {}

    if not models_path.exists():
        return models

    for xml_file in sorted(models_path.rglob("*.xml")):
        model = parse_model(xml_file)
        if model:
            # Key by the relative path after OPNsense/
            rel = xml_file.relative_to(models_path)
            models[str(rel)] = model

    return models


def parse_model(xml_file: Path) -> Model | None:
    """Parse a single XML model file into a Model object."""
    try:
        tree = ET.parse(xml_file)
    except ET.ParseError:
        return None

    root = tree.getroot()

    # Extract mount point
    mount_elem = root.find(".//mount")
    mount = mount_elem.text.strip() if mount_elem is not None and mount_elem.text else ""

    # Extract version
    version_elem = root.find(".//version")
    version = version_elem.text.strip() if version_elem is not None and version_elem.text else ""

    # Build URL from file path
    xml_url = str(xml_file)

    # Find items container
    items_elem = root.find(".//items")
    items: list[ModelItem] = []

    if items_elem is not None:
        items = _parse_items(items_elem)

    return Model(
        mount=mount,
        xml_url=xml_url,
        items=items,
        version=version,
    )


def _parse_items(items_elem: ET.Element) -> list[ModelItem]:
    """Parse the <items> element, extracting ModelItems from ArrayField containers."""
    items: list[ModelItem] = []
    found_flat_settings = False

    for container in items_elem:
        container_tag = container.tag  # e.g. "aliases"
        container_type = container.attrib.get("type", "")

        if container_type in _CONTAINER_TYPES or _has_array_children(container):
            # This is a container (e.g. <aliases type="ArrayField">)
            # Look for child elements that are the actual item templates
            found_nested = False
            for item_elem in container:
                if item_elem.tag in ("type", "style"):
                    continue
                item = _parse_item(item_elem, container_tag)
                if item and item.fields:
                    items.append(item)
                    found_nested = True

            # If no nested item templates found, this is a "flat array" where
            # the ArrayField container directly holds the fields (e.g. Bridge.xml)
            if not found_nested:
                item = _parse_flat_array(container)
                if item and item.fields:
                    items.append(item)
        elif _is_item_template(container):
            # Item template directly under <items> (e.g. <gateway_item type=".\GatewayField">)
            item = _parse_flat_array(container)
            if item and item.fields:
                items.append(item)
        elif not found_flat_settings:
            # Direct fields under items (non-array model)
            item = _parse_item_direct(container, items_elem)
            if item and item.fields:
                items.append(item)
                found_flat_settings = True  # Only one flat settings item

    return items


def _has_array_children(elem: ET.Element) -> bool:
    """Check if an element has children that look like model item templates."""
    for child in elem:
        if child.tag in ("type", "style"):
            continue
        # If a child has children that have 'type' attributes matching field types,
        # this is likely an array container
        for grandchild in child:
            gc_type = grandchild.attrib.get("type", "")
            if gc_type in _LEAF_FIELD_TYPES or grandchild.tag in _LEAF_FIELD_TYPES:
                return True
    return False


def _is_item_template(elem: ET.Element) -> bool:
    """Check if an element is an item template (has direct children with field types).

    Distinguishes e.g. <gateway_item type=".\\GatewayField"> (item template with field children)
    from <enable type="BooleanField"> (a leaf field with metadata children like Required/Default).
    """
    for child in elem:
        child_type = child.attrib.get("type", "")
        if child_type in _LEAF_FIELD_TYPES:
            return True
        if child_type.endswith("Field") and child_type not in _CONTAINER_TYPES:
            return True
    return False


def _item_go_name(name: str) -> str:
    """Compute a Go type name from an XML item name, handling hyphens and underscores."""
    normalized = name.replace("-", "_")
    if "_" in normalized:
        return snake_to_pascal(normalized)
    return normalized[0].upper() + normalized[1:] if normalized else normalized


def _parse_item(item_elem: ET.Element, container_name: str) -> ModelItem | None:
    """Parse a single item template element into a ModelItem."""
    item_name = item_elem.tag
    fields: list[ModelField] = []

    for field_elem in item_elem:
        field = _parse_field(field_elem)
        if field:
            fields.append(field)

    if not fields:
        return None

    return ModelItem(
        name=item_name,
        go_name=_item_go_name(item_name),
        container_name=container_name,
        fields=fields,
    )


def _parse_flat_array(container: ET.Element) -> ModelItem | None:
    """Parse a flat ArrayField where fields are directly inside the container.

    Example: <bridged type="ArrayField"><bridgeif type="TextField">...</bridgeif>...</bridged>
    The container tag becomes the item name.
    """
    fields: list[ModelField] = []

    for field_elem in container:
        field = _parse_field(field_elem)
        if field:
            fields.append(field)

    if not fields:
        return None

    item_name = container.tag
    return ModelItem(
        name=item_name,
        go_name=_item_go_name(item_name),
        container_name=item_name,
        fields=fields,
    )


def _parse_item_direct(first_child: ET.Element, items_elem: ET.Element) -> ModelItem | None:
    """Parse a flat model (no array containers) into a single ModelItem."""
    fields: list[ModelField] = []

    for field_elem in items_elem:
        field = _parse_field(field_elem)
        if field:
            fields.append(field)

    if not fields:
        return None

    return ModelItem(
        name="settings",
        go_name="Settings",
        container_name="",
        fields=fields,
    )


def _parse_field(field_elem: ET.Element) -> ModelField | None:
    """Parse a single field element into a ModelField."""
    field_type = field_elem.attrib.get("type", field_elem.tag)

    # Skip container/non-leaf types
    if field_type in _CONTAINER_TYPES:
        return None
    if field_type not in _LEAF_FIELD_TYPES and not _looks_like_field(field_elem):
        return None

    name = field_elem.tag

    # Extract field properties
    required = False
    default = None
    volatile = False
    multiple = False
    options: list[str] = []

    req_elem = field_elem.find("Required")
    if req_elem is not None and req_elem.text:
        required = req_elem.text.strip().upper() in ("Y", "YES", "1", "TRUE")

    default_elem = field_elem.find("Default")
    if default_elem is not None and default_elem.text:
        default = default_elem.text.strip()

    volatile_str = field_elem.attrib.get("volatile", "false")
    volatile = volatile_str.lower() in ("true", "1")

    multiple_elem = field_elem.find("Multiple")
    if multiple_elem is not None and multiple_elem.text:
        multiple = multiple_elem.text.strip().upper() in ("Y", "YES", "1", "TRUE")

    # Extract option values
    option_values = field_elem.find("OptionValues")
    if option_values is not None:
        for opt in option_values:
            opt_val = opt.tag
            options.append(opt_val)

    go_type = _field_type_to_go(field_type)

    return ModelField(
        name=name,
        field_type=field_type,
        go_name=field_to_go_name(name),
        json_name=name,
        required=required,
        default=default,
        volatile=volatile,
        multiple=multiple,
        options=options,
        go_type=go_type,
    )


def _field_type_to_go(field_type: str) -> str:
    """Map an OPNsense XML field type to a Go type."""
    if field_type == "BooleanField":
        return "opnsense.OPNBool"
    if field_type == "IntegerField":
        return "opnsense.OPNInt"
    return "string"


def _looks_like_field(elem: ET.Element) -> bool:
    """Heuristic: does this element look like a leaf field?"""
    # If it has field-like children (Required, Default, etc.), it's likely a field
    field_children = {"Required", "Default", "ValidationMessage", "Constraints",
                      "Multiple", "OptionValues", "BlankDesc", "Label"}
    for child in elem:
        if child.tag in field_children:
            return True
    # If it has a 'type' attribute that ends in 'Field', treat it as a field
    type_attr = elem.attrib.get("type", "")
    if type_attr.endswith("Field"):
        return True
    return False


def match_model_to_url(models: dict[str, Model], github_url: str) -> Model | None:
    """Find a parsed model matching a GitHub XML URL."""
    if not github_url:
        return None

    # Extract the OPNsense/Module/File.xml part from the URL
    import re
    match = re.search(r"models/(OPNsense/.+\.xml)", github_url)
    if not match:
        return None

    rel_path = match.group(1)
    return models.get(rel_path)

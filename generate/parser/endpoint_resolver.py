"""Resolve CRUD endpoints to their matching ModelItem types."""

from __future__ import annotations

from generate.model.ir import ModelItem, Module

_CRUD_PREFIXES = ("add_", "set_", "get_", "del_", "search_", "toggle_")

# Manual overrides for cases where endpoint suffix and item name are unrelated.
# Key: (module_name, controller_name, suffix) → item_name
_MANUAL_OVERRIDES: dict[tuple[str, str, str], str] = {
    ("clamav", "url", "url"): "list",
    ("wol", "wol", "host"): "wolentry",
}


def resolve_endpoints(modules: list[Module]) -> None:
    """For each endpoint, determine its CRUD verb and matching ModelItem."""
    for module in modules:
        for ctrl in module.controllers:
            if not ctrl.model or not ctrl.model.items:
                continue
            for ep in ctrl.endpoints:
                verb, suffix = _parse_crud(ep.command)
                if not verb:
                    continue
                item = _match_item(
                    suffix, ep.controller, ctrl.model.items, module.name,
                )
                if item:
                    ep.crud_verb = verb
                    ep.model_item = item
                    ep.item_json_key = item.name


def _parse_crud(command: str) -> tuple[str, str]:
    """Parse a command like 'add_item' into ('add', 'item').

    Returns ('', '') if the command doesn't match a CRUD pattern.
    """
    for prefix in _CRUD_PREFIXES:
        if command.startswith(prefix):
            verb = prefix.rstrip("_")
            suffix = command[len(prefix):]
            if suffix:
                return verb, suffix
    return "", ""


def _normalize(name: str) -> str:
    """Normalize a name for comparison: lowercase, strip underscores."""
    return name.lower().replace("_", "")


def _match_item(
    suffix: str,
    controller: str,
    items: list[ModelItem],
    module_name: str = "",
) -> ModelItem | None:
    """Match a CRUD suffix to a ModelItem.

    Matching strategy (in priority order):
    0. Manual override map (for unrelated names like url→list)
    1. If suffix == "item", look for item with name matching controller
    2. Exact match: item.name == suffix
    3. Container match: item.container_name == suffix
    4. Normalized match: compare with underscores/case stripped
    5. Plural match: suffix + "s" == item.name or container_name
    6. Compound suffix strategies (last word, first word)
    7. Startswith match: item name starts with suffix (e.g., dest→destinations)
    8. Return None (stay untyped)
    """
    suffix_lower = suffix.lower()
    suffix_norm = _normalize(suffix)

    # Check manual override map first
    override_key = (module_name, controller, suffix_lower)
    if override_key in _MANUAL_OVERRIDES:
        target = _MANUAL_OVERRIDES[override_key]
        for item in items:
            if item.name.lower() == target:
                return item

    if suffix_lower == "item":
        return _match_item_suffix(controller, items)

    # Try matching suffix directly against item names
    for item in items:
        if item.name.lower() == suffix_lower:
            return item

    # Try matching suffix against container names
    for item in items:
        if item.container_name.lower() == suffix_lower:
            return item

    # Try normalized match (strips underscores + lowercase)
    for item in items:
        if _normalize(item.name) == suffix_norm:
            return item
    for item in items:
        if _normalize(item.container_name) == suffix_norm:
            return item

    # Try simple plural forms (e.g., relay → relays, entry → entries)
    plurals = [suffix_lower + "s"]
    if suffix_lower.endswith("y"):
        plurals.append(suffix_lower[:-1] + "ies")
    for plural in plurals:
        for item in items:
            if item.name.lower() == plural:
                return item
        for item in items:
            if item.container_name.lower() == plural:
                return item

    # Try suffix + "ing" (e.g., forward → forwarding)
    for item in items:
        if item.name.lower() == suffix_lower + "ing":
            return item

    # Try item name ends with suffix or its plurals (e.g., boot → dhcp_boot, tag → dhcp_tags)
    endswith_candidates = [suffix_norm]
    endswith_candidates.extend(_normalize(p) for p in plurals)
    for candidate in endswith_candidates:
        for item in items:
            name_norm = _normalize(item.name)
            if len(name_norm) > len(candidate) and name_norm.endswith(candidate):
                return item
        for item in items:
            container_norm = _normalize(item.container_name)
            if len(container_norm) > len(candidate) and container_norm.endswith(candidate):
                return item

    # Try stripping trailing "_item" from item names (e.g., gateway → gateway_item)
    for item in items:
        item_stripped = item.name.lower().removesuffix("_item")
        if item_stripped != item.name.lower() and item_stripped == suffix_lower:
            return item

    # For compound suffixes (containing underscores), try additional strategies
    if "_" in suffix:
        parts = suffix_lower.split("_")

        # Try concatenated (e.g., layer4_openvpn → layer4openvpn)
        concatenated = "".join(parts)
        for item in items:
            if _normalize(item.name) == concatenated:
                return item

        # Try last word (e.g., host_alias → alias)
        last = parts[-1]
        for item in items:
            if item.name.lower() == last:
                return item

        # Try first word (e.g., reverse_proxy → reverse)
        first = parts[0]
        for item in items:
            if item.name.lower() == first:
                return item

    # Try startswith: item name starts with suffix (e.g., dest → destinations,
    # domain → domainoverrides). Require suffix >= 3 chars to avoid false matches.
    if len(suffix_norm) >= 3:
        for item in items:
            name_norm = _normalize(item.name)
            if len(name_norm) > len(suffix_norm) and name_norm.startswith(suffix_norm):
                return item
        for item in items:
            container_norm = _normalize(item.container_name)
            if len(container_norm) > len(suffix_norm) and container_norm.startswith(suffix_norm):
                return item

    return None


def _match_item_suffix(controller: str, items: list[ModelItem]) -> ModelItem | None:
    """Match for the generic 'item' suffix using controller name."""
    controller_lower = controller.lower()
    controller_norm = _normalize(controller)

    # Exact match
    for item in items:
        if item.name.lower() == controller_lower:
            return item

    # Normalized match (key_pairs → keypairs vs keyPair → keypair)
    for item in items:
        if _normalize(item.name) == controller_norm:
            return item

    # Try matching against container names
    for item in items:
        if _normalize(item.container_name) == controller_norm:
            return item

    # Try startswith: item name starts with controller (e.g., tls → tlsConfig)
    if len(controller_norm) >= 3:
        for item in items:
            name_norm = _normalize(item.name)
            if len(name_norm) > len(controller_norm) and name_norm.startswith(controller_norm):
                return item

    # If only one item exists, use it as fallback
    if len(items) == 1:
        return items[0]

    return None

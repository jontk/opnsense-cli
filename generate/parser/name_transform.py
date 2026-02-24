"""Name transformation utilities for converting between naming conventions."""

from __future__ import annotations

# Words that should always be uppercased as acronyms in Go
_KNOWN_ACRONYMS = {
    "uuid", "url", "uri", "api", "ip", "tcp", "udp", "dns", "http", "https",
    "tls", "ssl", "ssh", "cpu", "ram", "os", "id", "io", "xml", "json",
    "html", "css", "php", "sql", "dhcp", "nat", "vpn", "vlan", "mac",
    "arp", "icmp", "igmp", "bgp", "ospf", "rip", "snmp", "ntp", "ldap",
    "acl", "ha", "qos",
}


def snake_to_camel(s: str) -> str:
    """Convert snake_case to camelCase, grouping single-char segments as acronyms.

    Examples:
        add_item -> addItem
        get_alias_u_u_i_d -> getAliasUUID
        get_c_p_u_type -> getCPUType
        getOptions -> getOptions  (no underscores, passthrough)
        _rolling -> rolling
    """
    if "_" not in s:
        return s

    # Strip leading underscores
    s = s.lstrip("_")

    parts = s.split("_")
    if not parts:
        return s

    # Group consecutive single-char segments into acronyms
    grouped = _group_single_chars(parts)

    # camelCase: first word lowercase, rest capitalized
    result = []
    for i, word in enumerate(grouped):
        if not word:
            continue
        if i == 0:
            result.append(word.lower())
        elif len(word) > 1 and word.upper() in _KNOWN_ACRONYMS:
            result.append(word.upper())
        elif word.isupper() and len(word) > 1:
            # Grouped acronym (e.g., "UUID" from "u_u_i_d")
            result.append(word.upper())
        else:
            result.append(word[0].upper() + word[1:])

    return "".join(result)


def snake_to_pascal(s: str) -> str:
    """Convert snake_case to PascalCase for Go type/method names.

    Examples:
        add_item -> AddItem
        get_alias_u_u_i_d -> GetAliasUUID
        _carp_status -> CarpStatus
    """
    if "_" not in s:
        return s[0].upper() + s[1:] if s else s

    # Strip leading underscores
    s = s.lstrip("_")

    parts = s.split("_")
    grouped = _group_single_chars(parts)

    result = []
    for word in grouped:
        if not word:
            continue
        if len(word) > 1 and word.upper() in _KNOWN_ACRONYMS:
            result.append(word.upper())
        elif word.isupper() and len(word) > 1:
            result.append(word.upper())
        else:
            result.append(word[0].upper() + word[1:])

    return "".join(result)


def _group_single_chars(parts: list[str]) -> list[str]:
    """Group consecutive single-character parts into acronyms.

    ['get', 'alias', 'u', 'u', 'i', 'd'] -> ['get', 'alias', 'UUID']
    ['get', 'c', 'p', 'u', 'type'] -> ['get', 'CPU', 'type']
    """
    grouped: list[str] = []
    i = 0
    while i < len(parts):
        if len(parts[i]) == 1:
            # Collect consecutive single chars
            acronym = []
            while i < len(parts) and len(parts[i]) == 1:
                acronym.append(parts[i].upper())
                i += 1
            grouped.append("".join(acronym))
        else:
            grouped.append(parts[i])
            i += 1
    return grouped


def controller_to_go_name(controller: str) -> str:
    """Convert a controller name to a Go-friendly name.

    alias_util -> AliasUtil
    d_nat -> DNat
    filter_base -> FilterBase
    """
    return snake_to_pascal(controller)


def module_to_package(module_name: str) -> str:
    """Convert module name to Go package name (lowercase, no underscores).

    firewall -> firewall
    opncentral -> opncentral
    """
    return module_name.lower().replace("_", "")


def field_to_go_name(name: str) -> str:
    """Convert an XML field name to a Go struct field name (PascalCase).

    enabled -> Enabled
    proto -> Proto
    updatefreq -> Updatefreq
    state-policy -> StatePolicy
    max-src-nodes -> MaxSrcNodes
    """
    # Normalize hyphens to underscores so snake_to_pascal handles them
    normalized = name.replace("-", "_")
    if "_" in normalized:
        return snake_to_pascal(normalized)
    return normalized[0].upper() + normalized[1:] if normalized else normalized


def go_method_name(controller: str, command: str) -> str:
    """Build a Go method name from controller + command.

    controller=alias, command=add_item -> AliasAddItem
    controller=alias_util, command=add -> AliasUtilAdd
    controller=service, command=reconfigure -> ServiceReconfigure
    """
    ctrl_part = controller_to_go_name(controller)
    cmd_part = snake_to_pascal(command)
    return ctrl_part + cmd_part

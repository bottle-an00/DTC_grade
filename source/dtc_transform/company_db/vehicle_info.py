import xml.etree.ElementTree as ET


def build_vehicle_info_index(xml_paths: list[str]) -> tuple[dict[str, str], dict[str, set[str]]]:
    """Collect every (ecucode -> sysitemdesc) pairing across all given
    files first, then resolve: a code seen with exactly one sysitemdesc is
    trustworthy, a code seen with more than one is a conflict to report
    rather than silently pick a winner for."""
    seen: dict[str, set[str]] = {}

    for path in xml_paths:
        tree = ET.parse(path)
        for sysitem in tree.getroot().iter("sysitem"):
            desc = sysitem.get("sysitemdesc", "")
            if not desc:
                continue
            for ecuid in sysitem.iter("ecuid"):
                code = ecuid.get("ecucode", "")
                if not code:
                    continue
                seen.setdefault(code, set()).add(desc)

    resolved = {code: next(iter(descs)) for code, descs in seen.items() if len(descs) == 1}
    conflicts = {code: descs for code, descs in seen.items() if len(descs) > 1}
    return resolved, conflicts

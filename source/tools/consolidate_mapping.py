import argparse
import csv
import json

from dtc_transform.sheet_key import normalize_sheet_key

# Which source to trust when two spellings of one controller disagree.
# "manual" was confirmed by a person. "auto" was derived from the shipped
# reference DB, so it reproduces what the tool already displays. The
# 3-way join behind "company_db" joins on a 4-character compare code that
# unrelated controllers share, so its values are the least verified and
# only fill keys the other two leave empty.
PRECEDENCE = {"manual": 0, "auto": 1, "company_db": 2}


def _rank(entry: dict) -> int:
    return PRECEDENCE.get(entry.get("source", "auto"), len(PRECEDENCE))


def consolidate(mapping: dict[str, dict]) -> tuple[dict[str, dict], list[dict]]:
    """Fold spelling variants of one controller onto a single normalized key.

    Returns the consolidated lookup plus the groups where the sources
    disagreed on the System value -- those are the entries a person still
    has to settle, so they are reported rather than buried.
    """
    groups: dict[str, list[tuple[str, dict]]] = {}
    for name, entry in mapping.items():
        key = normalize_sheet_key(name)
        if not key:
            continue
        groups.setdefault(key, []).append((name, entry))

    consolidated: dict[str, dict] = {}
    disagreements: list[dict] = []

    for key, members in groups.items():
        ordered = sorted(members, key=lambda m: (_rank(m[1]), m[0]))
        winner_name, winner = ordered[0]
        consolidated[key] = {
            "system": winner["system"],
            "source": winner.get("source", "auto"),
            "aliases": sorted(name for name, _ in members),
        }

        losers = [
            {"name": name, "source": entry.get("source", "auto"), "system": entry["system"]}
            for name, entry in ordered[1:]
            if entry["system"] != winner["system"]
        ]
        if losers:
            disagreements.append(
                {
                    "key": key,
                    "chosen": winner["system"],
                    "chosen_source": winner.get("source", "auto"),
                    "chosen_name": winner_name,
                    "rejected": losers,
                }
            )

    return consolidated, disagreements


def write_disagreement_csv(path: str, disagreements: list[dict]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["key", "chosen_name", "chosen_source", "chosen_system", "rejected"])
        for row in disagreements:
            rejected = ";".join(f"{r['name']}[{r['source']}]={r['system']}" for r in row["rejected"])
            writer.writerow([row["key"], row["chosen_name"], row["chosen_source"], row["chosen"], rejected])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fold spelling variants in sheet_system_mapping.json onto normalized keys"
    )
    parser.add_argument("--mapping", required=True, help="Path to config/sheet_system_mapping.json")
    parser.add_argument("--output", required=True, help="Path to write the consolidated normalized lookup")
    parser.add_argument("--disagreement-csv", required=True, help="Path to write the source-disagreement report")
    args = parser.parse_args()

    with open(args.mapping, encoding="utf-8") as f:
        mapping = json.load(f)

    consolidated, disagreements = consolidate(mapping)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(consolidated, f, ensure_ascii=False, indent=2, sort_keys=True)
    write_disagreement_csv(args.disagreement_csv, disagreements)

    print(
        f"entries={len(mapping)} consolidated={len(consolidated)} "
        f"disagreements={len(disagreements)} output={args.output}"
    )


if __name__ == "__main__":
    main()

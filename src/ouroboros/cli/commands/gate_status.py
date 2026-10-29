"""Read-only, local ambiguity-gate provenance summary (#2231)."""

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class GateSummary:
    """Unique recorded decisions, with unknown history kept out of the rate."""

    forced: int
    gated: int
    unknown: int
    unreadable: int

    def render(self) -> str:
        known = self.forced + self.gated
        rate = f"{100 * self.forced / known:.1f}%" if known else "unavailable"
        total = known + self.unknown
        coverage = f"{100 * known / total:.1f}%" if total else "unavailable"
        return (
            f"Unique Seed IDs: {total}\nRecorded-decision coverage: {coverage}\n"
            f"Forced: {self.forced}\nGated: {self.gated}\n"
            f"Unknown: {self.unknown}\nUnreadable files: {self.unreadable}\n"
            f"Override rate (recorded decisions only): {rate}\n"
        )


def summarize_gate_decisions(directory: Path) -> GateSummary:
    """Read flat local Seed files; never infer force from today's threshold.

    Copies with the same seed_id count once. Conflicting copies become unknown.
    Missing historical provenance remains unknown, not a successful gate check.
    No telemetry is sent and no Seed or configuration is changed.
    """
    decisions: dict[str, bool | None] = {}
    unreadable = 0
    for path in sorted(directory.iterdir()):
        if path.suffix.lower() not in {".json", ".yaml", ".yml"}:
            continue
        try:
            if path.is_symlink():
                raise ValueError("symlink is not a local Seed file")
            if not path.is_file():
                continue
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            metadata = data.get("metadata") if isinstance(data, dict) else None
            if not isinstance(metadata, dict):
                raise ValueError("not a Seed metadata record")
            seed_id = metadata.get("seed_id")
            if not isinstance(seed_id, str) or not seed_id.strip():
                raise ValueError("missing seed identity")
            value = metadata.get("gate_forced")
            decision = value if type(value) is bool else None
            if seed_id in decisions and decisions[seed_id] != decision:
                decisions[seed_id] = None
            else:
                decisions[seed_id] = decision
        except (OSError, UnicodeError, yaml.YAMLError, ValueError):
            unreadable += 1
    return GateSummary(
        forced=sum(value is True for value in decisions.values()),
        gated=sum(value is False for value in decisions.values()),
        unknown=sum(value is None for value in decisions.values()),
        unreadable=unreadable,
    )

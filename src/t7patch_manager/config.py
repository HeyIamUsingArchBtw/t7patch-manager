"""Parse and write ``t7patch.conf`` (a simple ``key=value`` INI-style file)."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT = {
    "playername": "Unknown Soldier",
    "isfriendsonly": "1",
    "networkpassword": "",
}


@dataclass
class T7Config:
    playername: str = "Unknown Soldier"
    isfriendsonly: bool = True
    networkpassword: str = ""
    _raw: dict[str, str] = field(default_factory=dict, repr=False)

    def to_text(self) -> str:
        # Preserve any unknown keys the user added by hand
        merged = dict(self._raw) if self._raw else dict(DEFAULT)
        merged["playername"] = self.playername
        merged["isfriendsonly"] = "1" if self.isfriendsonly else "0"
        merged["networkpassword"] = self.networkpassword
        lines = [f"{k}={merged[k]}" for k in merged]
        return "\n".join(lines) + "\n"


def read(path: Path) -> T7Config:
    if not path.is_file():
        return T7Config()
    raw: dict[str, str] = {}
    for line in path.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        raw[k.strip().lower()] = v.strip()
    return T7Config(
        playername=raw.get("playername", "Unknown Soldier"),
        isfriendsonly=raw.get("isfriendsonly", "1") == "1",
        networkpassword=raw.get("networkpassword", ""),
        _raw=raw,
    )


def write(path: Path, cfg: T7Config) -> None:
    path.write_text(cfg.to_text())

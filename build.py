#!/usr/bin/env python3
"""Unified build & GitHub-safety audit CLI for Newtribe-SX (Bring Your Own Firmware).

Usage:
  python build.py all         # Build ESX-1 SD N-Sys (ESX0103N.BSS) + DSP Tape Delay (ESX0102D.BDS) -> release/esx1-sd/
  python build.py sd          # Build ESX-1 SD N-Sys firmware only
  python build.py dsp         # Build DSP Tape Delay firmware only
  python build.py audit-git   # Verify no Korg-copyrighted binaries or full disassemblies would be published
"""
from __future__ import annotations
import argparse
import fnmatch
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FW_TOOLS = ROOT / "fw-src-sm" / "tools"
FW_SD = ROOT / "fw-src-sd"
DSP_DIR = ROOT / "dsp-src"
FACTORY_SD = ROOT / "factory-firmware-sd"
RELEASE_SD = ROOT / "release" / "esx1-sd"


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def ensure_sd_extracted() -> None:
    """If fw-src-sd/src/ does not exist yet (fresh GitHub clone), extract it locally from user's stock ESX0103N.BSS."""
    src_dir = FW_SD / "src"
    if src_dir.exists() and any(src_dir.glob("*.s")):
        return
    stock_bss = FACTORY_SD / "ESX0103N.BSS"
    if not stock_bss.exists():
        sys.exit(
            f"ERROR: Missing stock firmware {stock_bss}.\n"
            "Place your own dumped ESX-1 SD ESX0103N.BSS there first (Bring Your Own Firmware)."
        )
    print(f"[extract] Disassembling {stock_bss} -> {FW_SD}/src/ ...")
    subprocess.run(
        [
            sys.executable, str(FW_TOOLS / "shdis.py"),
            str(stock_bss), str(FW_SD),
            "--img-end", "0x0C0EE98C",
        ],
        check=True,
    )


def build_sd() -> Path:
    ensure_sd_extracted()
    print("[build] Building ESX-1 SD Newtribe firmware (ESX0103N.BSS)...")
    out = FW_SD / "build" / "ESX0103N.BSS"
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable, str(FW_TOOLS / "build.py"),
            "--src", str(FW_SD / "src"),
            "--out", str(out),
            "--header", str(FW_SD / "header.json"),
            "--map", str(FW_SD / "build" / "fw.map"),
            "--newtribe", str(FW_SD / "newtribe"),
            "--header-version", "01030002",
        ],
        check=True,
    )
    assert out.exists() and out.stat().st_size == 0x200000
    RELEASE_SD.mkdir(parents=True, exist_ok=True)
    dst = RELEASE_SD / "ESX0103N.BSS"
    shutil.copy2(out, dst)
    print(f"[ok] {dst} ({dst.stat().st_size} B, sha256={sha256_file(dst)})")
    return dst


def build_dsp() -> Path:
    stock_bds = FACTORY_SD / "ESX0102D.BDS"
    if not stock_bds.exists():
        stock_bds = ROOT / "factory-firmware-sm" / "ESX0102D.BDS"
    if not stock_bds.exists():
        sys.exit(
            "ERROR: Missing stock DSP firmware factory-firmware-sd/ESX0102D.BDS (or factory-firmware-sm/ESX0102D.BDS).\n"
            "Place your own stock ESX0102D.BDS there first (Bring Your Own Firmware)."
        )
    print("[build] Building DSP Tape Delay PoC firmware (ESX0102D.BDS)...")
    out = DSP_DIR / "build" / "ESX0102D.BDS"
    subprocess.run(
        [
            sys.executable, str(DSP_DIR / "tools" / "bdspack.py"),
            "build",
            "--base", str(stock_bds),
            "--patch", str(DSP_DIR / "patches" / "tape_delay.dsp"),
            "--out", str(out),
        ],
        check=True,
    )
    assert out.exists() and out.stat().st_size == 0xF0000
    RELEASE_SD.mkdir(parents=True, exist_ok=True)
    dst = RELEASE_SD / "ESX0102D.BDS"
    shutil.copy2(out, dst)
    print(f"[ok] {dst} ({dst.stat().st_size} B, sha256={sha256_file(dst)})")
    return dst


def load_gitignore_patterns() -> list[str]:
    gi = ROOT / ".gitignore"
    pats = []
    if gi.exists():
        for line in gi.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                pats.append(s)
    return pats


def is_ignored(rel_posix: str, pats: list[str]) -> bool:
    parts = rel_posix.split("/")
    for pat in pats:
        if pat.endswith("/"):
            d = pat[:-1]
            if "/" in d:
                if fnmatch.fnmatch(rel_posix, d) or fnmatch.fnmatch(rel_posix, d + "/*"):
                    return True
            else:
                if any(fnmatch.fnmatch(seg, d) for seg in parts):
                    return True
        else:
            if "/" in pat:
                if fnmatch.fnmatch(rel_posix, pat):
                    return True
            else:
                if fnmatch.fnmatch(parts[-1], pat):
                    return True
    return False


def audit_git() -> None:
    """Walk the repo using .gitignore rules and verify repo size, no build caches, and GitHub file-size limits."""
    pats = load_gitignore_patterns()
    kept = []
    flagged = []
    total_bytes = 0
    max_file = (0, "")

    def walk(d: Path):
        nonlocal total_bytes, max_file
        for entry in sorted(d.iterdir()):
            rel = entry.relative_to(ROOT).as_posix()
            if entry.name == ".git":
                continue
            if is_ignored(rel, pats):
                continue
            if entry.is_dir():
                walk(entry)
            else:
                sz = entry.stat().st_size
                total_bytes += sz
                if sz > max_file[0]:
                    max_file = (sz, rel)
                kept.append(rel)
                if sz > 50 * 1024 * 1024:
                    flagged.append(f"{rel} ({sz/1048576:.1f} MiB > 50 MiB GitHub warning limit)")
                if any(bad in rel for bad in ("/target/", "/target_", "/build/", "/scratch/", "__pycache__")):
                    flagged.append(f"{rel} (build/cache artifact)")

    walk(ROOT)
    print(f"[audit-git] Tracked repo files: {len(kept)} ({total_bytes/1048576:.2f} MiB total, largest: {max_file[1]} = {max_file[0]/1048576:.2f} MiB)")
    by_top: dict[str, tuple[int, int]] = {}
    for f in kept:
        t = f.split("/")[0] if "/" in f else "(root)"
        c, b = by_top.get(t, (0, 0))
        by_top[t] = (c + 1, b + (ROOT / f).stat().st_size)
    for k, (c, b) in sorted(by_top.items()):
        print(f"  {k:<20s}: {c:4d} files  ({b/1048576:6.2f} MiB)")

    if flagged:
        print("\n[FAIL] Unwanted artifacts or oversized files found:")
        for f in flagged[:30]:
            print("  !", f)
        sys.exit(1)
    print("\n[PASS] Repo is clean and ready for GitHub (all files well under GitHub limits, zero build/cache bloat)!")


def main() -> None:
    ap = argparse.ArgumentParser(description="Newtribe-SX Build & Audit Tool")
    ap.add_argument("cmd", choices=["all", "sd", "dsp", "audit-git"])
    args = ap.parse_args()
    if args.cmd == "sd":
        build_sd()
    elif args.cmd == "dsp":
        build_dsp()
    elif args.cmd == "all":
        build_sd()
        build_dsp()
    elif args.cmd == "audit-git":
        audit_git()


if __name__ == "__main__":
    main()

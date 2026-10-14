#!/usr/bin/env python3
"""Build Luma's Finder installer without modifying or launching the source app."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import plistlib
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "work/luma-dmg-tools"))
import dmgbuild
from ds_store import DSStore


def run(*args, capture=False):
    return subprocess.run(args, check=True, capture_output=capture)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(root):
    return {str(p.relative_to(root)): ("link:" + os.readlink(p) if p.is_symlink() else digest(p))
            for p in root.rglob("*") if p.is_file() or p.is_symlink()}


def require_clean_bundle_metadata(root):
    # FinderInfo/resource forks invalidate modern app signatures even when all
    # ordinary file bytes are identical. Check the bundle root as well as files.
    forbidden = {"com.apple.FinderInfo", "com.apple.ResourceFork"}
    # Python's os.listxattr is not available in all macOS Python distributions.
    # xattr -rs reads names only and checks symlinks without following them.
    attributes = run("/usr/bin/xattr", "-rs", str(root), capture=True).stdout.decode("utf-8")
    for line in attributes.splitlines():
        path, separator, name = line.rpartition(": ")
        if separator and name in forbidden:
            raise RuntimeError(f"Signed app has forbidden metadata at {path}: {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, default=HERE / "Luma.app")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true", help="Validate inputs without mounting an image")
    args = parser.parse_args()
    app = args.app.resolve()
    if app.name != "Luma.app" or not app.is_dir():
        raise ValueError("Choose an existing Luma.app bundle")
    info = plistlib.loads((app / "Contents/Info.plist").read_bytes())
    if info.get("CFBundleIdentifier") != "com.roey.luma":
        raise ValueError("Unexpected application identifier")
    version = info["CFBundleShortVersionString"]
    signature = subprocess.run(["/usr/bin/codesign", "-d", "--verbose=4", str(app)],
                               check=True, capture_output=True, text=True).stderr
    developer_signed = "Authority=Developer ID Application:" in signature
    suffix = "candidate" if developer_signed else "preview"
    output = (args.output or HERE / f"Luma-{version}-Apple-Silicon-{suffix}.dmg").resolve()
    if output.suffix != ".dmg" or output.is_relative_to(app):
        raise ValueError("Output must be a .dmg outside the app bundle")
    background = HERE / "luma-distribution-art/Luma-DMG-background.tiff"
    icon = app / "Contents/Resources/Luma.icns"
    for p in [background, icon]:
        if not p.is_file():
            raise ValueError(f"Missing installer artwork: {p.name}")
    run("/usr/bin/codesign", "--verify", "--deep", "--strict", str(app))
    require_clean_bundle_metadata(app)
    before = manifest(app)
    settings = {
        "format": "UDZO", "filesystem": "HFS+", "size": "128M",
        "files": [(str(app), "Luma.app")],
        "symlinks": {"Applications": "/Applications"},
        "icon": str(icon), "background": str(background),
        "icon_locations": {"Luma.app": (190, 255), "Applications": (530, 255)},
        "window_rect": ((160, 160), (720, 480)),
        "icon_size": 96, "text_size": 13, "label_pos": "bottom",
        "arrange_by": None, "grid_spacing": 80,
        "show_status_bar": False, "show_toolbar": False,
        "show_pathbar": False, "show_sidebar": False, "show_tab_view": False,
        "default_view": "icon-view", "include_icon_view_settings": True,
        "include_list_view_settings": False, "show_icon_preview": False,
        # Hiding the app extension would run SetFile on the signed bundle and
        # add com.apple.FinderInfo. Keep all Finder decoration outside Luma.app.
        "hide_extensions": [],
    }
    print(f"Luma {version} · Apple silicon · macOS 13+", flush=True)
    print("Developer ID signed; notarization still required." if developer_signed
          else "Private preview: not Developer ID signed or notarized.", flush=True)
    if args.check:
        print("PASS signatures, artwork, app identity and installer layout inputs")
        print(json.dumps({"output": str(output), "settings": settings}, indent=2))
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    # Keep the prior deliverable intact until the new image passes verification.
    with tempfile.TemporaryDirectory(prefix="luma-dmg-", dir=output.parent) as temp:
        image = Path(temp) / output.name
        print("Building the installation window…", flush=True)
        dmgbuild.build_dmg(str(image), "Luma", settings=settings, lookForHiDPI=False)
        run("/usr/bin/hdiutil", "verify", str(image))
        mounted = plistlib.loads(run("/usr/bin/hdiutil", "attach", "-readonly", "-nobrowse",
                                    "-plist", str(image), capture=True).stdout)
        volumes = [e for e in mounted["system-entities"] if "mount-point" in e]
        if len(volumes) != 1:
            raise RuntimeError("Expected one installer volume")
        volume = Path(volumes[0]["mount-point"])
        try:
            assert (volume / "Applications").is_symlink()
            assert os.readlink(volume / "Applications") == "/Applications"
            assert manifest(volume / "Luma.app") == before, "Packaged app changed"
            require_clean_bundle_metadata(volume / "Luma.app")
            run("/usr/bin/codesign", "--verify", "--deep", "--strict", str(volume / "Luma.app"))
            with DSStore.open(str(volume / ".DS_Store"), "r") as store:
                assert store["Luma.app"]["Iloc"] == (190, 255)
                assert store["Applications"]["Iloc"] == (530, 255)
                view = store["."]["icvp"]
                assert view["iconSize"] == 96 and view["backgroundType"] == 2
            assert (volume / ".background.tiff").is_file()
        finally:
            run("/usr/bin/hdiutil", "detach", str(volume))
        assert manifest(app) == before, "Source app changed during packaging"
        os.replace(image, output)
    sha = digest(output)
    output.with_suffix(".sha256").write_text(f"{sha}  {output.name}\n")
    output.with_suffix(".validation.json").write_text(json.dumps({
        "version": version, "sha256": sha, "developer_id_signed": developer_signed,
        "notarized": False, "image_verified": True,
        "packaged_app_byte_identical": True, "signatures_verified": True,
        "signed_bundle_metadata_clean": True,
        "finder_layout_metadata_verified": True,
        "note": "Finder appearance and first setup on a clean Mac require separate checks.",
    }, indent=2) + "\n")
    print(f"\nReady: {output}\nThe running app and background service were not changed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"\nBuild stopped: {error}", file=sys.stderr)
        sys.exit(1)

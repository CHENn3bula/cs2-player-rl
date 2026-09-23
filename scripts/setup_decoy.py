"""Fetch the exact audited DECOY source and map. Run with Python 3.12.

python scripts/setup_decoy.py --install
The map remains a local third-party asset; this script does not redistribute it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REVISION = "6f93b8efe5a778384ccd284c31b2141b6b0ce5da"
MAP_ID = "1P75FvSoT1C_MT1ebG9U8R0dNQcSOQYUT"
ASSET_HASHES = {
    "env/assets/de_dust_2.fbx": "967f436a1f2768f9f07f37f530f1d84d5e5e56e4814864e135c7459cce774a48",
    "env/assets/de_dust2.png": "4ead7f432241d5c06fb91df917f6c77a424bfb032d255854c72019d2230d3483",
    "env/assets/WaypointDust2Verified_p3d_clean_verified.json": "4bcd62a4d898e9ff8d125934b81394469e066e73ce45b4a23dab8eb9b1e38dad",
    "models/train-di_20250328-183510_y5vpxd/checkpoints/best_model.pth": "6b58f2cdb52ae32301a32551f725743cdf41d4c068eee41e5e375909b2ec093f",
    "models/train-vae_20250321-040316_upf4hz/checkpoints/best_model.pth": "0bcf5df3e083d3a82e0104dae8bb385bc438f24adaba282409a385ab6aa6ea03",
}
DEPENDENCIES = [
    "panda3d==1.10.15", "panda3d-gltf==1.3.0", "torch==2.14.0",
    "numpy==2.5.3", "networkx==3.6.1", "plotly==7.1.0", "gdown==6.4.0",
    "pytest==9.1.1",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install", action="store_true", help="Create .venv-decoy and install pinned runtime dependencies")
    args = parser.parse_args()
    repo = ROOT / "vendor" / "decoy"
    if not repo.exists():
        repo.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "https://github.com/HATS-ICT/decoy.git", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "checkout", REVISION], check=True)
    actual = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    if actual != REVISION:
        raise SystemExit(f"Existing DECOY revision is {actual}; expected {REVISION}. Not overwriting it.")
    if subprocess.run(["git", "-C", str(repo), "diff", "--quiet", "HEAD", "--"]).returncode:
        raise SystemExit("DECOY tracked source has local changes; restore or review them before claiming the pinned runtime.")
    python = Path(sys.executable)
    if args.install:
        if sys.version_info[:2] != (3, 12):
            raise SystemExit("Use Python 3.12 for the verified runtime environment.")
        venv = ROOT / ".venv-decoy"
        subprocess.run([str(python), "-m", "venv", str(venv)], check=True)
        python = venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        lock = ROOT / "requirements-decoy.lock.txt"
        spec = ["-r", str(lock)] if lock.is_file() else DEPENDENCIES
        subprocess.run([str(python), "-m", "pip", "install", *spec], check=True)
    path = repo / "env/assets/de_dust_2.fbx"
    if not path.exists():
        code = "import gdown,sys; assert gdown.download(id=sys.argv[1],output=sys.argv[2],quiet=False)"
        subprocess.run([str(python), "-c", code, MAP_ID, str(path)], check=True)
    if path.stat().st_size < 1_000_000 or not path.read_bytes()[:32].startswith((b"Kaydara FBX Binary", b"; FBX 7.7.0")):
        raise SystemExit("Downloaded map is not the expected FBX. Inspect it before retrying.")
    records = []
    for relative, expected in ASSET_HASHES.items():
        asset = repo / relative
        actual_hash = hashlib.sha256(asset.read_bytes()).hexdigest()
        if actual_hash != expected:
            raise SystemExit(f"Asset checksum mismatch for {asset}: got {actual_hash}; expected {expected}. Refusing changed asset.")
        records.append({"path": str(asset.relative_to(ROOT)).replace("\\", "/"), "bytes": asset.stat().st_size,
                        "sha256": actual_hash})
    manifest = {"repository": "https://github.com/HATS-ICT/decoy", "revision": REVISION,
                "map_source": f"https://drive.google.com/file/d/{MAP_ID}/view", "assets": records}
    destination = ROOT / "data/manifests/decoy_assets.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()

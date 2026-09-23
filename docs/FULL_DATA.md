# Full ESTA Dust II LAN corpus

The full manifest contains **all 75 Dust II map recordings under ESTA's LAN directory at commit `0e81f74d480689a83f6e1e90835c1eb6f7aa0de2`**. They represent 75 distinct source matches and 11 tournaments, from July 8, 2021 through May 21, 2022. No outcome or team filtering is applied.

The acquisition inspected every one of the **680 LAN files** in the pinned repository tree. Map discovery reads only the first 8,192 compressed bytes of each `.xz` file and decompresses that prefix to inspect `mapName`. It then downloads the complete matching Dust II files, verifies the upstream Git blob SHA-1 (including Git's blob header), computes SHA-256, and records the immutable download URL and byte length. The total Dust II compressed raw size is **200,290,052 bytes**, about 191 MiB. The existing 12 starter files are reused and reverified.

Files:

- `data/manifests/esta-lan-discovery-v1.json`: complete map inventory and pinned Git blob IDs for all 680 LAN files.
- `data/manifests/esta-dust2-lan-full-v1.json`: all 75 verified Dust II source files, provenance, checksums, dates, match URLs, and splits.
- `data/raw/esta/`: compressed source cache, shared with the starter corpus.
- `data/processed-full/<demo_id>.json.gz`: the normalized full corpus, kept separate from the starter viewer data.
- `data/processed-full/summary.json`: per-map counts, canonical checksums and explicit failures, if any.
- `data/processed-full/scenarios.json`: candidate frame index; candidates are not automatically certified playable.
- `reports/full_data_audit.json`: independent canonical validation and waypoint-alignment measurements.

The starter manifest, its processed files, and the viewer's default 12-match catalog remain unchanged. The full corpus is selected explicitly for larger experiments.

## Verified corpus size

All 75 maps normalized successfully and passed the canonical schema checks; no maps were quarantined.

| Measure | Count |
|---|---:|
| Professional map recordings / source matches | 75 / 75 |
| Tournaments | 11 |
| Rounds | 1,963 |
| Accepted active-round frames | 352,117 |
| Accepted active-round events | 394,130 |
| Conservative scenario candidates | 1,739 |
| Raw compressed bytes | 200,290,052 |
| Normalized gzip bytes | 253,404,003 |
| Train / validation / test matches | 60 / 7 / 8 |

Cleaning retained the underlying source files and excluded 18,777 pre/post-round frames, 43 incomplete-roster frames, and 6,374 pre/post-round events from canonical output. The candidate index contains 1,043 midround and 696 postplant frames. These counts describe recorded starting-state candidates, not 1,739 certified simulator restores.

## Reproduce or resume

From the project directory after installing the main environment:

```powershell
.venv\Scripts\python.exe scripts/gather_lan_corpus.py
.venv\Scripts\igl.exe audit --manifest data/manifests/esta-dust2-lan-full-v1.json --processed-dir data/processed-full --report reports/full_data_audit.json
```

The script uses at most four concurrent header requests and two full-file downloads/decompressions. Discovery results are saved every 40 entries; acquisition reuses cache files only after matching their pinned upstream blob hash. A one-billion-byte raw Dust II limit prevents accidental unexpectedly large downloads. A normal repeated run verifies the cached bytes and regenerates deterministic canonical files.

Useful narrower operations:

```powershell
# Inspect the complete pinned LAN tree without acquiring new full files.
.venv\Scripts\python.exe scripts/gather_lan_corpus.py --discover-only

# Acquire and checksum all matching files without normalizing.
.venv\Scripts\python.exe scripts/gather_lan_corpus.py --skip-normalize

# Rebuild canonical data from an already acquired full manifest and raw cache.
.venv\Scripts\python.exe scripts/gather_lan_corpus.py --prepare-existing
```

## Splits and provenance

The full manifest assigns **60 training, 7 validation and 8 test matches**. Match groups are sorted chronologically, and the 80% and 90% group boundaries are rounded down. Every recording, round and frame from a source match remains in one split. The current corpus also has 75 distinct HLTV match URLs. Repeated teams, players and events across splits remain possible.

These full-corpus split assignments are independent of the starter engineering fixture's 8/2/2 split. **Use one manifest consistently for a study.** Merging samples using each manifest's own split labels would introduce cross-manifest leakage. No model training has been performed.

Source: [Esports Trajectories and Actions (ESTA)](https://github.com/pnxenopoulos/esta/tree/0e81f74d480689a83f6e1e90835c1eb6f7aa0de2), Peter Xenopoulos and contributors, parsed with Awpy 1.x. Dataset license: **CC-BY-SA-4.0**; see `data/manifests/ESTA-LICENSE.txt`. Raw files are unchanged. Canonical files are adapted through normalization/filtering, with those changes and exclusions recorded in each replay's provenance.

## Validation and limits

The acquisition script calls the same canonical schema validator used by the starter corpus on each map before writing a normalized output. A failed source is retained in the raw cache and manifest, and its exact error appears in `summary.json`; failures cannot be reported as a passed corpus. The separate audit rechecks raw SHA-256, canonical schema, continuous timelines, five slots per team, split metadata, and waypoint-alignment diagnostics. **The independent full-corpus audit completed with status `passed` for all 75 maps.** This means the listed checks ran successfully; the alignment measurement is not a physics-fidelity certification.

All frame/event cleaning and timing rules in [DATA.md](DATA.md) apply, including the correction for source `seconds` resetting on bomb plant and the exclusion of pre/post-round records and incomplete rosters. Missing timer cvars remain explicit, and displayed bomb clocks retain their one-second quantization caveat.

This is the **full Dust II LAN subset of the pinned ESTA release**, not all professional Dust II matches or the dataset's online subset. It is historical CS:GO data, not current CS2. It spans multiple historical game updates. Waypoint distance is a coverage diagnostic; it does not prove that every source map revision, obstacle, visibility ray, or utility interaction matches DECOY. Replay outcomes and hidden enemy information remain privileged data, never unrestricted policy observations.

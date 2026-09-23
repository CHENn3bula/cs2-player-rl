# Third-party provenance

- **DECOY code**: [HATS-ICT/decoy](https://github.com/HATS-ICT/decoy), MIT, pinned commit `6f93b8efe5a778384ccd284c31b2141b6b0ce5da`. Original license remains in the fetched checkout. Source code is not edited in place; this project's wrapper documents its behavior changes.
- **DECOY Dust II asset, radar and published checkpoints**: fetched from upstream locations, recorded in `data/manifests/decoy_assets.json`. The external FBX's original game-version and redistribution rights are not independently established. Assets stay local and are not bundled into this project's Git files. The upstream code license should not be interpreted as a separate grant for Valve game assets.
- **ESTA professional match data**: [pnxenopoulos/esta](https://github.com/pnxenopoulos/esta), Peter Xenopoulos and contributors, CC-BY-SA-4.0. Pinned source commit, original license, attribution and change notice are checked in under `data/manifests/`. Normalized/filtered data and real test excerpts are adaptations; preserve attribution and the data license when sharing them. Raw files are unchanged.
- **Python packages**: pinned in `requirements.lock` and the DECOY runtime lock file. Their installed distributions include their respective licenses.

No professional demo video, player portrait, or third-party web service is required by the local viewer.

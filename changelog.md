# Changelog

All notable changes to this dataset will be documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Dataset releases are versioned as `MAJOR.MINOR.PATCH`:

- **MAJOR** — incompatible structural changes (e.g., renamed folders, changed filename convention, removed images)
- **MINOR** — backwards-compatible additions (e.g., new metadata columns, additional splits, new generator subset)
- **PATCH** — corrections to metadata, checksums, or documentation with no change to image content

---

## [1.0.0] — 2026-05-06

### Added
- 36,000 PNG images (512 × 512 px) across six text-to-image generators:
  DALL-E 2, FuseDream, PixArt-α, SANA, Stable Diffusion 1.4, VQGAN-CLIP.
- `metadata/prompts.csv` — 40 author-written English prompts
  (20 short + 20 long, pairwise matched by `pair_id`).
- `metadata/images.csv` — per-image manifest including filename, model,
  prompt_id, iteration index, SHA-256 hash, and dimensions.
- `splits/splits_100.csv` — 100 random stratified train/test splits
  defined at the prompt level (`prompt_id`, `split_id`, `partition`).
- `splits/average_split.json` — canonical split used for all figures and
  tables in the accompanying paper; selected as the split whose per-metric
  performance vector has minimum sum of squared deviations from the
  100-split mean.
- `checksums/SHA256SUMS` — BSD-style SHA-256 checksums for all 36,000 images.
- `CITATION.cff` — CFF 1.2.0 citation metadata.
- `LICENSE.txt` — CC BY-NC-SA 4.0, with DALL-E 2 and NVIDIA-SANA redistribution caveat.

### Notes
- Image-generation scripts are maintained in a separate companion repository at https://github.com/emarich18-res/PRISM-36K and are not bundled with this record.
- The PRISM classifier and evaluation code will be released upon full paper acceptance.

[1.0.0]: https://doi.org/10.5281/zenodo.20038953
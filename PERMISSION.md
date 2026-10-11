# Redistribution permission — `DIFF_PL_phonemiser.dll`

This repository includes the third-party plugin binary `DIFF_PL_phonemiser.dll` (original and
patched variants, under `dll/`), which is **not** authored by this repository's owner.

**Permission to redistribute the DLL was granted by the plugin's creator** to the repository owner
(2026-10). This covers the unmodified binary and the patched variant produced by
`tools/patch_pl_getlangcode.ps1` (which adds a `GetLangCode()` method override; the plugin's own
data — `dict.txt`, `phones.txt`, `g2p.onnx` — is byte-identical to the original).

If you are the plugin's author and this record misstates the terms, or you want the binaries
removed or the license changed, open an issue in this repository and they will be taken down.

All other content in this repository (scripts, documentation) is written by the repository owner.

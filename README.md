# DIFF_PL_phonemiser — `pl/` language-prefix patch

Makes the third-party `DIFF_PL_phonemiser.dll` OpenUtau plugin (Polish phonemizer for DiffSinger
banks) report `GetLangCode() = "pl"`, so it emits `pl/`-prefixed phones the way `[DIFFS EN]` emits
`en/*`.

Without the prefix, one bare spelling can be claimed by two sounds: the Polish word path wants
`pl/w` (Polish /v/, token 122) while an English hint `[w]` wants `en/w` (English /w/, token 44).
OpenUtau resolves bare names first, so one of the two always gets the wrong phone and the wrong
timing. Six phones are affected — `l ng r t w y`, the deliberately un-merged en/pl pairs. Full
analysis: [docs/PL-PREFIX-PHONEMIZER-EDIT.md](docs/PL-PREFIX-PHONEMIZER-EDIT.md).

Tested in OpenUtau 0.1.571.0: Polish `woda` → `pl/w` = /v/; English hint `Trey [ch r ey]` →
`en/ch en/r en/ey`, with timing identical to the explicitly prefixed spelling.

## Contents

| path | what |
| --- | --- |
| `dll/DIFF_PL_phonemiser.pl-prefix.dll` | patched plugin, drop-in (sha256 `c5696455…`) |
| `dll/DIFF_PL_phonemiser.original.dll` | pristine plugin as received (sha256 `53a7e397…`) |
| `tools/patch_pl_getlangcode.ps1` | the patch, re-runnable |
| `tools/drop_bare_alias_bank.py` | drops the six bare shadow aliases from a bank |
| `tools/check_hint_types.py` | regression check: bare vs `en/` hint spelling |
| `docs/PL-PREFIX-PHONEMIZER-EDIT.md` | problem, root cause, fix, failed attempts |
| `docs/HISTORY-G90.md` | the wrong fixes, and why each was wrong |
| `PERMISSION.md` | redistribution permission for the DLL |

## Install

1. Close OpenUtau.
2. Back up the `DIFF_PL_phonemiser.dll` already in your OpenUtau `Plugins` folder, then copy
   `dll/DIFF_PL_phonemiser.pl-prefix.dll` over it.
3. If a bank's `phonemes.json` still carries the bare aliases `l ng r t w y`, drop them:

   ```
   python tools/drop_bare_alias_bank.py <path-to-bank> [--dry-run]
   ```

   Banks built for the unpatched plugin have them: the script finds every copy the bank ships
   (root, `dsdur/`, `dspitch/`, `dsvariance/`). The patched plugin resolves everything through
   `pl/*`, so the bare aliases are dead weight that keep capturing English hints.
4. Restart OpenUtau. Polish words should give `pl/…` phones, English hints `en/…`.

## Rebuild

```
powershell -File tools/patch_pl_getlangcode.ps1 -DllPath dll/DIFF_PL_phonemiser.original.dll
```

Mono.Cecil 0.11.5 is fetched into `.cecil/` on first run. The patcher adds `ldstr "pl"; ret` as a
`GetLangCode()` override on `DiffSingerPolishPhonemizer`, then re-reads the candidate with Cecil and
checks the method body, the override flags, the original overrides and the `g2p-pl` resource before
writing anything; a failed check deletes the candidate and leaves the tree untouched. The build is
deterministic — rebuilding from `original.dll` reproduces `pl-prefix.dll` byte for byte:
sha256 `c5696455cb990055c0538d1287466e230b1a2cc22414c0db8692b8664e16e1c3`.

Fixes to the plugin's own data (`dict.txt`, `phones.txt`, `g2p.onnx`, packed as the `g2p-pl`
resource) do not work and break its G2P; the renaming is done at runtime by `G2pRemapper`, driven by
`GetLangCode()`. See [docs/HISTORY-G90.md](docs/HISTORY-G90.md).

## Scope

- No change to OpenUtau itself; the host runs unpatched.
- Unnecessary once upstream adds `GetLangCode()` overrides (about three lines per language).

## Requirements

Windows with PowerShell (the patcher uses .NET reflection, no Visual Studio needed), Python 3 for
the two `tools/*.py` scripts, and OpenUtau with DiffSinger support — tested on 0.1.571.0.

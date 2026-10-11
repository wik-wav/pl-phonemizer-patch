# Failure-log excerpt — notebook.md G90

### G90 ðŸ”´ One bare name cannot serve two sounds â€” and my first plugin edit deleted the .NET header

**The G84â†’G89 thread ends at the source.** The bare-token whack-a-mole (State A: English hints right,
Polish broken / State B: Polish right, English hints wrong) was not three separate bugs â€” it was one
impossibility. Bare `w` is claimed by two different sounds:

| path | wants bare `w` | token id |
| --- | --- | --- |
| Polish **word** (plugin G2P, emits bare) | `pl/w` = Polish /v/ | 122 |
| English **hint** `[w]` (bare input) | `en/w` = English /w/ | 44 |

`ValidatePhoneme` resolves bare-first, so whichever way the single bare token points, **one** path is
wrong. `l ng r t w y` are exactly the deliberate un-merged en/pl pairs; the 16 merged pairs are
unaffected because both sounds share one id. **Root cause (found by decompiling the plugin with dnfile+dncil):** `DiffSingerPolishPhonemizer`
(`OpenUtau.Core.DiffSinger`) overrides `GetDictionaryName`/`LoadBaseG2p`/`GetBaseG2pVowels`/
`GetBaseG2pConsonants` but **not `GetLangCode()`** (so it returns `""`). `DiffSingerG2pPhonemizer.LoadG2p`
renames the base-G2P phones to `<lang>/<phone>` **only when `GetLangCode()` is non-empty**, then
`G2pRemapper` remaps the word output â€” exactly how `[DIFFS EN]` (which overrides `GetLangCode()="en"`)
gets `en/*`. With `""`, Polish emits **bare** names into the one namespace English hints use. The fix
must remove the ambiguity **at the source**: make the plugin report `GetLangCode()="pl"` so it emits
`pl/w`; bare `w` is then free to mean `en/w`. Both correct at once, no bank-side compromise.

**Symptom of the fix attempt itself.** The first edit (`tools/_tmp_plugin_edit.py`) rewrote the DLL as
a bare zip with Python `zipfile`. Result: the phonemizer **vanished from OpenUtau's phonemizer list** â€”
not an error, just gone.

**Evidence.** `DIFF_PL_phonemiser.dll` is **simultaneously a PE/CLR assembly and a zip**:
`bytes[0:9514]` is PE + CLR + IL (CLR header RVA 8200, size 72), and only from offset 9514 does the
self-extracting zip tail begin (`dict.txt`@9514, `g2p.onnx`@9717, `phones.txt`@1653181). `zipfile`
discovers the zip through the end-of-central-directory record at the end and silently **rewrote the
whole file as zip-only**, discarding the 9,514-byte .NET prefix. `is_zipfile` stayed true â€” which is
why a "did the zip survive?" check passes on a corpse. The `.NET` loader sees no `MZ`-rooted CLR
metadata and drops the assembly silently, hence "doesn't show up on the list".

**Fix** (two halves â€” both needed; verified in OpenUtau, owner: "fix worked flawlessly"):
1. **Plugin â€” real IL edit via Mono.Cecil 0.11.5: add a `GetLangCode()` override returning `"pl"`**
   (`ldstr "pl"; ret`, public/virtual/reuseSlot = a true override of `DiffSingerBasePhonemizer.GetLangCode`)
   to `DiffSingerPolishPhonemizer`. `LoadG2p` then renames the Polish G2P output `w â†’ pl/w` via
   `G2pRemapper`, mirroring English's `en/*`. Globals (`cl`/`SP`/`AP`) stay bare automatically
   (`IsPhonemeSupported("pl/cl")` is false â†’ the `else if(IsPhonemeSupported(ph))` fallback keeps bare).
   The `g2p-pl` resource (`dict.txt`/`phones.txt`/`g2p.onnx`) is **untouched** â€” those are `PolishG2p`'s
   internal vocab; the rename is done by `G2pRemapper`, not those tables.
2. **Drop the six bare aliases `l ng r t w y` from every `phonemes.json`** (`tools/drop_bare_alias_all.py`,
   root + dsdur/dspitch/dsvariance Ã— both banks, 196â†’190, twin-guarded). With the plugin now emitting
   `pl/*`, these bare names only shadowed `en/*`; dropping them lets `ValidatePhoneme` fall through to
   `en/r` â€” fixing sound, timing **and** the display (`r`â†’`en/r`, like `ch`/`ey`).

**SUPERSEDED â€” everything below ("Symptom of the fix attempt", "Half 1 detail", the numbered zip-repack
list, "self-extracting archive" Rule) records FAILED table-rename approaches
(`_tmp_plugin_edit.py`, `patch_pl_plugin.py`, `patch_pl_plugin_v2.py`: rename `dict.txt`/`phones.txt`
inside the `g2p-pl` resource to `pl/*`). They did NOT work and are kept only as evidence:**
renaming those tables made `PolishG2p` reject its own G2P output (`Unrecognized phoneme "w"`), and
repacking the DLL's zip / `.resources` truncated the fixed-size resource frame â†’ `ResourceReader` threw
at init â†’ the phonemizer silently vanished from OpenUtau's list (twice). The rename must happen at
`GetLangCode` â†’ `G2pRemapper`, never in the data tables.

**The real Check (passed).** Cecil re-read: `GetLangCode` body `ldstr pl; ret`, 4 overrides intact;
`ResourceReader` read-back: `g2p-pl` = 1,644,114 bytes. Model level: `tools/check_hint_types.py` EN
chain **PASS** on both banks â€” `ch r ey` bare `starts=[1]` == `en/ch en/r en/ey` `starts=[1]` (the
DIVERGENCE is gone), and every plugin-emitted `pl/*` target resolves. OpenUtau (owner): "fix worked
flawlessly" â€” Polish `woda`â†’`pl/w`=/v/ (122), English hint `Trey [ch r ey]`â†’`en/ch en/r en/ey` (id 36,
prefixed, identical timing). Full write-up: `documentation/PL-PREFIX-PHONEMIZER-EDIT.md`.

**Half 1 detail â€” the first plugin edit deleted the .NET header, and the SECOND broke the `.resources`
frame.** Both died editing the *wrong* zip. Truth (from .NET `ResourceReader`, not Python `zipfile`):
the plugin reads ONE manifest resource **`g2p-pl`**, a `Byte[]` that is itself a zip of
`dict.txt`/`g2p.onnx`/`phones.txt`, at file `[9514, 1653628)` inside a `.resources` blob `[9300, 1653628)`.
The DLL is *also* a valid outer zip, but that view is a coincidental overlay the plugin never reads.
Attempt 1 (`_tmp_plugin_edit.py`) rewrote the whole file as a bare zip â†’ `is_dotnet=False` â†’ phonemizer
gone from the list. Attempt 2 (`patch_pl_plugin.py`) rebuilt the *outer* zip tail and rebased offsets,
shrinkÂ­ing the file to 1653474 â†’ truncated the fixed-size `.resources` (needed end 1653628) and smashed
its directory â†’ `ResourceReader` threw at init â†’ gone again (`is_dotnet=True` this time, which is why it
looked survivable). **v2 (`patch_pl_plugin_v2.py`) is in-place and framing-preserving:** transform the
`g2p-pl` *inner* zip only (`dict.txt` right col + `phones.txt` left col â†’ `pl/`, `KEEP_BARE={cl,SP,AP}`,
`g2p.onnx` verÂ­batim, CRLF preserved), pad it with a zip comment to **exactly 1644114 bytes**, and swap
it into `[9514, 1653628)`. PE/CLR/metadata, `.resources` dir, CLI `Resources.size` and total size 1655808
stay **byte-identical** â€” so the frame and assembly load cannot break. (Earlier note that the fix
preserved a "PE prefix + zip tail" is superseded by this.)

1. keep `bytes[0:9514]` **byte-identical** (PE/CLR/IL untouched);
2. rebuild only the **zip tail**: same three entries, `g2p.onnx` copied verbatim (never re-encoded),
   `dict.txt` right column and `phones.txt` left column rewritten to `pl/`-prefixed except
   `KEEP_BARE = {"cl","SP","AP"}` (language-neutral globals) â€” the `dict.txt` **grapheme** column is
   untouched so unprefixed input still matches (owner requirement);
3. rebase every stored local-header offset by `+len(prefix)`;
4. **verify before any write**: PE prefix byte-identical, `MZ`/`PE\0\0` intact, CLR data-directory
   index 14 non-zero, zip parses with exactly the three entries, content round-trips, every
   central-directory `header_offset` lands on `PK\x03\x04`. Writes nothing on failure.

Applied 2026-10-08: `VERIFY: PE/CLR preserved, CLR header present, zip round-trips, offsets valid.`
On-disk re-probe: `is_dotnet=True` (the check the first edit failed), `is_zip=True`, `dict.txt` 389 b
and `phones.txt` 372 b (up from 269/255 â€” the prefixes), `g2p.onnx` 1,778,876 b unchanged. Revert at
any point: `DIFF_PL_phonemiser.dll.bak-20261008` (sha256 `53a7e397â€¦`).

**Rule.** A file that is both a .NET assembly and a zip is a self-extracting archive: "it parses as a
zip" is true of the corpse after any repack. Preserve the PE prefix verbatim and rebase the offsets;
never let `zipfile` write the whole file. And for any format-hybrid artifact, the integrity check must
assert **both** identities (`is_dotnet` AND `is_zip`), not just the one the tool knows how to read.

**Check.** `tools/patch_pl_plugin.py --dry-run`'s verify gate (four assertions above) +
`tools/_tmp_dll_probe.py`'s `is_dotnet=True` on the **written** file + `_tmp_verify_plugin_names.py`
(all 41 emitted names resolve). Model level: `tools/check_hint_types.py` EN chain **PASS** on both
banks â€” `ch r ey` bare `starts=[1]` == `en/ch en/r en/ey` `starts=[1]` (the DIVERGENCE is gone).
(The GENERIC `[DIFFS]` chain diverges by design: `GetLangCode()==""` means a bare hint has no language
to auto-prefix to, so it needs an explicit `lang/` â€” see `documentation/PL-PREFIX-PHONEMIZER-EDIT.md`
Â§7.1. Default phonemizer is `[DIFFS EN]`, so this is not the owner's path.) OpenUtau-side, the four
render checks: Polish `woda`â†’`pl/w`=/v/ (122), English hint `[w]`â†’`en/w`=/w/ (44), `Tray [ch r ey]`
timing == `[en/ch en/r en/ey]`, and a plain unprefixed Polish word still phonemizes.







# Making the Polish phonemizer emit `pl/`-prefixed phones — root cause and fix

Status: **FIXED and verified in OpenUtau (owner: "fix worked flawlessly"), 2026-10-08.**
Companion failure-log entry: `notebook.md` G90.

---

## 1. The problem

`Trey [ch r ey]` phonemized to `en/ch, r, en/ey` — the `r` came out with **no `en/` prefix** and was
**timed differently** from the explicit `en/r`. Generalized by the owner: `r` was one example; several
phones (`l ng r t w y`) behaved this way. The ask: *"per each language, have the phonemic hints
automatically prefixed with the right `lang/`, when it makes sense."*

## 2. Root cause — the Polish phonemizer never reports a language code

`<OpenUtau>\Plugins\DIFF_PL_phonemiser.dll` decompiled (dnfile + dncil for reading, **Mono.Cecil 0.11.5**
for the edit) is:

```
OpenUtau.Core.G2p.PolishG2p : OpenUtau.Api.G2pPack
OpenUtau.Core.DiffSinger.DiffSingerPolishPhonemizer : OpenUtau.Core.DiffSinger.DiffSingerG2pPhonemizer
    GetDictionaryName, LoadBaseG2p, GetBaseG2pVowels, GetBaseG2pConsonants   (overrides)
    // NOTE: NO GetLangCode() override
```

`DiffSingerG2pPhonemizer.LoadG2p` renames the base-G2P phones to `<lang>/<phone>` **only when
`GetLangCode()` is non-empty** ([DiffSingerG2pPhonemizer.cs:100-116](../Q:/GitHub/OpenUtau/OpenUtau.Core/DiffSinger/Phonemizers/DiffSingerG2pPhonemizer.cs)):

```csharp
var langCode = GetLangCode();
if(!string.IsNullOrEmpty(langCode)){
    foreach (var ph in GetBaseG2pVowels().Concat(GetBaseG2pConsonants())){
        if(replacements.ContainsKey(ph)) continue;
        var prefixed = langCode + "/" + ph;
        if(IsPhonemeSupported(prefixed))      replacements[ph] = prefixed;
        else if(IsPhonemeSupported(ph))       replacements[ph] = ph;
        else                                  replacements[ph] = useLangId ? prefixed : ph;
    }
}
g2ps.Add(new G2pRemapper(baseG2p, phonemeSymbols, replacements));   // remaps the word G2P output
```

`G2pRemapper.Query` applies `replacements` to the word output ([G2pRemapper.cs:39-42](../Q:/GitHub/OpenUtau/OpenUtau.Core/Api/G2pRemapper.cs)).

`[DIFFS EN]` overrides `GetLangCode()="en"` → emits `en/*`. The Polish plugin returns `""` → the loop is
skipped → it emits **bare** names (`w`, `r`, …).

Those bare names collide with English **phonetic hints**, which `ValidatePhoneme` resolves **bare-first**
([DiffSingerBasePhonemizer.cs:180-192](../Q:/GitHub/OpenUtau/OpenUtau.Core/DiffSinger/DiffSingerBasePhonemizer.cs)):

```csharp
if (g2p.IsValidSymbol(phoneme) && phonemeTokens.ContainsKey(phoneme)) return phoneme;   // BARE wins
var phonemeWithLanguage = langCode + "/" + phoneme; ...
```

So one bare `w` in `phonemes.json` can map to only **one** token — `pl/w` (=122, Polish /v/) for the
Polish word path, or `en/w` (=44, English /w/) for English hints. `l ng r t w y` are exactly the six
**deliberately un-merged** en/pl pairs where the two sounds/tokens genuinely differ. Whichever way the
single bare token points, one path is wrong — which is why every bank-only change regressed the other side.

**Fix direction: remove the ambiguity at the source — make the Polish path emit `pl/*`, then the bare
namespace is free to mean English.**

## 3. The fix (two coordinated changes)

### (a) Plugin — real IL edit: add `GetLangCode()` returning `"pl"`

Via **Mono.Cecil** (loaded from a byte array to bypass the Mark-of-the-Web `0x80131515` block), added to
`DiffSingerPolishPhonemizer` a method:

```
GetLangCode : string   (public, virtual, reuseSlot → a true override of DiffSingerBasePhonemizer.GetLangCode)
    ldstr "pl"
    ret
```

Now `LoadG2p` renames the Polish G2P output `w → pl/w` etc. through `G2pRemapper` — exactly mirroring how
English gets `en/*`. Globals stay bare automatically: `IsPhonemeSupported("pl/cl")` is false, so the
`else if(IsPhonemeSupported(ph))` branch keeps bare `cl`/`SP`/`AP`. `dict.txt`/`phones.txt`/`g2p.onnx`
(the `g2p-pl` resource) are **untouched** — they are `PolishG2p`'s internal vocab; the rename is done by
`G2pRemapper`, not those tables.

Verified after write: `GetLangCode` body `ldstr pl; ret`, the 4 original overrides intact, and the
`g2p-pl` manifest resource still reads back as a 1,644,114-byte `Byte[]` via `ResourceReader`.

### (b) Bank — drop the six bare shadows

Removed `l ng r t w y` from **every** `phonemes.json` (root + `dsdur` + `dspitch` + `dsvariance`, both
`2027-V2\bank\lem_v2` and `<OpenUtau>\Singers\content\OU_voicebank\lem_v2`; 196 → 190 names each).
With the plugin now emitting `pl/*`, nothing produces those bare names, so they only shadowed `en/*`.
Dropping them makes a bare English hint fall through to `en/r` — fixing sound, timing **and** the `en/`
display label (like `ch`/`ey` already behaved). Guarded so it aborts unless both `en/<x>` and `pl/<x>`
twins exist.

### Result

| input | resolves to | sound / id | label |
| --- | --- | --- | --- |
| Polish word `woda` | `pl/w pl/o pl/d pl/a` | /v/ id 122 | `pl/w` |
| English hint `[ch r ey]` | `en/ch en/r en/ey` | English R id 36 | `en/ch en/r en/ey` |
| `[ch r ey]` vs `[en/ch en/r en/ey]` | — | **identical timing** | — |

## 4. What did NOT work (tried and rejected — the lessons)

1. **Retargeting the bare token in `phonemes.json`** (bare→`en/*` or bare→`pl/*`) — impossible; one bare
   name can't serve two tokens (§2). Bank-only whack-a-mole.
2. **Renaming `dict.txt`/`phones.txt` inside the `g2p-pl` resource to `pl/*`** — wrong lever. Those are
   `PolishG2p`'s internal vocab (its output names come from `g2p.onnx`); renaming them made the G2P
   reject its own output → `Unrecognized phoneme "w"` crash. The rename is done by `G2pRemapper`, driven
   by `GetLangCode()`.
3. **Repacking the DLL as a zip / rebuilding its `.resources`** — `DIFF_PL_phonemiser.dll` is a .NET
   assembly with one manifest resource `g2p-pl` (a `Byte[]` that is itself a zip). Rewriting the file as
   a zip, or repacking the `.resources`, truncated the fixed-size resource frame → `ResourceReader` threw
   at init → the phonemizer silently vanished from OpenUtau's list. (Note: the DLL *is* also a valid zip
   at the outer level, but the plugin never reads that view.)

**Rule (G90).** When a fix requires a behavior the component doesn't expose (here, a language code), edit
the component to expose it — don't rename its data tables. And for a format-hybrid file (.NET assembly +
embedded resource + coincidental outer zip), change only the one bytes that must change and assert every
other identity still holds before committing.

## 5. Reproducible procedure

1. **Backup** `DIFF_PL_phonemiser.dll` → `.bak-20261008` (sha256 `53a7e397…`, 1,655,808 bytes).
2. **Decompile** (read-only): `dnfile` + `dncil` list types/methods; confirmed `DiffSingerPolishPhonemizer`
   overrides `GetDictionaryName`/`LoadBaseG2p`/`GetBaseG2pVowels`/`GetBaseG2pConsonants` but **not**
   `GetLangCode`. Read `DiffSingerG2pPhonemizer.LoadG2p` + `G2pRemapper.Query` source to confirm the
   `GetLangCode` → `replacements` → `G2pRemapper` rename path.
3. **Edit (Mono.Cecil):** `AssemblyDefinition.ReadAssembly(<pristine backup>)`, add the `GetLangCode`
   override (`ldstr "pl"; ret`, `MethodAttributes` public+virtual+reuseSlot), `Write(<candidate>)`.
   Load Cecil with `[Reflection.Assembly]::Load(ReadAllBytes(...))` (byte load bypasses MOTW); set method
   flags via the `IsPublic`/`IsVirtual`/`IsReuseSlot`/`IsHideBySig` properties (PowerShell `-bor` on the
   enum throws `InvalidCastException`).
4. **Verify the candidate before committing:** re-read with Cecil (body = `ldstr "pl"; ret`, 4 overrides
   intact) + `ResourceReader` read-back of `g2p-pl` (= 1,644,114 bytes) + `MZ`/PE check. Commit only on
   PASS (`Copy-Item candidate → dll`).
5. **Drop bare shadows:** `tools/drop_bare_alias_all.py` (removes `l ng r t w y` from all 8 `phonemes.json`,
   twin-guarded). Then `tools/check_hint_types.py --phonemizer EN` (expect PASS).
6. **OpenUtau check** (confirmed): Polish `woda`→`pl/w`=/v/ (122); English hint `[ch r ey]`→`en/ch en/r
   en/ey` (id 36, prefixed, identical timing to the explicit spelling).

## 6. Verification results

* `check_hint_types.py` (EN chain, both banks): 15 bare/en pairs classify and place identically;
  `ch r ey` bare `starts=[1]` == `en/ch en/r en/ey` `starts=[1]` — the "`r` is timed differently"
  DIVERGENCE is gone. **PASS.**
* All plugin-emitted targets resolve (`pl/*` + `cl`/`SP`/`AP` globals) in both banks — no missing symbols.
* OpenUtau (owner): **"fix worked flawlessly."**

## 7. Tools written this session

* `tools/drop_bare_alias_all.py` — **part (b)**: drops the six bare shadows from every `phonemes.json`
  (root + 3 submodules × both banks), twin-guarded and idempotent.
* `tools/check_hint_types.py` — models `ValidatePhoneme` + `ProcessWord` placement (EN chain = dsdict +
  base-G2P union; GENERIC = `dsdict.yaml` only) and asserts a bare symbol places identically to its
  `<lang>/` twin. Regression gate.
* `tools/_tmp_disasm.py` / `_tmp_decompile_explore.py` — dnfile+dncil type/method/IL dump (read-only).
* `tools/_tmpcecil/` — Mono.Cecil 0.11.5 (from NuGet) used for the IL edit.
* Superseded (kept as evidence, do **not** reuse): `patch_pl_plugin.py`, `patch_pl_plugin_v2.py`
  (table-rename approaches), `_tmp_plugin_edit.py` (bare-zip rewrite), `fix_dsdict_bare_types.py`,
  `drop_bare_alias_shadow.py` (single-bank variant).

## 8. Revert

* Plugin: `<OpenUtau>\Plugins\DIFF_PL_phonemiser.dll.bak-20261008` → `DIFF_PL_phonemiser.dll`
  (pristine original, sha256 `53a7e397…`).
* Banks: `phonemes.json` ← `.bak-barealias` in each of the 8 copies (restores the six bare aliases).

## 9. Known limitation

Under the generic `[DIFFS]` phonemizer (`GetLangCode()==""`, no word G2P), a *bare* hint needs an explicit
`lang/` prefix — there is no language to auto-prefix to. This matches "prefix **when it makes sense**";
the default phonemizer is `[DIFFS EN]` (`character.yaml`), which is unaffected. (A bare hint typed while
the Polish phonemizer is selected now falls through to `pl/*` too, since `GetLangCode()=="pl"`.)

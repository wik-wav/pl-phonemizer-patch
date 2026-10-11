"""check_hint_types.py - assert that a bare phoneme and its <lang>/ twin produce the SAME
phoneme-to-note placement (TIMING) in OpenUtau.

Regression gate for notebook.md G90. It models the ACTUAL resolution OpenUtau performs -- the same
one, for every phoneme in the bank, not just `r`:

  1. VALIDITY (G2pFallbacks.IsValidSymbol): TRUE if the symbol is declared in the phonemizer's
     loaded dsdict (dsdict-en.yaml for [DIFFS EN], dsdict.yaml for [DIFFS]) OR is a base-G2P
     vowel/consonant.  DiffSingerG2pPhonemizer.LoadG2p:94-99 adds every base-G2P phone to the
     symbol set; DiffSingerBasePhonemizer.LoadG2p does NOT (so [DIFFS] only accepts dsdict names).
     -> ProcessWord:264 throws `Type definition of symbol X not found` on any INVALID symbol.

  2. TYPE FLAGS (G2pDictionary.AddSymbol, G2pFallbacks.IsVowel/IsGlide): looked up per dictionary,
     first-dict-that-VALIDATES-it wins:
         isVowel = (type == 'vowel')
         isGlide = (type in ('semivowel','liquid'))
     For [DIFFS EN] the chain is [dsdict-en.yaml, baseG2P] -> a bare phone declared in dsdict-en
     wins there; one NOT declared there falls to baseG2P's vowel/consonant (never a glide).
     For [DIFFS] it is [dsdict.yaml] only.

  3. PLACEMENT (DiffSingerBasePhonemizer.ProcessWord:276-302): the Consonant-Glide-Vowel rule
         if i>=2 and isGlide[i-1] and not isVowel[i-2]: isStart[i-1] = True   # glide pulls to the vowel's onset
         else:                                          isStart[i]   = True
     `isStart` is what splits a word across notes, so it IS the timing.

THE INVARIANT: for every bare X with a <lang>/X twin, the (validity, isVowel, isGlide) that the
ACTIVE resolution produces for X and for <lang>/X must be identical. When they are, `[ch r ey]` and
`[en/ch en/r en/ey]` place every phoneme on the same note and time identically. When they differ --
an undeclared bare name, or a bare `liquid`/`semivowel` twin that resolves to baseG2P's consonant --
the two spellings diverge. This is checked for EVERY phone in the bank, so it catches the whole class
(`l ng r t w y` and any future one), not just the phone first noticed.

Note on the DISPLAYED label: ValidatePhoneme returns the bare name whenever it resolves (bare-first),
so the piano roll shows `r`, not `en/r`. That is host naming behaviour (G89) and is NOT this check --
this check is about the audio/timing being identical, which is bank-side and is what G90 fixes.

Usage:
    python tools/check_hint_types.py --bank <bank dir> [<bank dir> ...] [--lang en] [--phonemizer EN|GENERIC]

Exit 0 = every bare/<lang>/ pair resolves and places identically. Exit 1 = a divergence, each printed
with the two resolutions and the phonemes whose note placement differs.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

import yaml

GLIDE_TYPES = {'semivowel', 'liquid'}

# Base-G2P phones of the English DiffSinger phonemizers (DiffSingerEnglishPhonemizer +
# DiffSingerARPAPlusEnglishPhonemizer). Valid + typed vowel/consonant by LoadG2p:94-99; NEVER glides
# (AddSymbol(symbol, bool isVowel) leaves the glide set empty), and load-bearing for [DIFFS EN+].
BASE_G2P_VOWELS = ['aa', 'ae', 'ah', 'ao', 'aw', 'ax', 'ay', 'eh', 'er', 'ey',
                   'ih', 'iy', 'ow', 'oy', 'uh', 'uw']
BASE_G2P_CONSONANTS = ['b', 'ch', 'd', 'dh', 'dr', 'dx', 'f', 'g', 'hh', 'jh',
                       'k', 'l', 'm', 'n', 'ng', 'p', 'q', 'r', 's', 'sh', 't',
                       'th', 'tr', 'v', 'w', 'y', 'z', 'zh']


def load_tokens(bank: pathlib.Path) -> dict:
    return json.loads((bank / 'phonemes.json').read_text(encoding='utf-8-sig'))


def load_symbols(path: pathlib.Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding='utf-8-sig')) or {}
    return {e['symbol']: e.get('type') for e in (data.get('symbols') or [])}


class Resolution:
    """(valid, isVowel, isGlide) for one symbol under one phonemizer's G2pFallbacks chain."""

    __slots__ = ('valid', 'is_vowel', 'is_glide', 'source')

    def __init__(self, valid, is_vowel, is_glide, source):
        self.valid, self.is_vowel, self.is_glide, self.source = valid, is_vowel, is_glide, source

    def flags(self):
        return (self.valid, self.is_vowel, self.is_glide)

    def __repr__(self):
        if not self.valid:
            return 'INVALID(->ProcessWord:264 throws)'
        return f'{"vowel" if self.is_vowel else "consonant"}' + (f'+glide[{self.source}]' if self.is_glide else f'[{self.source}]')


def resolve(symbol: str, chain: list[tuple[str, dict]], base: dict | None) -> Resolution:
    """Mirror G2pFallbacks: first dict in the chain that VALIDATES the symbol supplies its flags."""
    for name, table in chain:
        if symbol in table:
            t = table[symbol]
            return Resolution(True, t == 'vowel', t in GLIDE_TYPES, name)
    if base is not None and symbol in base:
        return Resolution(True, base[symbol], False, 'baseG2P')
    return Resolution(False, False, False, '')


def note_starts(symbols: list[str], chain, base):
    res = [resolve(s, chain, base) for s in symbols]
    if not all(r.valid for r in res):
        return None, res  # ProcessWord:264 would throw
    is_vowel = [r.is_vowel for r in res]
    is_glide = [r.is_glide for r in res]
    n = len(symbols)
    is_start = [False] * n
    if not any(is_vowel):
        is_start[0] = True
    for i in range(n):
        if is_vowel[i]:
            if i >= 2 and is_glide[i - 1] and not is_vowel[i - 2]:
                is_start[i - 1] = True
            else:
                is_start[i] = True
    return [i for i, v in enumerate(is_start) if v], res


def build_chain(bank: pathlib.Path, lang: str, phonemizer: str) -> tuple[list, dict | None]:
    ddir = bank / 'dsdur'
    base = None
    if phonemizer == 'EN':  # [DIFFS EN] / [DIFFS EN+]: LoadG2p adds base-G2P phones
        base = {p: (p in BASE_G2P_VOWELS) for p in BASE_G2P_VOWELS + BASE_G2P_CONSONANTS}
        chain = []
        en = ddir / f'dsdict-{lang}.yaml'
        uni = ddir / 'dsdict.yaml'
        pick = en if en.exists() else uni  # GetDictionaryName() -> dsdict-<lang>.yaml, else dsdict.yaml
        chain.append((pick.name, load_symbols(pick)))
    else:  # [DIFFS] generic: DiffSingerBasePhonemizer.LoadG2p, NO base-G2P, dict is dsdict.yaml
        chain = [('dsdict.yaml', load_symbols(ddir / 'dsdict.yaml'))] if (ddir / 'dsdict.yaml').exists() else []
    return chain, base


def check_bank(bank: pathlib.Path, lang: str, phonemizer: str) -> int:
    tokens = load_tokens(bank)
    chain, base = build_chain(bank, lang, phonemizer)
    problems = 0
    print(f'=== {bank}  [{phonemizer}] ===')
    for name, _ in chain:
        print(f'  chain: {name}' + (' + baseG2P' if base else ''))
    print()

    pairs = []
    for bare in sorted(tokens):
        if '/' in bare or bare in ('SP', 'AP'):
            continue
        twin = f'{lang}/{bare}'
        if twin in tokens:
            pairs.append((bare, twin))
    if not pairs:
        print(f'  no bare/{lang}/ twin pairs in phonemes.json')
        return 0

    divergent = []
    for bare, twin in pairs:
        rb = resolve(bare, chain, base)
        rt = resolve(twin, chain, base)
        if rb.flags() != rt.flags():
            divergent.append((bare, twin, rb, rt))

    print(f'  {len(pairs)} bare/{lang}/ pairs checked.')
    if divergent:
        problems += len(divergent)
        print(f'  {len(divergent)} DIVERGENT (bare vs {lang}/ twin resolve or classify differently):')
        for bare, twin, rb, rt in divergent:
            why = []
            if rb.valid != rt.valid:
                why.append('validity')
            if rb.is_vowel != rt.is_vowel:
                why.append(f'IsVowel {rb.is_vowel}->{rt.is_vowel}')
            if rb.is_glide != rt.is_glide:
                why.append(f'IsGlide {rb.is_glide}->{rt.is_glide}')
            print(f'    {bare!r}={rb}  vs  {twin!r}={rt}   [{", ".join(why)}]')
    else:
        print(f'  OK - every bare symbol resolves and classifies exactly like its {lang}/ twin')

    # Whole-word placement proof across the actual hint phones, both spellings.
    for word in (['ch', 'r', 'ey'], ['ch', 'r', 'ey', 'z'], ['b', 'eh', 'dx', 'er'], ['ax', 'w', 'ey']):
        pref = [f'{lang}/{p}' if f'{lang}/{p}' in tokens else p for p in word]
        if not all(f'{lang}/{p}' in tokens for p in word):
            continue
        sb, _ = note_starts(word, chain, base)
        sp, _ = note_starts(pref, chain, base)
        ok = sb == sp
        if not ok:
            problems += 1
        print(f'  {" ".join(word):16} bare starts={sb}   {" ".join(pref):20} starts={sp}   {"OK" if ok else "DIVERGES"}')

    print()
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--bank', nargs='+', required=True)
    ap.add_argument('--lang', default='en')
    ap.add_argument('--phonemizer', choices=['EN', 'GENERIC'], default='EN',
                    help='EN = [DIFFS EN/EN+] (base-G2P union active); GENERIC = [DIFFS] (dsdict only)')
    args = ap.parse_args()
    total = 0
    for b in args.bank:
        total += check_bank(pathlib.Path(b), args.lang, args.phonemizer)
    if total:
        print(f'FAIL: {total} divergence(s) -> the bare hint and its {args.lang}/ spelling time differently.')
        print('  Fix: python tools/fix_dsdict_bare_types.py --bank <bank> --apply')
        return 1
    print(f'PASS: bare and {args.lang}/ spellings resolve and place identically -> identical timing.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

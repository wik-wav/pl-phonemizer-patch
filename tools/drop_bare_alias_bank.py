"""Drop the six bare shadow aliases (l ng r t w y) from EVERY phonemes.json in the given banks.

Why: with the patched plugin emitting pl/* (via its GetLangCode override), nothing produces these
bare names any more, and while present they SHADOW the en/* twins in OpenUtau's bare-first hint
resolution - which is the whole bug (bare 'r' -> Polish R instead of en/r, mistimed, no prefix).
Dropping them makes a bare English hint fall through to en/<x>: correct sound, timing and label.

The six are the deliberately un-merged en/pl pairs (l ng r t w y); merged pairs (b d f g k m n p s z
...) share one token id and are fine as bare aliases. Globals (cl SP AP q vf ...) must STAY.

Guarded: aborts (writes nothing) unless both en/<x> and pl/<x> twins exist for every dropped name.
Idempotent. Reversible by re-adding bare X -> pl/<X>'s id.

Usage:
  python drop_bare_alias_bank.py <bank_dir> [<bank_dir> ...] [--dry-run]

<bank_dir> is a voicebank root containing phonemes.json and its dsdur/ dspitch/ dsvariance/ copies.
"""
import json
import pathlib
import sys

DROP = ["l", "ng", "r", "t", "w", "y"]


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    dry = "--dry-run" in argv
    if not args:
        print(__doc__)
        return 2

    files = []
    for a in args:
        bank = pathlib.Path(a)
        if not bank.exists():
            print(f"!! not found: {bank}")
            return 2
        files.extend(sorted(bank.rglob("phonemes.json")))
    if not files:
        print("!! no phonemes.json found under the given bank(s)")
        return 2

    # guard pass over all files first - write nothing unless every file is safe
    problems = []
    for pj in files:
        toks = json.loads(pj.read_text(encoding="utf-8"))
        for b in DROP:
            if b not in toks:
                continue
            for twin in ("en/" + b, "pl/" + b):
                if twin not in toks:
                    problems.append(f"{pj}: bare {b!r} present but twin {twin!r} missing")
    if problems:
        print("GUARD FAILED - nothing written:")
        for p in problems:
            print("  !!", p)
        return 1

    for pj in files:
        toks = json.loads(pj.read_text(encoding="utf-8"))
        dropped = [b for b in DROP if b in toks]
        for b in DROP:
            toks.pop(b, None)
        if not dry:
            pj.write_text(json.dumps(toks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{pj}: {len(toks)} names, dropped {dropped or 'none'}  "
              f"en/r={toks.get('en/r')} pl/r={toks.get('pl/r')}")
    print("\n" + ("(dry run) nothing written" if dry else
                  "done. bare hints now fall through to en/<x>; plugin output resolves via pl/<x>."))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

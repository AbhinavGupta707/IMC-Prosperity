# Phase 8.5 hybrid-candidate pass — memo

One narrow follow-up pass to the Phase-8.5 memo. Built and ran
exactly four combined candidates on the Round-1 local replay (3 days
× 10 000 snapshots). **No new estimators, no PEPPER code changes, no
broad sweeps, no silent promotion.**

Candidate set:

| Label | PEPPER leg | ASH leg |
|-------|------------|---------|
| **Promoted** | shipped promoted PEPPER (`linear_drift, t=2.0, m=1.0, skew=2.0, flatten=0.7, h=32`) | shipped promoted ASH (`ewma_mid α=0.3, t=0.25, m=1.0, skew=4.0, flatten=0.7, h=48`) |
| **Alt** | shipped alt PEPPER (`linear_drift, t=2.0, m=1.0, skew=1.0, flatten=0.9, h=32`) | shipped alt ASH (`wall_mid, t=0.5, m=1.5, skew=4.0, flatten=0.7, h=48`) |
| **H1** | promoted PEPPER | alt ASH A1 (`wall_mid, t=0.5, m=1.5`) |
| **H2** | promoted PEPPER | A3 (`wall_mid, t=0.5, m=1.0`) |

Script: `outputs/round_1/phase8_5/run_hybrid.py`.
Raw table: `hybrid_shortlist.{csv,md}`.

---

## Results

| Candidate | total | ASH PnL | PEPPER PnL | ASH trades | ASH mk20 | ASH near-limit | PEPPER near-limit | PEPPER max-short-fh |
|-----------|------:|--------:|-----------:|-----------:|---------:|---------------:|------------------:|--------------------:|
| Promoted | +60 462 | +6 447 | +54 015 | 472 | +1.93 | 0 | 755 | −6 |
| **H2** | **+61 711** | +7 696 | +54 015 | 768 | +1.70 | 135 | 755 | −6 |
| **H1** | **+61 762** | +7 747 | +54 015 | 766 | +1.72 | 110 | 755 | −6 |
| Alt | +86 591 | +7 747 | +78 844 | 766 | +1.72 | 110 | **7 224** | −6 |

### Clean-isolation sanity check

The PEPPER columns for Promoted / H1 / H2 are **bit-identical**
(`trades=792`, `bucket 0-25=+1 264.5`, `max_short_first_half=−6`,
`near_limit=755`, `mk20=+3.43`). This confirms the ASH swap is a
truly isolated intervention — the local replay's per-product engines
don't interact across products.

### ASH detail, H1 vs H2

| | H1 (m=1.5) | H2 (m=1.0) |
|---|---:|---:|
| ASH PnL | +7 747 | +7 696 |
| ASH trades | 766 (9 mkr + 757 tkr) | 768 (6 mkr + 762 tkr) |
| ASH markout (20) | +1.72 | +1.70 |
| ASH entry edge | +2.08 | +2.07 |
| ASH near-limit steps | 110 | 135 |
| ASH final position | −9 | −9 |

H1 and H2 are statistically indistinguishable on PnL (ΔPnL = +51,
<1 %). H1's only edge is ~20 % fewer near-limit steps on ASH. H2's
narrower maker quotes (m=1.0) don't buy anything locally.

---

## Interpretation

### Does swapping ONLY the ASH leg beat promoted?

**Yes — by ~2 % locally.** The ASH leg from Alt (wall_mid, t=0.5,
m=1.5) adds +1 300 PnL vs promoted's ewma_mid leg, while PEPPER
stays on its validated promoted behavior (same early-day, same
max-short-first-half = −6, same near-limit exposure = 755).

The local +2 % ASH gain is consistent with the Phase-8.5A forensic
evidence: on official data, promoted ASH posted +720.91 and Alt ASH
posted +982.81 (+36 %). The local-to-official fill-model scaling is
~2× generous per the Phase-7 finding, so the expected official
uplift for H1/H2 is closer to the +260 official ASH gap than the
+1 300 local gap.

### Does H1 or H2 buy us Alt's upside without Alt's risk?

**Partially.** H1/H2 keep promoted PEPPER's tame inventory path
(755 local near-limit steps; officially 0 bucket-3 snapshots above
40 units) instead of Alt PEPPER's aggressive one (7 224 local steps;
officially 22 of 250 snapshots above 40 units in bucket 50-75k).
What H1/H2 recover is the **ASH uplift only** — ≈ +260 official PnL,
or ≈ 13 % of the +522 gap between Promoted (+2 518) and Alt
(+3 040). The other ≈ +262 of Alt's advantage over Promoted comes
from Alt PEPPER's larger long build, which H1/H2 don't touch.

So H1/H2 are **not a substitute for Alt** — they're a narrower,
lower-variance win that captures the structurally-justified ASH
improvement without adopting Alt PEPPER's higher-variance inventory
bet.

### Is H1 preferred over H2?

**Yes, but marginally.** H1 matches the shipped Alt ASH leg
verbatim — one empirical official-data point directly supports it.
H2 is a plausible sibling with the same fair-value choice but
narrower maker (m=1.0 instead of 1.5); locally it ties H1 on PnL and
adds a small ash_near_limit penalty (135 vs 110). There is no local
reason to prefer H2 over H1, and the official-data reason to prefer
H1 (it's the actually-tested config) is non-trivial.

---

## Explicit recommendation

**Prepare H1 as a revised upload candidate, but don't promote it
silently.**

Specifically:

1. **Default shipped bundle stays on Promoted** until a new upload
   empirically validates H1.
2. **H1 is the cleanest "next upload" option** available without
   code changes: it's Promoted's PEPPER leg (which official data
   validated as solid, final position −2) plus Alt's ASH leg (which
   official data validated as the best-performing ASH config).
3. **Do NOT upload H2** — no local or official evidence prefers it
   over H1, and it loses the one-config advantage of being exactly
   the previously-tested Alt ASH.
4. **Rotating to Alt instead** is still the higher-upside bet, but
   inherits Alt PEPPER's 9.6× near-limit exposure on a single data
   point of cross-day evidence. Reserve Alt for a separate upload
   slot, not as the default rotation.

### What this pass did NOT answer

- Whether H1 beats Promoted on the official fill model by a
  *statistically meaningful* margin. One upload slot would tell us.
- Whether the code-level PEPPER early-day fix flagged in Section E
  of the Phase-8.5 memo (first-25k sell-taker gate + early short
  cap) is worth building now, before or after uploading H1. That is
  a separate decision with separate evidence requirements.
- Whether H1's ASH leg holds up on cross-day local replay with
  stressed market microstructure. The 3-day local replay has thin
  regime variety; this is the same caveat as the Phase-8.5 memo.

---

## Files written

- `outputs/round_1/phase8_5/run_hybrid.py`
- `outputs/round_1/phase8_5/hybrid_shortlist.csv`
- `outputs/round_1/phase8_5/hybrid_shortlist.md`
- `outputs/round_1/phase8_5/hybrid_memo.md` (this file)

No edits to `src/core/config.py` or any other production module.

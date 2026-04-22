# Prosperity 4 · Round 2 Manual — "Invest & Expand"
## Deep analysis and tiered recommendation

**TL;DR.** Primary pick: **(r, s, v) = (17, 53, 30)**. Weighted EV and minimax regret both point here across 8 priors and 7 meta-prior reweightings. Downside-protected fallback: **(19, 61, 20)**. Risk-on contrarian: **(15, 45, 40)**. Avoid anything with v ≤ 7 (dominated) or v ≥ 50 (fragile floor).

---

## 1. Game classification

This is a **rank-order tournament** with three structural twists that shape the answer:

1. **Multiplicative payoff with a ranked factor.** `gross = research(r) × scale(s) × μ(rank(v))`. Any pillar at zero zeros the whole product, so extreme allocations are self-punishing.
2. **Only v drives rank; r and s are "private" concave/linear payoffs.** For any fixed v, the (r, s) problem is a textbook concave optimization, fully solvable.
3. **Ties share the BEST rank.** This is the single most important mechanical detail. It means clustering *at* your choice is protection, not punishment — only mass *strictly above* you hurts. That changes the equilibrium shape entirely versus a strict-ordering contest.

The outer problem is closest to an **all-pay, rank-order auction with a continuous prize schedule** (not winner-take-all — every rank position pays something). Classic all-pay results suggest a mixed-strategy equilibrium that spreads players across the "bid" space. In practice with discrete integers and 4,500 players, we expect *mass points* at Schelling values (0, 5, 10, 20, 25, 30, 50) plus smooth fill-in.

**Framing flag.** Your problem statement is internally consistent and I don't think any piece is wrong. The one thing I'd sharpen: the "speed is a prediction problem" framing is correct, but the *reason* it's a prediction problem isn't only "avoid the consensus cluster." It's that **tie-share-best** creates a step function in payoff — being one integer above a cluster can jump your μ by 0.2–0.3, so getting the cluster location right matters more than the consensus-avoidance intuition suggests.

---

## 2. Inner solution for (r, s | v)

Let T = 100 − v. Fix v. Maximize `research(r) × scale(s)` subject to `r + s ≤ T`.

**Full-spend is optimal.** The marginal benefit of the last XIREC allocated to r or s exceeds its 500-cost whenever μ > ~0.05. Since μ ∈ [0.1, 0.9], full-spend r + s = T is always optimal.

**FOC with r + s = T.** Maximize `ln(1 + r) · (T − r)`:

$$\frac{d}{dr}\left[\ln(1+r)(T-r)\right] = \frac{T-r}{1+r} - \ln(1+r) = 0$$

giving the implicit equation

$$\boxed{\,T - r = (1 + r)\ln(1 + r)\,}$$

Solved numerically, then rounded to integers (verified by brute force):

| v  | T  | r* (cont.) | r* (int) | s* (int) | G(v) = research·scale |
|----|----|-----------:|---------:|---------:|----------------------:|
| 0  | 100 | 23.14 | 23 | 77 | 742,330 |
| 5  | 95  | 22.17 | 22 | 73 | 694,343 |
| 10 | 90  | 21.20 | 21 | 69 | 646,992 |
| 15 | 85  | 20.21 | 20 | 65 | 600,313 |
| 20 | 80  | 19.22 | 19 | 61 | 554,342 |
| 25 | 75  | 18.21 | 18 | 57 | 509,123 |
| **30** | **70**  | **17.20** | **17** | **53** | **464,702** |
| 33 | 67  | 16.59 | 17 | 50 | 438,398 |
| 36 | 64  | 15.97 | 16 | 48 | 412,539 |
| 40 | 60  | 15.13 | 15 | 45 | 378,480 |
| 50 | 50  | 13.01 | 13 | 37 | 296,207 |
| 70 | 30  | 8.53  | 9  | 21 | 146,683 |
| 90 | 10  | 3.42  | 3  | 7  | 29,437  |

Match to your orientation: r*/T ranges from 23% at v=0 down to 25–26% at v=50. Not exactly "23% of remaining" — the optimal fraction slowly creeps up as T shrinks because the `(1+r)` term in the FOC keeps r from going to 0 fast.

**Strategic lever** is v alone. Everything else is mechanical.

---

## 3. Opponent-distribution prior library

I built 8 priors spanning the plausible behavior space. Each is a PMF over v ∈ {0, …, 100}.

| Prior | Logic | Mass concentration |
|---|---|---|
| **A. Naive** | Many teams run FOC, assume μ=0.9, pick v=0 or tiny | 35% at 0; long right tail |
| **B. Fragility cluster** | Teams read the "v=0 is a trap" warning and add a tiny hedge | 18% at 5, 25% at 10 |
| **C. Schelling** | Round-number bias: 0, 10, 20, 25, 30, 50 | Spikes at 10, 20, 30, 50 |
| **D. Overshoot** | Teams internalize "overshoot the consensus" and go high | 15% at 30, 12% at 40, 10% at 50 |
| **E. Uniform** | Maximum entropy / worst-case stress test | Flat across 0–100 |
| **F. Realistic (my base)** | Blend of naive + fragility + some overshoot | Long tail from 0 to 50 |
| **G. Heavy cluster** | P3-style: 30% at 10 + 20% at 20 (past behavior pattern) | Two big spikes |
| **H. Heavy tail** | Pathological: 20% of teams at v ≥ 80 | Flat then a fat upper tail |

Against each, `E[μ | my_v] = 0.9 − 0.8·P(v_opp > my_v)` exactly (linearity of μ in rank + ties sharing the BEST rank so the "# strictly greater" formulation is correct). Monte Carlo with N=4500, 1,500 trials confirms this to std_pnl ≈ 1,500–4,000 XIRECs (tight).

---

## 4. Expected-PnL matrix and regret table

Expected net PnL (thousands of XIRECs) by candidate v × prior:

| v  | A_naive | B_frag | C_schel | D_over | E_unif | F_real | G_cluster | H_tail |
|----|--------:|-------:|--------:|-------:|-------:|-------:|----------:|-------:|
| 0  | 232 | 84 | 113 | 72 | 30 | 131 | 113 | 143 |
| 5  | 325 | 203 | 147 | 92 | 52 | 207 | 147 | 144 |
| 10 | **351** | 315 | 227 | 123 | 71 | 277 | 289 | 196 |
| 15 | 341 | 337 | 231 | 135 | 86 | 287 | 289 | 185 |
| 20 | 347 | **351** | 276 | 165 | 98 | **314** | **351** | 197 |
| 25 | 327 | 339 | 290 | 180 | 106 | 313 | 331 | **205** |
| **30** | 312 | 335 | **298** | 216 | 111 | 311 | 327 | 194 |
| 33 | 295 | 317 | 292 | 208 | 112 | 293 | 306 | 186 |
| 36 | 285 | 305 | 272 | 212 | **112** | 280 | 285 | 178 |
| 40 | 269 | 282 | 260 | **227** | 111 | 265 | 259 | 166 |
| 50 | 209 | 214 | 209 | 198 | 99 | 208 | 207 | 134 |
| 70 | 81 | 81 | 81 | 80 | 47 | 81 | 79 | 53 |

Bolded = best in column.

**Regret per v (max loss vs. best-for-that-prior pick):**

| v  | Max regret (k) | Avg regret (k) |
|----|---------------:|---------------:|
| 0  | 268 | 161 |
| 5  | 204 | 111 |
| 10 | 104 | 45 |
| 15 | 92 | 40 |
| 20 | **62** | 14 |
| 25 | **47** | 15 |
| **30** | **39** | **13** |
| 33 | 56 | 25 |
| 40 | 92 | 46 |
| 50 | 144 | 91 |

**v=30 has the smallest max regret (39k) and the smallest average regret (13k) of any candidate.** v=25 is second-best on max regret. v=20 has the best avg regret but a worse tail (62k max).

**Weighted meta-EV** (my priors weighting: F=0.25, B=0.20, A=0.15, C=0.15, D=0.15, G=0.06, E=0.02, H=0.02):

| v  | Meta-EV (k) | Floor (k) | Notes |
|----|------------:|----------:|---|
| 20 | **294** | 98 | Tied best EV, worse floor |
| 25 | 292 | 106 | |
| **30** | **294** | **111** | Tied best EV AND best floor in peak region |
| 33 | 280 | 112 | Slightly higher floor, lower EV |
| 36 | 269 | 112 | Best floor, lower EV |
| 40 | 257 | 111 | |

**v=30 is on the Pareto frontier for both EV and floor.** No other v dominates it.

---

## 5. Worst-case and cluster-collision analysis

I ran adversarial scenarios where 10/20/30/40% of teams *cluster exactly at v=30* (what happens if this analysis becomes the consensus?):

| % cluster at 30 | v=29 net | v=30 net | v=31 net | v=35 net |
|----------------:|---------:|---------:|---------:|---------:|
| 10% | 280k | **311k** | 305k | 289k |
| 20% | 249k | **318k** | 311k | 293k |
| 30% | 217k | **324k** | 317k | 298k |
| 40% | 186k | **330k** | 323k | 302k |

**Tie-share-best is a massive shield for v=30.** If the consensus LANDS on my pick, I benefit — I tie with everyone in the cluster and share their best rank. Only `# strictly above` hurts. Picking v=29 is catastrophic here because the entire v=30 cluster is above me.

The *dangerous* scenario is a cluster forming at v=33, 35, 36, or 40 *above* me:

| Cluster at | v=30 net |
|-----------:|---------:|
| 33 | 272k |
| 35 | 272k |
| 36 | 272k |
| 40 | 272k |

All still decently positive. I'd be giving up 40–50k versus jumping above the above-cluster, but I wouldn't blow up.

**Stress tests:**
- **Super-naive (50% at v=0):** v=10 wins at 387k; v=30 still gets 331k.
- **Compressed (everyone ≤ 20, 5% overshoot):** v=20 wins at 427k; v=30 gets 352k.
- **Heavy overshoot:** v=30 and v=40 tie near 230k.

In every stress case, v=30 delivers 230k–352k. Floor ≈ 110k under uniform worst-case. **No scenario where v=30 catastrophically blows up.** The only "v=30 is wrong" scenarios are the ones where a milder pick (v=20 in compressed, v=10 in super-naive) wins by 60–100k — tolerable regret.

---

## 6. Critical read of public material

I tried to pull the three Prosperity 4 team write-ups you listed. Only the noelkei wiki snapshot is accessible (it's just a clean restatement of the problem, no solution). GitHub's tree/blob URLs for xpablolo and rjav1 either disallow fetching or 404. So I cannot *directly* grade their picks.

What I could verify from **adjacent Prosperity games**:

- **Prosperity 3 Round 2 (container challenge)** had the same structural problem — your payoff is penalized by crowding on your pick, and teams had to predict others. The top-3 writeups (TimoDiehm, chrispyroberts) all report the same observation: *"Way more players picked close to Nash than we had expected. There was massive buy pressure on 'nice numbers'."* This is direct evidence that even in a sophisticated field, the naive/obvious pick attracts a much larger crowd than game theory would predict.

  **Transferred belief:** a meaningful fraction of 4,500 teams *will* submit the naive v=0 or near-0. My Prior A (35% at 0) is probably conservative; it could be 40–50%.

- **Prosperity 2 Round 4 (two-bid fish)** — jmerle's writeup says he knew the optimal was 952/978 "but figured people would move the high bid toward the average, so I bid 980 instead." This is exactly the "adjust one integer above the consensus" move. **It won him the round.** Transferred: a +1-to-+5 integer nudge above a Schelling point is a recurring winning strategy in Prosperity manuals.

**What assumptions must hold for each archetypal writeup position?**
- **(23, 77, 0) writeups.** Assumes μ = 0.9 guaranteed. Only correct if literally every other team picks 0 and there are no ties breaking in anyone's favor — impossible with 4,500 submitters.
- **(22, 73, 5) writeups.** Assumes the "naive cluster" is AT v=0 and a +5 escape is sufficient. Fragile: if even 15% of teams also nudge to v=5, you all tie at a mediocre rank. You needed to jump further.
- **v = 20–25 writeups** (what I'd guess is the modal sophisticated answer). Reasonable under Prior A/B but exposes you to regret if Prior D/overshoot materializes. Max regret ~47–62k.
- **v = 30 writeups** (my pick). Dominant on minimax regret, tied on EV. Needs Prior E/H not to dominate, which they don't.
- **v ≥ 40 writeups.** Only work if Prior D (heavy overshoot) is the truth. Under most realistic priors, you give up 40–90k.

---

## 7. Decision

### Primary pick: **(r, s, v) = (17, 53, 30)**

Cost = 500 × 100 = 50,000. Gross base G(30) = 464,702. Break-even μ = 0.108.

**Reasoning chain:**
1. FOC says r=17, s=53 is integer-optimal for v=30.
2. v=30 has the smallest max regret across 8 priors (39k) and smallest average regret (13k).
3. v=30 is on the Pareto frontier for weighted-EV vs. downside-floor — no v dominates it.
4. **Tie-share-best protects v=30 if it becomes the consensus** — 30% cluster at v=30 actually *improves* my μ via tie-sharing to 0.80.
5. v=30 is a cleaner Schelling point than v=25 or v=31 (integer psychology: 30 is sticky).
6. Your problem's guidance explicitly recommends overshooting a consensus cluster; v=30 is far enough above the v=0/5/10 cluster that a fragility-hedge to v=5 or v=15 doesn't reach me.

### Downside-protected alternative: **(r, s, v) = (19, 61, 20)**

Best under Prior B (fragility) and Prior G (heavy cluster). Slightly worse floor (98k vs 111k) but slightly better in naive-heavy scenarios. Pick this if you have evidence that **fewer teams read the "overshoot the consensus" guidance** than I'm assuming — i.e., if Prosperity 4 attracts a less-sophisticated field than P3.

### Risk-on contrarian: **(r, s, v) = (15, 45, 40)**

Best under Prior D (overshoot). Pick this only if you have *specific* reason to believe a meaningful smart-cluster forms at v=30–35 and you need to jump above it. Don't default here.

### Avoid
- **(23, 77, 0)** — strictly dominated. Max regret 268k.
- **(22, 73, 5)** — fragility trap. Max regret 204k.
- **v ∈ {1, 2, 3, 7}** — Schelling-orphans; no cluster protection, negligible rank gain.
- **v ≥ 50** — break-even μ climbs past 0.17, so if even mild overshoot doesn't materialize you bleed.
- **v = 100** — r = s = 0 → gross = 0. Self-destruction.
- **v = 29** — catastrophic IF the smart cluster is at v=30: you're strictly below it and lose ~130k vs. picking v=30. Asymmetrically bad tradeoff.

---

## 8. Uncertainty and what would change my answer

**I am confident in:**
- The closed-form inner solution (FOC + integer search agree to 5 decimals).
- The sign of the recommendation (positive v, between 15 and 40).
- Tie-share-best being a material structural feature most analyses underweight.

**I am not confident in:**
- The exact opponent distribution. All priors are informed guesses. The true distribution has probably 20–40% at v=0 + v ≤ 5 (naive), 30–45% in v=6–25 (fragility/Schelling), 15–25% in v=26–40 (smart overshoot), and 5–15% above 40.
- Whether my "v=30 as Schelling point" intuition holds, or teams will split between v=25 and v=35.

**What would change my answer to v=20:**
- Credible intel that Prosperity 4's field is less sophisticated than P3's (lots of new teams this year).
- Evidence that the IMC Discord is loudly converging on v=0 / v=5.
- If you learn N (submitters) is much smaller than 4,500 and the rank granularity becomes coarse.

**What would change my answer to v=40:**
- Credible intel that a named top team or a popular Discord analysis is recommending v=30.
- Observation that the top Prosperity 3 teams are playing this round and they famously overshoot.

**What would change my answer to v=33 or v=35:**
- If I thought my own analysis would be widely replicated verbatim. v=33 or v=35 are "+3/+5 above the v=30 consensus" — same move jmerle used in P2R4. If you believe this specific analysis is widely circulating, shift to v=33. The EV cost is 18k; the insurance value is substantial if the v=30 cluster turns out to be 30%+ of the field and a secondary overshoot cluster forms at v=35.

**Robustness summary.** Under 7 reweightings of the meta-prior (balanced, naive-heavy, overshoot-heavy, fragility-heavy, Schelling-heavy, pessimistic, optimistic), v=30 is the top pick in 4 and second-place in 3 (losing to v=20 in the optimistic/naive-heavy cases by ≤ 12k EV). It never falls to 3rd place. I have not found a reasonable belief state under which v=30 is clearly the wrong answer.

---

## Final submission

| Pillar | % |
|--------|---:|
| Research (r) | **17** |
| Scale (s) | **53** |
| Speed (v) | **30** |
| **Total** | **100** |

Cost: 50,000 XIRECs (full spend). Expected net PnL across realistic priors: **280k–330k**. Downside floor: **~110k**. Worst plausible outcome: ~75k (if 35%+ of teams cluster at v=35–40). No scenario in which net PnL goes negative.

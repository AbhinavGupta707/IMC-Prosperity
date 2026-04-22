# IMC Prosperity 4 Round 2 Manual — Invest & Expand

## Final recommendation

**Primary submission:** **Research = 14, Scale = 40, Speed = 46**.

**Why:** I do not think the best play is the textbook low-speed allocation, and I also do not think the correct response is to chase all the way to 55–70. The strategic mass is likely around **35–46**, with a meaningful chance of public/AI/sophisticated overshoot into the low-to-mid 40s. **46** is high enough to clear the main 35/36/40/42 clusters, but not so high that the Research × Scale base collapses.

**Downside-protected strategic alternative:** **Research = 13, Scale = 37, Speed = 50**. Use this only if you believe a large public cluster forms around **46–50**. It is worse in my central model, but it protects against a “everyone overshoots to 50” field.

**Positive theoretical floor alternative:** **Research = 18, Scale = 57, Speed = 25**. This has a positive net floor even if you receive the minimum 0.1 speed multiplier, but it is too low-speed for my main recommendation.

I would **avoid**: `(23,77,0)`, `(22,73,5)`, most `v ≤ 30` unless you believe the field is extremely naive, and `v ≥ 55` unless you believe a real speed race is underway.

---

## One correction to the framing

The statement “any pillar at 0 zeros out gross” conflicts with the rest of the problem as written. If `v=0` truly zeroed the Speed pillar, then `(23,77,0)` would have zero gross and would not be a meaningful anti-pattern. I therefore treat **Research = 0** or **Scale = 0** as gross-zero, but treat **Speed** as the rank-based multiplier even when `v=0`, exactly as implied by the speed-rank formula and the warning about `(23,77,0)`.

The other important nuance: **ties are friendly**. A crowd exactly on your speed does **not** push you down, because rank is determined by the number of strictly higher speeds. The danger is not “many people pick my exact number”; the danger is “many people pick one step above me.”

---

# 1. Game classification

This is best classified as a **rank-order all-pay tournament with endogenous bid value**.

It is not a Tullock contest. In a Tullock contest, effort usually gives a probabilistic chance of winning. Here, effort in Speed gives a deterministic rank, and rank maps linearly into a multiplier. It is also not a standard first-price auction, because everyone “pays” through the opportunity cost of allocating budget to Speed, not only the winner.

The game has two layers:

1. **Production layer:** for fixed Speed `v`, allocate the remaining budget between Research and Scale.
2. **Rank layer:** choose `v` by forecasting the distribution of other teams’ `v`.

The official-style wiki mirror confirms the Round 2 manual task is a 50,000 XIREC allocation across Research, Scale, and Speed, with these as manual inputs. ([GitHub][1])

Because there are thousands of submitters, your own effect on the distribution is negligible. So the strategic object is not “how valuable is one more speed point?” in isolation. It is:

[
q(v)=\Pr(V_{\text{other}}>v)
]

and therefore

[
\mathbb{E}[\mu(v)] = 0.9 - 0.8q(v).
]

For expected value, `N = 4,500` mostly cancels out. It matters for variance, not mean. With 4,500 players, binomial rank noise is small; prior error about the crowd is the real uncertainty.

This is the same kind of manual-round workflow your internal manual plan recommends: classify the problem, write the payoff, solve the baseline, add crowd priors, simulate, and stress-test. 

---

# 2. Closed-form inner solution for `(r, s | v)`

For fixed `v`, let:

[
T = 100-v.
]

Assuming the budget cap is active, we set:

[
r+s = T.
]

The gross base before Speed is:

[
G(r,s)=
\frac{200000\ln(1+r)}{\ln(101)}\cdot \frac{7s}{100}.
]

The constants do not affect the Research/Scale split, so maximize:

[
f(r)=\ln(1+r)(T-r).
]

Differentiate:

[
f'(r)=\frac{T-r}{1+r}-\ln(1+r).
]

Set `f'(r)=0`:

[
\frac{T-r}{1+r}=\ln(1+r).
]

Let:

[
y=1+r.
]

Then:

[
T+1 = y(1+\ln y).
]

Let:

[
z=1+\ln y.
]

Then (y=e^{z-1}), so:

[
T+1 = ze^{z-1}
]

[
e(T+1)=ze^z.
]

Thus:

[
z=W(e(T+1)),
]

where (W) is the Lambert W function. Therefore:

[
y=\frac{T+1}{W(e(T+1))}
]

and:

[
r^*(T)=\frac{T+1}{W(e(T+1))}-1.
]

Then:

[
s^*(T)=T-r^*(T).
]

For integer submissions, evaluate the nearest integers around the continuous solution and choose the higher gross base.

Examples:

| Speed `v` | `T=100-v` | Integer optimal `(r,s)` | Gross base `G(r,s)` |
| --------: | --------: | ----------------------: | ------------------: |
|         0 |       100 |               `(23,77)` |              742.3k |
|        20 |        80 |               `(19,61)` |              554.3k |
|        36 |        64 |               `(16,48)` |              412.5k |
|        40 |        60 |               `(15,45)` |              378.5k |
|        46 |        54 |               `(14,40)` |              328.6k |
|        50 |        50 |               `(13,37)` |              296.2k |

For the economically relevant range `v ≤ 55`, full spending remains optimal even at the minimum multiplier `0.1`. For extreme speeds like `v=70` or `v=90`, the full-spend assumption can break under a very bad multiplier, but those candidates are dominated anyway.

---

# 3. Prior library

I used eight stress priors. These are not claims of exact truth. They are scenario tests.

Public writeups disagree materially. One public analysis builds a mixture with AI/Nash/just-above/classic/naive/high-speed/random components and recommends central `v=42`, conservative `v=46`. ([GitHub][2]) Another public context dump recommends `Research=13, Scale=37, Speed=50`, partly from empirical assumptions about a high sharp-optimizer rate; it also records a Round 1 manual perfect-score mass of 1,790 teams, or 37.3% of manual submitters. ([GitHub][3]) I treat those as **priors to test**, not as authorities.

Related Prosperity manual problems support the idea that crowding and “what others will do” matter, but the transfer is structural rather than numerical. The Prosperity 3 Neko writeup, from a team that reports 2nd in Manual, explicitly frames a crowding problem around estimating expected value and avoiding over-crowded obvious choices. ([GitHub][4]) The Prosperity 2 manual writeup similarly models expedition payoffs as being divided by other players’ destination shares and discusses maximin reasoning under unknown shares. ([GitHub][5])

My priors:

| Prior               | Meaning                                                        |
| ------------------- | -------------------------------------------------------------- |
| **Naive-low**       | Many teams underinvest in Speed or treat it as a tax.          |
| **Coast-edge**      | Extreme low-speed / coasting field.                            |
| **35-cluster**      | Heavy cluster around 33–37, with some just-above behavior.     |
| **Schelling**       | Round numbers, equal splits, 33/40/50, and just-above anchors. |
| **42/46-consensus** | Public/sophisticated cluster around 42–46.                     |
| **50-sharp**        | First-principles / overshoot cluster around 50–55.             |
| **Heavy-tail**      | Broad heterogeneous field: low, random, mid, high.             |
| **Speed-race**      | Many teams aggressively race to 50–80.                         |

---

# 4. Expected PnL by candidate speed

Values are **net PnL in thousands of XIRECs**, using the integer-optimal `(r,s)` for each `v`.

|  v | Naive-low | Coast-edge | 35-cluster | Schelling | 42/46-cons | 50-sharp | Heavy-tail | Speed-race |
| -: | --------: | ---------: | ---------: | --------: | ---------: | -------: | ---------: | ---------: |
|  0 |     137.3 |      256.0 |       29.1 |      44.1 |       24.8 |     27.0 |       56.3 |       27.0 |
|  5 |     202.5 |      334.3 |       31.2 |      54.3 |       24.4 |     25.9 |       80.4 |       25.9 |
| 10 |     268.9 |      379.6 |       34.5 |      72.0 |       23.4 |     25.4 |      102.5 |       25.4 |
| 15 |     284.8 |      384.0 |       34.2 |      75.1 |       21.9 |     23.1 |      110.6 |       23.1 |
| 20 |     306.0 |      381.9 |       36.4 |      88.1 |       20.5 |     21.5 |      117.7 |       21.5 |
| 25 |     309.3 |      361.8 |       41.4 |     101.9 |       19.8 |     19.6 |      118.6 |       19.6 |
| 30 |     298.9 |      329.9 |       50.4 |     113.0 |       19.9 |     16.9 |      115.0 |       16.9 |
| 33 |     292.4 |      318.5 |       78.7 |     139.8 |       31.4 |     21.2 |      116.5 |       16.0 |
| 36 |     278.6 |      299.9 |      187.7 |     194.9 |       87.6 |     54.0 |      145.2 |       14.4 |
| 40 |     258.9 |      274.8 |      208.5 |     199.0 |       90.8 |     57.3 |      143.0 |       11.8 |
| 44 |     232.7 |      246.6 |      208.6 |     195.1 |      163.5 |     88.6 |      150.2 |       47.2 |
| 50 |     199.0 |      207.8 |      192.1 |     183.3 |      173.8 |    117.3 |      135.2 |       69.2 |
| 55 |     166.9 |      174.0 |      166.9 |     158.1 |      159.4 |    140.6 |      116.7 |       83.1 |
| 70 |      77.8 |       79.9 |       78.2 |      76.9 |       76.2 |     72.6 |       60.9 |       57.0 |
| 90 |     -23.8 |      -23.6 |      -23.8 |     -23.8 |      -23.8 |    -23.8 |      -24.5 |      -23.9 |

Candidate-table reading:

* If the field is genuinely low-speed, `v=20–25` wins.
* If the field clusters around `35–40`, `v=40–44` wins.
* If the field clusters around `42–46`, `v=46–50` wins.
* If the field clusters around `50+`, `v=50–55` wins.
* `v=70` and `v=90` are bad: too much Research/Scale is sacrificed.

---

# 5. Regret table

Regret is measured against the best candidate within that prior. Values are in **thousands of XIRECs**.

|  v | Naive-low | Coast-edge | 35-cluster | Schelling | 42/46-cons | 50-sharp | Heavy-tail | Speed-race | Max regret | Mean regret |
| -: | --------: | ---------: | ---------: | --------: | ---------: | -------: | ---------: | ---------: | ---------: | ----------: |
|  0 |     172.0 |      128.0 |      179.5 |     154.9 |      149.0 |    113.6 |       93.9 |       56.1 |      179.5 |       130.9 |
|  5 |     106.8 |       49.7 |      177.4 |     144.6 |      149.4 |    114.7 |       69.8 |       57.2 |      177.4 |       108.7 |
| 10 |      40.4 |        4.3 |      174.1 |     126.9 |      150.4 |    115.2 |       47.7 |       57.7 |      174.1 |        89.6 |
| 15 |      24.5 |        0.0 |      174.5 |     123.9 |      151.9 |    117.5 |       39.6 |       60.0 |      174.5 |        86.5 |
| 20 |       3.3 |        2.1 |      172.2 |     110.9 |      153.3 |    119.1 |       32.5 |       61.6 |      172.2 |        81.9 |
| 25 |       0.0 |       22.1 |      167.2 |      97.1 |      154.0 |    121.0 |       31.6 |       63.5 |      167.2 |        82.1 |
| 30 |      10.4 |       54.1 |      158.3 |      86.0 |      153.9 |    123.7 |       35.2 |       66.2 |      158.3 |        86.0 |
| 33 |      16.9 |       65.5 |      129.9 |      59.2 |      142.4 |    119.4 |       33.7 |       67.2 |      142.4 |        79.3 |
| 36 |      30.7 |       84.0 |       20.9 |       4.1 |       86.2 |     86.6 |        4.9 |       68.7 |       86.6 |        48.3 |
| 40 |      50.4 |      109.2 |        0.1 |       0.0 |       83.0 |     83.3 |        7.2 |       71.3 |      109.2 |        50.6 |
| 44 |      76.6 |      137.3 |        0.0 |       3.9 |       10.3 |     52.0 |        0.0 |       35.9 |      137.3 |        39.5 |
| 50 |     110.3 |      176.2 |       16.6 |      15.7 |        0.0 |     23.3 |       15.0 |       13.9 |      176.2 |        46.4 |
| 55 |     142.4 |      210.0 |       41.7 |      40.9 |       14.4 |      0.0 |       33.5 |        0.0 |      210.0 |        60.4 |
| 70 |     231.5 |      304.0 |      130.5 |     122.1 |       97.6 |     68.0 |       89.2 |       26.1 |      304.0 |       133.6 |
| 90 |     333.1 |      407.6 |      232.4 |     222.8 |      197.5 |    164.4 |      174.7 |      107.0 |      407.6 |       229.9 |

Among the listed candidates, `v=44` has the best mean regret. But because the actual optimum is not restricted to the candidate set, the local neighborhood matters more. Testing all integer speeds gives my best central pick at **v=46**.

---

# 6. Worst-case floors

The theoretical floor assumes you receive the minimum speed multiplier `0.1`:

[
\text{floor}(v)=0.1G(v)-50000.
]

|  v |  r |  s | Gross base, k | Floor at μ=0.1, k |
| -: | -: | -: | ------------: | ----------------: |
|  0 | 23 | 77 |         742.3 |              24.2 |
|  5 | 22 | 73 |         694.3 |              19.4 |
| 10 | 21 | 69 |         647.0 |              14.7 |
| 15 | 20 | 65 |         600.3 |              10.0 |
| 20 | 19 | 61 |         554.3 |               5.4 |
| 25 | 18 | 57 |         509.1 |               0.9 |
| 30 | 17 | 53 |         464.7 |              -3.5 |
| 33 | 17 | 50 |         438.4 |              -6.2 |
| 36 | 16 | 48 |         412.5 |              -8.7 |
| 40 | 15 | 45 |         378.5 |             -12.2 |
| 44 | 14 | 42 |         345.0 |             -15.5 |
| 46 | 14 | 40 |         328.6 |             -17.1 |
| 50 | 13 | 37 |         296.2 |             -20.4 |
| 55 | 12 | 33 |         256.8 |             -24.3 |
| 70 |  9 | 21 |         146.7 |             -35.3 |
| 90 |  3 |  7 |          29.4 |             -47.1 |

Only `v ≤ 25` has a positive adversarial floor. That does **not** make `v≤25` optimal; it means low-speed plays are safe only in a literal worst-case-floor sense. They give up too much if the field is strategically aware.

---

# 7. Cluster trap analysis

Because ties are friendly, the math is:

[
\mu(v)=0.9-0.8\Pr(V_{\text{other}}>v).
]

A cluster exactly at your `v` does not hurt. A cluster just above you hurts a lot.

If 35% of the field is just above you, your multiplier drops by:

[
0.8 \times 0.35 = 0.28.
]

At `v=46`, with gross base about `328.6k`, that is:

[
0.28 \times 328.6k \approx 92k
]

of lost PnL. So the key is not avoiding your own tie; it is avoiding being below a likely public cluster.

Pairwise thresholds:

* `v=46` beats `v=42` if roughly **>9–10%** of the field is in `43–46`.
* `v=50` beats `v=46` if roughly **>10–11%** of the field is in `47–50`.

I think the first condition is more likely than the second. That is the core reason I prefer **46** over both **42** and **50**.

---

# 8. Critical read of public writeups

## xpablolo analysis

The xpablolo analysis is strong because it uses the correct tie-aware ranking engine, an exact integer Research/Scale solver, and an explicit mixture with AI, Nash, just-above, classic, naive, high-speed, and random components. It recommends central `v=42`, robust `v=42`, conservative `v=46`, and a defensible band `41–46`. ([GitHub][2])

My critique: its answer is highly dependent on the assumed AI/Nash/just-above mixture. If too many sophisticated teams react to the same analysis and move above 42, then 42 becomes slightly under-positioned. Its own conservative output, `v=46`, is closer to my conclusion.

## rjav analysis

The rjav context dump ends at `Research=13, Scale=37, Speed=50`, with a stated expected PnL around 181.8k. ([GitHub][3]) It also records a high Round 1 sharp-optimizer share, which is a real argument for taking the field seriously rather than assuming naive play. ([GitHub][3])

My critique: `v=50` is a good hedge against a high-sharp public cluster, but it sacrifices too much Research × Scale if the actual cluster sits in `35–46`. I would use `v=50` only if I believed a large fraction of active teams had converged to 50 or just below it.

## Different-game writeups

The Prosperity 2 and 3 manual crowding problems transfer one main lesson: **do not choose the obvious high-EV point without modeling crowd behavior**. But they do not transfer exact numbers, because those games had payoff sharing/crowding denominators, while Invest & Expand has a rank-order speed multiplier with friendly ties. ([GitHub][6])

---

# 9. Decision

## Primary pick

[
\boxed{(r,s,v)=(14,40,46)}
]

Estimated central-model net PnL: roughly **170k–175k XIRECs**, but I do not want to imply fake precision. The true uncertainty is the opponent distribution, not the arithmetic.

Why 46:

* Clears 35/36/40/42 clusters.
* Does not overpay as much as 50–55.
* Is the conservative end of the public 41–46 band.
* Performs well in the 35-cluster, Schelling, 42/46-consensus, and heavy-tail priors.
* Still does not catastrophically lose under low-speed priors.

## Alternative if you believe in a 50 cluster

[
\boxed{(r,s,v)=(13,37,50)}
]

This is a good “public overshoot insurance” choice. I do not make it primary because it needs a meaningful mass around 47–50 to justify the lower Research × Scale base.

## Alternative if you require positive adversarial floor

[
\boxed{(r,s,v)=(18,57,25)}
]

This is not my main EV-maximizing pick. It is the best “I want a positive minimum multiplier floor and I think the field may underinvest in Speed” pick.

---

# 10. What would change my answer?

I would move from **46 to 50** if I saw credible evidence that many teams were submitting or publicly recommending `v=50–52`.

I would move from **46 to 42–44** if I believed the field’s sharp cluster was mostly `35–40` and not reacting upward.

I would move from **46 to 20–25** only if I believed most R2 manual submitters were naive or coasting. Given the sharp Round 1 manual mass reported in public data, I do not believe that is the base case. ([GitHub][3])

My confidence is moderate, not absolute. This is a prediction problem about a sealed distribution. The arithmetic strongly identifies the important region; judgment determines whether the right point is 42, 46, or 50. My judgment is **46**.

[1]: https://github.com/noelkei/simplex-imc-prosperity-26/blob/main/docs/prosperity_wiki/rounds/round_2.md "simplex-imc-prosperity-26/docs/prosperity_wiki/rounds/round_2.md at main · noelkei/simplex-imc-prosperity-26 · GitHub"
[2]: https://raw.githubusercontent.com/xpablolo/imc-prosperity-4/main/round_2/manual/results/iteration4/manual_round2_summary_iteration4.md "raw.githubusercontent.com"
[3]: https://raw.githubusercontent.com/rjav1/prosperity4/main/research/COMPLETE_CONTEXT.md "raw.githubusercontent.com"
[4]: https://raw.githubusercontent.com/KengLL/Prosperity-3-Neko/master/README.md "raw.githubusercontent.com"
[5]: https://raw.githubusercontent.com/gabsens/IMC-Prosperity-2-Manual/master/Round3.ipynb "raw.githubusercontent.com"
[6]: https://raw.githubusercontent.com/KengLL/Prosperity-3-Neko/master/Manual/day2.ipynb "raw.githubusercontent.com"

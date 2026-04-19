# Invest & Expand — my solved view

## Bottom line

My **primary pick** is:

**(r, s, v) = (14, 42, 44)**

My **faster-field hedge** is:

**(13, 37, 50)**

My **literal downside-floor pick** is:

**(18, 57, 25)**

And the main ones I would **avoid** are:

**(23, 77, 0)**, **(22, 73, 5)**, and **very high speed like 90**.

The reason is simple: the inner optimization pushes Research/Scale into a predictable split, so the real game is mostly a **crowding game on `v`**. The trap is not “mispricing the payoff function.” The trap is “picking the same speed everyone else thinks is optimal.”

---

## 1) What game is this?

This is best thought of as a **discrete all-pay rank-order tournament with anti-coordination**.

Why:

* **All-pay**: whatever speed you choose, you pay for it through budget usage.
* **Rank-order tournament**: the speed payoff is determined by rank, not by absolute value.
* **Anti-coordination / congestion**: if many people choose the same “smart” `v`, that choice becomes worse.
* **Not a Tullock contest**: your speed payoff is not proportional to your share of effort; it is rank-based.

So the structure is:

1. Choose `v` to position yourself in the ranking game.
2. Given `v`, allocate the rest between `r` and `s`.
3. Because ties share best rank, **jumping just above a crowded integer matters a lot**.

---

## 2) Closed-form inner solution for `(r, s | v)`

Let

[
t = 100 - v
]

be the remaining percentage budget after choosing speed.

For fixed `v`, and assuming you use all remaining budget on research + scale, set

[
s = t-r
]

and maximize

[
\text{gross}(r) \propto (t-r)\ln(1+r)
]

since the constants (200{,}000/\ln(101)) and (7/100) do not affect the argmax.

So define

[
f(r) = (t-r)\ln(1+r)
]

Then

[
f'(r) = -\ln(1+r) + \frac{t-r}{1+r}
]

FOC:

[
\frac{t-r}{1+r} = \ln(1+r)
]

Let (x = 1+r). Then (r=x-1), and:

[
\frac{t-(x-1)}{x} = \ln x
]

[
\frac{t+1-x}{x} = \ln x
]

[
\frac{t+1}{x} - 1 = \ln x
]

[
t+1 = x(1+\ln x)
]

Now let (y=\ln x), so (x=e^y). Then:

[
t+1 = e^y(1+y)
]

Let (z=1+y). Then (y=z-1), giving:

[
t+1 = e^{z-1}z = \frac{z e^z}{e}
]

[
e(t+1)= z e^z
]

So:

[
z = W(e(t+1))
]

and therefore

[
x = \frac{t+1}{W(e(t+1))}
]

Hence the continuous optimizer is

[
\boxed{
r^*(v)=\frac{101-v}{W(e(101-v))}-1
}
]

and

[
\boxed{
s^*(v)=100-v-r^*(v)
}
]

Then round to the best nearby integers.

### Integer-optimal pairs for your candidate set

These are the exact best integer `(r,s)` splits for the listed `v` values in the normal full-spend region:

|  v |  r |  s |
| -: | -: | -: |
|  0 | 23 | 77 |
|  5 | 22 | 73 |
| 10 | 21 | 69 |
| 15 | 20 | 65 |
| 20 | 19 | 61 |
| 25 | 18 | 57 |
| 30 | 17 | 53 |
| 33 | 17 | 50 |
| 36 | 16 | 48 |
| 40 | 15 | 45 |
| 44 | 14 | 42 |
| 50 | 13 | 37 |
| 55 | 12 | 33 |
| 70 |  9 | 21 |
| 90 |  3 |  7 |

So your orientation rule was basically right: the optimum really does sit near **23% research / 77% scale of the non-speed budget**.

### One correction to your framing

That rule is **not universal**. It is correct in the economically relevant region, but for very high `v` and very low expected speed multiplier, the exact optimum can be **not** to spend the rest at all. For example, at `v=90`, if the expected multiplier is poor enough, the exact optimizer is effectively `r=s=0`. So “`r+s=100-v` always” is a very good approximation, not a theorem.

---

## 3) The key speed insight

Let (V) be an opponent’s speed choice, and define

[
q(v) = P(V>v)
]

Because ties share the **best** rank, your rank is:

[
\text{rank} = 1 + #{\text{opponents with strictly higher speed}}
]

If there are (N) total submitters, then:

[
#{\text{higher}} \sim \text{Binomial}(N-1, q(v))
]

and the speed multiplier is linear in rank, so

[
\mu(v) = 0.9 - 0.8\frac{\text{rank}-1}{N-1}
]

Taking expectations:

[
E[\mu(v)] = 0.9 - 0.8q(v)
]

So:

[
\boxed{E[\mu(v)] = 0.9 - 0.8P(V>v)}
]

### Big consequence

Under an i.i.d. field prior, **the expected multiplier does not depend on `N`**.
`N` only affects variance.

At your working assumption (N=4500), that variance is tiny. The maximum standard deviation is roughly

[
0.8\sqrt{\frac{0.25}{4499}} \approx 0.006
]

So this is overwhelmingly a **belief-about-field-distribution** problem, not a small-`N` lottery problem.

### The “just above” formula

Moving from `v` to `v+1` changes expected multiplier by

[
E[\mu(v+1)] - E[\mu(v)] = 0.8P(V=v+1)
]

That is the cleanest way to see why “sit just above a focal point” matters.

---

## 4) Prior library

I used six stylized opponent priors.

They are not “truth”; they are stress tests.

1. **Naive** — broad low/mid-speed crowd.
2. **Fragility-25** — many teams cluster around the obvious low/mid answer near 25.
3. **Schelling** — mass on focal integers.
4. **Public-mix** — approximate the only directly relevant public manual writeup I found.
5. **Heavy-tail** — meaningful right tail into the 50–70 range.
6. **Edge-high** — genuine speed-race / arms-race stress.

Before the numbers, a quick audit of the public resources you listed:

* the noelkei page is basically a **Round 2 mechanics summary**, not a serious manual-game strategy note;
* the `rjav1` writeup is about the **algorithmic round-2 bid/auction** and explicitly says the **manual round is handled separately**;
* the only directly relevant public manual analysis among the three is `xpablolo`, whose script builds a subjective mixture model with `MAIN_N = 50`, AI mass around 25 and 35, “just-above” focal values like 21/26/31/35/36/41/46/51, classic focal values like 20/25/33/34/35/40/50, a naive component centered at 32, a high-speed component centered at 64, and only small-`N` sensitivity cases up to 100. That makes it useful as a **crowding map**, but weak as a literal model for your stated (N\approx 4500). ([GitHub][1])

---

## 5) Expected PnL by candidate speed

All values below are **expected net PnL in thousands of XIRECs**.

|  v | Naive | Frag-25 | Schelling | Public-mix | Heavy-tail | Edge-high |
| -: | ----: | ------: | --------: | ---------: | ---------: | --------: |
|  0 |  35.2 |    24.2 |      40.4 |       24.5 |       24.2 |      24.2 |
|  5 |  47.5 |    19.4 |      59.8 |       21.1 |       19.4 |      19.4 |
| 10 |  72.7 |    14.7 |      85.3 |       17.5 |       14.8 |      14.7 |
| 15 | 115.6 |    10.4 |     110.4 |       13.8 |       12.0 |      10.0 |
| 20 | 195.0 |    42.7 |     146.5 |       17.8 |       14.4 |       5.4 |
| 25 | 274.1 |   200.6 |     182.3 |       46.8 |       37.7 |       0.9 |
| 30 | 309.7 |   295.9 |     195.9 |       67.0 |       63.1 |      -3.5 |
| 33 | 307.3 |   294.6 |     207.5 |      100.2 |       81.5 |      -6.2 |
| 36 | 300.5 |   302.9 |     240.3 |      167.9 |      109.1 |      -8.4 |
| 40 | 281.6 |   283.7 |     238.3 |      196.0 |      124.6 |      -4.0 |
| 44 | 256.5 |   258.2 |     235.4 |      205.2 |      141.8 |       5.6 |
| 50 | 215.7 |   216.6 |     208.0 |      189.7 |      145.7 |      24.0 |
| 55 | 180.9 |   181.1 |     177.4 |      163.4 |      139.5 |      47.4 |
| 70 |  82.0 |    82.0 |      80.9 |       78.5 |       77.1 |      58.7 |
| 90 | -23.5 |   -23.5 |     -23.5 |      -23.6 |      -23.5 |     -23.5 |

### Best `v` by prior, within your candidate grid

* Naive: **30**
* Fragility-25: **36**
* Schelling: **36**
* Public-mix: **44**
* Heavy-tail: **50**
* Edge-high: **70**

That already tells you the shape of the problem:

* if the field is **slower** than feared, 30–36 wins;
* if the field is **public-analysis-shaped**, 40s win;
* if the field is **genuinely fast**, 50+ wins.

---

## 6) Regret table

Again in **thousands of XIRECs**.

|  v | Mean EV | Min EV | Mean regret | Max regret | Worst μ=0.1 floor |
| -: | ------: | -----: | ----------: | ---------: | ----------------: |
|  0 |    29.7 |   24.2 |        10.7 |       16.2 |              24.2 |
|  5 |    33.5 |   19.4 |        26.4 |       40.4 |              19.4 |
| 10 |    41.0 |   14.7 |        44.3 |       70.6 |              14.7 |
| 15 |    52.5 |   10.4 |        63.1 |      105.2 |              10.0 |
| 20 |    83.3 |   14.4 |       111.7 |      180.6 |               5.4 |
| 25 |   148.3 |   37.7 |       125.8 |      236.4 |               0.9 |
| 30 |   186.3 |   63.1 |       123.4 |      246.6 |              -3.5 |
| 33 |   198.2 |   81.5 |       109.1 |      225.8 |              -6.2 |
| 36 |   224.1 |  109.1 |        78.8 |      193.7 |              -8.7 |
| 40 |   224.8 |  124.6 |        58.8 |      159.1 |             -12.2 |
| 44 |   219.4 |  141.8 |        38.7 |      116.3 |             -15.5 |
| 50 |   195.1 |  145.7 |        21.4 |       70.8 |             -20.4 |
| 55 |   168.4 |  139.5 |        12.6 |       41.6 |             -24.3 |
| 70 |    80.1 |   77.1 |         1.9 |        4.9 |             -35.0 |
| 90 |   -23.5 |  -23.6 |         0.0 |        0.1 |             -45.0 |

### What this says

* **40** has the highest **mean EV** in my six-prior library.
* **44** has the best **balanced robustness** among plausible serious picks.
* **50** is the best hedge against a faster field.
* **70** has tiny regret only because it is mediocre in almost every scenario and only decent in the high-speed stress.
* **90** is just bad.

This is why I do **not** pick 40 despite its slightly higher average in my stress set: it is more fragile to crowding extending into the low 40s.

---

## 7) Worst-case analysis

If you take the literal worst rank, so (\mu = 0.1), and re-optimize exactly:

* positive floor for **0, 5, 10, 15, 20, 25**
* first negative floor at **30**
* very negative by **44+**

So if by “downside protection” you mean **strict non-negative floor at the minimum multiplier**, the best serious candidate is:

**(18, 57, 25)**

Its worst-case floor is about **+0.9k**.

But that is **not** my main recommendation, because it gives up too much in the more plausible mid-30s to mid-40s crowding regimes.

A useful way to think about it is:

* **25** = floor-protected
* **44** = best balance
* **50** = hedge against faster-field overshoot

---

## 8) Critical read of the public writeups

My view after reading them:

### Noelkei

Useful for restating the round structure, but not useful for choosing `v`. It is a rules/mechanics summary. ([GitHub][1])

### rjav1

Not relevant to the manual problem. It is focused on the algorithmic auction/bid side of Round 2 and explicitly says the manual round is separate. ([GitHub][2])

### xpablolo

This is the only one that seriously engages with the manual speed game. Its strengths:

* models ties correctly through “strictly higher speeds only,”
* explicitly includes “just above focal number” behavior,
* recognizes that AI/public writeups can create endogenous clusters. ([GitHub][3])

Its weaknesses:

* the mixture is highly subjective,
* `MAIN_N = 50` and its sensitivity only runs up to 100,
* several components already encode a mid-20s to low-40s world before the model starts,
* so it is best treated as a **scenario generator**, not as a calibrated equilibrium estimate for a 4,500-team field. ([GitHub][3])

So I would **use xpablolo as evidence of where thoughtful public crowding may form**, not as a final answer.

---

## 9) Final decision

## Primary pick

**(14, 42, 44)**

Why:

* It overshoots the obvious 25/30/35/36/40 crowding band without paying the heavy gross-value penalty of 50+.
* It is the best compromise between upside and robustness in my stress tests.
* It remains positive across all six stylized priors I tested.
* It directly respects your warning that the “obvious rational answer” is a trap.

## Downside-protected alternative

I’d separate this into two meanings.

### If you mean “best robust alternative if the field is faster than expected”

**(13, 37, 50)**

### If you mean “strict non-negative downside floor at the worst multiplier”

**(18, 57, 25)**

## Candidates to avoid

* **(23, 77, 0)** — textbook but strategically naive.
* **(22, 73, 5)** — classic false-insurance pick.
* **30 / 33** — good only if the field stays slower than I think; too fragile to public clustering.
* **70** — only worth it if you believe a genuine speed arms race is underway.
* **90** — dominated.

---

## 10) What would change my answer?

I would move **down** from 44 toward **36–40** if I became convinced that:

* most teams will either not think strategically, or
* most teams will stop after the textbook inner optimization and pick something near the 20s/30s.

I would move **up** from 44 toward **50–55** if I became convinced that:

* public writeups and AI tools are being used heavily,
* many teams explicitly reason about “overshooting the cluster,” and
* the crowd is likely to create a real right tail.

What would make me choose **25** as the main pick? Only if my objective were explicitly **capital preservation** rather than maximizing expected net PnL under strategic uncertainty.

---

# Final answer

**Primary:** **(14, 42, 44)**
**Faster-field hedge:** **(13, 37, 50)**
**Strict floor-protected alternative:** **(18, 57, 25)**

If I had to submit one number, I would submit:

[
\boxed{(r,s,v)=(14,42,44)}
]

[1]: https://github.com/noelkei/simplex-imc-prosperity-26/blob/main/docs/prosperity_wiki/rounds/round_2.md "simplex-imc-prosperity-26/docs/prosperity_wiki/rounds/round_2.md at main · noelkei/simplex-imc-prosperity-26 · GitHub"
[2]: https://raw.githubusercontent.com/rjav1/prosperity4/main/research/r2_final_writeup.md "raw.githubusercontent.com"
[3]: https://raw.githubusercontent.com/xpablolo/imc-prosperity-4/main/round_2/manual/finalize_iteration4_analysis.py "raw.githubusercontent.com"

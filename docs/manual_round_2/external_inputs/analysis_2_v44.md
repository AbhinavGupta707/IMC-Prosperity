Here is the comprehensive analysis and solution for the Round 2 "Invest & Expand" manual challenge. 

### **1. Game Classification & The "Tie-Breaker" Anomaly**

At first glance, this resembles a continuous All-Pay Auction or a Tullock Contest, where players burn potential value (Gross PnL) to secure a higher rank multiplier ($\mu$). In standard continuous all-pay games, the optimal strategy involves a mixed distribution, and players heavily incentivize outbidding known clusters by a tiny fraction ($\epsilon$) to secure a massive rank jump.

However, the specific rule **"TIES SHARE THE BEST RANK"** radically alters the game theory. 

If you submit $v$, your rank is mathematically defined strictly by the number of opponents who bid *higher* than $v$:
$$Rank(v) = 1 + N_{>v}$$

**The Consequence:** The mass of people who bid exactly $v$ alongside you **does not penalize your rank**. If 2,000 teams play $v=30$, and you play $v=30$, you all receive the rank *above* the cluster. 
If you decide to "add a little insurance" and play $v=31$, your rank is $1 + N_{>31}$. You only gain rank equal to the number of people who played exactly $31$. You do not jump the 2,000 people at $v=30$—you were *already* ahead of them by tying with them. 

> **Strategic Takeaway:** You must land **exactly on** major psychological or rational Schelling points. Bidding $v+1$ to "beat the cluster" is a mathematical trap. It sacrifices Base Gross PnL without significantly improving your rank multiplier.

---

### **2. Inner Solution: Deriving $(r, s | v)$**

Assuming full spend ($r + s + v = 100$), let $K = 100 - v$. Thus, $s = K - r$.
For a fixed $v$ and multiplier $\mu$, maximizing Net PnL is equivalent to maximizing the Gross PnL function since the cost is fixed at $50,000$.

$$Gross(r) = \left( 200,000 \cdot \frac{\ln(1+r)}{\ln(101)} \right) \cdot \left( \frac{7(K-r)}{100} \right) \cdot \mu$$

We drop the constants to find the First Order Condition (FOC) with respect to $r$:
$$\frac{d}{dr} \left[ \ln(1+r) \cdot (K-r) \right] = 0$$
$$\frac{K-r}{1+r} - \ln(1+r) = 0$$

Let $x = 1+r$. Substituting $K = 100 - v$, the exact closed-form solution governing the optimal split is:
$$101 - v = x(1 + \ln x)$$

Because submissions must be integers, we test the two closest integer values of $r$ around the root of this equation to find the exact local maximum. 

**Optimal Splits for Key $v$ Candidates:**
* **$v=33$**: $x(1+\ln x) = 68 \implies r=17, s=50$. Base Gross $\approx 438,438$
* **$v=40$**: $x(1+\ln x) = 61 \implies r=15, s=45$. Base Gross $\approx 376,013$
* **$v=42$**: $x(1+\ln x) = 59 \implies r=15, s=43$. Base Gross $\approx 361,594$
* **$v=44$**: $x(1+\ln x) = 57 \implies r=14, s=42$. Base Gross $\approx 345,026$
* **$v=50$**: $x(1+\ln x) = 51 \implies r=13, s=37$. Base Gross $\approx 296,200$

*(Note: Base Gross assumes $\mu = 1.0$. Actual Gross will be Base $\times \mu$.)*

---

### **3. Opponent-Distribution Prior Library**

To evaluate the Speed multiplier ($\mu \in [0.1, 0.9]$), we must estimate the field's behavior. We define three plausible priors for the 4,500 active teams.

* **Prior A: The Naive / Uniform Spread**
    * **Logic:** The field is highly distributed. Many follow the pure $v=0$ FOC; others sprinkle bids evenly up to 50. 
    * **CDF $F(v)$:** $F(33)=0.60$, $F(40)=0.75$, $F(44)=0.82$, $F(50)=0.90$.
* **Prior B: The "Rational" Cluster (Github/Schelling)**
    * **Logic:** Teams run expected-value math assuming uniform opponents, yielding $v \approx 33$, or they default to round numbers ($40$). Massive clusters form here.
    * **CDF $F(v)$:** $F(33)=0.65$, $F(40)=0.85$, $F(44)=0.90$, $F(50)=0.95$.
* **Prior C: Level-k Unraveling (Paranoid)**
    * **Logic:** The field realizes 33 and 40 are traps. A massive wave of teams overshoots the consensus, heavily pushing the median into the high 40s and beyond. 
    * **CDF $F(v)$:** $F(33)=0.40$, $F(40)=0.60$, $F(44)=0.75$, $F(50)=0.85$.

---

### **4. Expected PnL & Regret Table**

Using the formula $\mu(v) = 0.1 + 0.8 \cdot F(v)$ (derived from the rank mapping), we calculate Expected Net PnL = $(BaseGross \times \mu) - 50,000$.

| Candidate $v$ | Optimal $(r, s)$ | Prior A (Naive) | Prior B (Cluster) | Prior C (Paranoid) | Worst-Case Floor |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **$v=33$** | (17, 50) | 204,200 | 221,800 | **134,100** | Highly Vulnerable |
| **$v=40$** | (15, 45) | 213,200 | **243,200** | 168,000 | Vulnerable |
| **$v=42$** | (15, 43) | 223,300 | **240,600** | 196,000 | Moderate |
| **$v=44$** | (14, 42) | **210,800** | 232,900 | **208,700** | **Robust** |
| **$v=50$** | (13, 37) | 192,800 | 204,700 | 181,000 | **Ironclad** |

---

### **5. Tiered Recommendations**

#### **Primary Pick: `(14, 42, 44)`**
* **Reasoning:** As the prompt warns: *"If many teams converge on the same rational answer, the median shifts against you... You may need to overshoot the consensus cluster."* The rational expected-value math yields 30–35. The obvious psychological wall is 40. The "smart quant" meme anchor is 42. 
* **Why 44?** By playing exactly $44$, you completely clear the devastating gravity of the $33$, $40$, and $42$ clusters. Because of the "best rank" rule, you don't care how massive those clusters get; they act as a floor that pushes the rest of the field down to $\mu = 0.1$ while keeping your multiplier securely in the $0.75 - 0.85$ range. The optimal FOC split at $v=44$ yields a highly efficient Base Gross of 345k, easily absorbing the 50k cost.

#### **Downside-Protected Alternative: `(13, 37, 50)`**
* **Reasoning:** $v=50$ is the ultimate psychological boundary. Allocating more than half your budget to a pure multiplier feels viscerally wrong to most players. If you believe the competition has completely unraveled and Prior C is too conservative, 50 guarantees you are in the top fractional percentiles of the field. Even in absolute worst-case unraveling, it nets $\approx 180,000$. 

#### **Candidates to AVOID (Anti-Patterns):**
* **$v \le 30$:** Mathematical suicide. You will be swallowed by the median and hit with $\mu \le 0.4$. Gross PnL will not cover the 50,000 cost.
* **The "Insurance" values ($v=31, v=34, v=41$):** Due to the *Ties Share Best Rank* rule, adding +1 to a Schelling point (like 30 or 40) causes you to lose thousands in Base PnL without leaping any meaningful amount of players. Never bid in the "no man's land" between major anchors.

### **6. Uncertainty & Robustness**
This recommendation assumes the field size remains large enough ($N \approx 4,500$) to smooth out wild idiosyncratic spikes and that a significant portion of teams are using public heuristics. If the active player base drops significantly and becomes dominated *only* by hyper-rational bots running Level-3+ models, the cluster could shift higher. However, human behavioral economics strongly dictate that $v=50$ acts as a hard upper bound for $>90\%$ of participants, cementing $v=44$ as the optimal risk-adjusted strike point.
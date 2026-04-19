# Round-2 test-upload variants — manifest

Built by `src/scripts/round_2/export_test_variants.py`. All bundles
use `bid=0` (MAF auction is ignored during testing). Upload these
to the IMC sandbox per the test plan and record results in
`outputs/round_2/test_uploads/log.md`.

## Bundles

| variant | size (bytes) | validator | SHA256 | purpose |
|---|---:|---|---|---|
| `round2_promoted` | 83995 | ✅ OK (0 error(s), 0 warning(s), size 83995 bytes) | `0e45bd7a5e7000db13e4d00c44e2e2490f29efa415a67bca4086b2572878fd7b` | Actual upload candidate. v5_micro PEPPER + wide_w113 ASH, kill switches DISABLED. Upload 3x to estimate noise floor from the 80% randomized quote subsample. |
| `round2_L1_ash` | 83979 | ✅ OK (0 error(s), 0 warning(s), size 83979 bytes) | `04ca7bb90c329159fb777af946c898d3c3085987c88f08544a45e4b62803fd4a` | Ablation: PEPPER unchanged, ASH = L1 ladder (R1 winner). Tests batch-D1 claim that wide_w113 > L1 on R2. If this scores >= round2_promoted average, wide_w113 is not real. |
| `round2_killswitches_on` | 84060 | ✅ OK (0 error(s), 0 warning(s), size 84060 bytes) | `07b870532acce60bd3f895baebacf5f532482a4b1599749c3193e55023645436` | Ablation: same as round2_promoted but with batch-B kill thresholds active. Tests batch-D2 claim that kill switches are redundant with v5_micro's existing guard. If this scores >= round2_promoted, kills DO help on the official sim. |
| `round1_v5micro_l1` | 84015 | ✅ OK (0 error(s), 0 warning(s), size 84015 bytes) | `98be4194167c901d8c2fb74293bc24ba609755b8e67fd7f68384d7a808ceeeec` | R1 winning bundle, unchanged. Simulator-consistency anchor: if this scores ~ R1 final scaled to 100k ticks (~+9k), the R2 simulator behaves like R1's. Materially different = R2 tape microstructure changed. |

## Reproduce

```bash
PYTHONPATH=. .venv/bin/python -m src.scripts.round_2.export_test_variants
shasum -a 256 outputs/submissions/round_2/test_variants/*.py
```

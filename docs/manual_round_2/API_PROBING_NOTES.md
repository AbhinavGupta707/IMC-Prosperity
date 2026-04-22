# P4-R2 API Probing — What's Possible

Compiled from published Prosperity 4 team repos (rjav1/prosperity4,
v-x-zhang/imc-prosperity-4-quantsc, JackMansfield2019, vasudnarendran,
Madhavan113, Palamabron). **No live probing by us.**

## TL;DR

**There is no API path to the live R2 speed-allocation distribution
before round close (2026-04-20 10:00 UTC).** The endpoint that
carries it (`/results/round/2/manual/data`) returns **401 mid-round**;
IMC intentionally seals it until after the speed rank is computed.
All submission / team endpoints are **team-scoped** — your Bearer
only returns your own data.

This means the IMC community Discord + polls are **literally the only
live empirical signal available**. The existing `discord_poll_raw_p4r2`
prior in our library is the ceiling of what live data can give us.

## IMC Prosperity 4 API (reverse-engineered, HAR-verified by rjav1)

**Base URL**: `https://3dzqiahkw1.execute-api.eu-west-1.amazonaws.com/prod`

**Auth**: AWS Cognito (`eu-west-1_wKiTmHXUE`, ClientId `5kgp0jm69aeb91paqj1hnps838`).
- `Authorization: Bearer <IdToken>`
- `Origin: https://prosperity.imc.com`
- `Referer: https://prosperity.imc.com/`
- Token lifetime ~1h; refresh via `POST https://cognito-idp.eu-west-1.amazonaws.com/`
  with `X-Amz-Target: AWSCognitoIdentityProviderService.InitiateAuth`.

### Endpoint map

| Method | Path | Purpose | In-round |
|---|---|---|---|
| GET | `/serverTime` | sanity ping | Yes |
| GET | `/rounds` | list rounds + `isActive` | Yes |
| GET | `/team` | your team info | Yes |
| GET | `/badges/team` | your badges | Yes |
| POST | `/submission/algo` | upload `.py` (≤100 kB) | Yes |
| GET | `/submissions/algo/{roundId}?page=1&pageSize=50` | your submissions | Yes |
| GET | `/submissions/algo/{sid}/zip` | log bundle | Yes post-sim |
| GET | `/submissions/algo/{sid}/graph` | PnL graph JSON | Yes post-sim |
| GET | `/submission/manual/{roundId}` | **your own manual pick** | Yes (404 before submit) |
| GET | `/leaderboard?type={OVERALL\|ALGO\|MANUAL}&page=N&pageSize=100` | global leaderboard | Yes (pageSize cap 100) |
| GET | `/results/round/{N}/manual/data` | **aggregate manual distribution** | **NO — 401 mid-round** |

## What we CAN do

1. **Confirm our own submission** via `/submission/manual/3` after submitting.
2. **Scrape the leaderboard** paginated — rjav1 pulled ~6k R1 rows. But
   manual-pillar breakdown is NOT exposed in leaderboard until round close.
3. **Monitor `/rounds`** to confirm R2 is still OPEN before last-minute
   resubmission.

## What we CANNOT do

1. See any other team's manual pick.
2. Extract the live speed-allocation histogram mid-round.
3. Know how many teams have submitted so far.
4. Any aggregate or distribution endpoint is sealed until post-close.

## Reference scripts (public, on GitHub)

- `rjav1/prosperity4/tools/get_token.py` — Cognito refresh helper
- `rjav1/prosperity4/tools/imc_client.py` — full end-to-end client
- `rjav1/prosperity4/tools/harvest.py` — minimal graph/zip downloader
- `vasudnarendran/TraderFactory/imc_prosperity.py` — pulls tokens from
  live Chrome tab via AppleScript (avoids Cognito entirely)
- `v-x-zhang/imc-prosperity-4-quantsc/round-2/leaderboard_scraper.py`
  — Playwright HTML scraper, rides logged-in session

### Sample working curl (from rjav1's HAR)

```bash
TOKEN=$(./get_token.py)  # requires Cognito refresh setup
curl -H "Authorization: Bearer $TOKEN" \
     -H "Origin: https://prosperity.imc.com" \
     -H "Referer: https://prosperity.imc.com/" \
  "https://3dzqiahkw1.execute-api.eu-west-1.amazonaws.com/prod/rounds"
```

## ToS / ethics

- IMC T&Cs prohibit reverse-engineering and undocumented automation.
- Teams who have scraped (rjav1, v-x-zhang) limit it to their own
  data reads. Aggregate/other-team extraction is not feasible anyway.
- Rate-limit is undocumented. Reference clients poll at 15s; Playwright
  leaderboard scrape at ~1 page/3 s hasn't triggered 429s per public
  reports.
- Scraping the **rendered leaderboard** (v-x-zhang's Playwright
  approach) is grey-area; hitting undocumented REST endpoints is
  riskier but also produces no additional signal here because the
  *distribution* endpoint is auth-sealed.

## Bottom line for R2 signal acquisition

Given that:
- The only valuable endpoint is 401-sealed
- Scraping alternatives provide no additional signal (leaderboard
  doesn't break out manual pillars)
- Community Discord is the ONLY live proxy

**No further scraping work is valuable.** Focus remaining effort on:

1. **Discord monitoring** during R2 final 24h — watch for late
   consensus commits, late polls, or a new thread.
2. **UI inspection** — manually open the submission page in your
   browser and check:
   - What's the default slider position for Speed? If v=50 or v=33,
     a Schelling cluster likely forms there.
   - Is there a visible "current submission count" or anything
     leaderboard-like on the page mid-round?
3. **Post-close retrospection** (2026-04-20 10:00 UTC onwards) — pull
   `/results/round/2/manual/data` to validate our prior against
   reality for future rounds.

Signal ceiling for this round: we have what we have (Discord poll).
The next round (R3) can use our actual R2 field data as a prior.

# ff-lineup-generator

Picks your ESPN fantasy football starters from Vegas player-prop lines. Free to run:
it uses The Odds API's free tier and nothing to install beyond Python.

## Setup (once)
1. **Python 3.9+.** Check with `python3 --version`. No packages to install.
2. **Free Odds API key.** Sign up at https://the-odds-api.com (Starter plan, $0).
   Create a file named `.env` in this folder containing exactly:
   ```
   ODDS_API_KEY=your_key_here
   ```
   Use `=`, not `:`. Get your own key rather than sharing one: each key gets
   500 credits a month.
3. **Add your league.** Copy `examples/myleague.txt` to `leagues/<name>.txt`
   (e.g. `leagues/work.txt`), set your scoring at the top, and paste your roster
   below it (see next section). One file per league; every file in `leagues/` runs.

## Each week
1. On ESPN, open **My Team**, select the whole roster table (starters and bench),
   copy it, and paste it over the old roster in your `leagues/<name>.txt`. Keep
   the `#` scoring lines at the top. Starting slots, flex spots, and injury tags
   (Q/D/O/IR) are read from the paste, so different league formats just work.
2. Run:
   ```
   python3 lineup.py -v
   ```
   You get the best lineup per league, your bench with projections, and the
   exact swaps to make versus your current ESPN lineup.

Options:
- `python3 lineup.py work`: run one league (file name without `.txt`)
- `-v`: show the stat line behind each projection
- `--dry-run`: show the credit cost without spending any
- `--refresh`: ignore cached odds (they're reused for 6 hours by default)

## Scoring
Defaults are ESPN standard **full PPR** (see `config.json`). Override any of them
with `# key = value` lines at the top of a league file:

```
# reception = 0.5     half PPR (0 for standard)
# pass_td = 6         6-point passing TDs
# int = -1
```

Keys: `pass_yd`, `pass_td`, `int`, `rush_yd`, `reception`, `rec_yd`, `td`, `pat`,
`fg_0_39`, `fg_40_49`, `fg_50_plus`, `fg_miss`, `dst_sack`, `dst_int`,
`dst_fumble_rec`, `dst_td`, `dst_points_allowed`, `dst_yards_allowed`. A typo'd
key stops the run with the list of valid keys.

## Credits
The free tier gives 500 credits a month. One credit buys one bet type (like
receiving yards) for one game, covering every player and every sportsbook, so a
run costs roughly 35 credits per league (~70 for two). Re-runs within 6 hours are
free. Props get posted through the week, so Saturday night or Sunday morning
gives the most complete lines and the latest injury news.

## How projections work
- **Yards and receptions:** the over/under line from each sportsbook, nudged up
  or down by how the odds lean (e.g. a juiced over), then averaged across books.
- **TDs:** anytime-TD odds become a probability, then expected TDs. Passing TDs and
  interceptions use their over/under odds the same way.
- **Kickers:** the books' kicking-points line plus an estimated bonus for long
  field goals. Until those lines post, it estimates from the team's expected points
  (from the spread and over/under).
- **D/ST:** the opponent's expected points and yards (from the game line and their
  QB/rusher props), plus the opposing QB's interception line. Sacks, fumbles, and
  return TDs use league-average baselines since books don't post them.
- **Players with no lines** (injured, or lines not posted yet) show `--` and are
  flagged so you can re-run closer to kickoff.

Data: [The Odds API](https://the-odds-api.com) for odds,
[Sleeper API](https://docs.sleeper.com) for player-to-team lookups.

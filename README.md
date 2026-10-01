# ff-lineup-generator

Picks fantasy starters from Vegas player-prop lines (The Odds API free tier, $0).

## Weekly use
1. On ESPN's **My Team** page, select the roster table, copy, and paste it over
   `leagues/netties.txt` / `leagues/fff.txt`. Starting slots are read from the paste.
2. `python3 lineup.py -v`

Options: `python3 lineup.py netties` (one league), `--dry-run` (credit cost only),
`--refresh` (ignore the 6-hour odds cache).

## Credits
Free tier = 500/month. A full run of both leagues costs ~70; re-runs within 6 hours
are free (cached). Props post through the week, so Saturday night / Sunday morning
runs have the most complete lines.

## Scoring
`config.json` holds ESPN default scoring; per-league overrides live under
`leagues.<name>.scoring` (Netties is half PPR).

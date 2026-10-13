---
demo: true
status: active
outcome: beta used by 10 friends for one growing season
---

# Kitchen Garden Planner

A small offline app that plans which vegetables go in which bed each season, following crop rotation rules.

## Scope for the beta
- Beds and plant families
- Rotation warnings (same family in the same bed two years in a row)
- Sowing calendar

## Technical choices
- Local SQLite database; no account and no cloud sync in the beta.

## Next steps
- Encode the rotation groups from [[Crop_Rotation]].

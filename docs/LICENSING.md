# Licensing recommendation

No license file is included yet. Until one is added, the code is "all rights reserved": people can read it but not
legally reuse it. Choose a license before the first public release.

## Third-party components

None. PersonalOS uses only the Python standard library and the SQLite library that ships with Python (public
domain). The UI uses no external fonts, scripts or icon sets; the logo is original. Nothing restricts the choice of
license.

## Options, given the plan (free core now, paid features later)

| License | Effect | Fits an open core with paid add-ons? |
|---|---|---|
| **Apache-2.0** (recommended) | Anyone may use, modify and sell it, including closed forks; includes an explicit patent grant and trademark clause | Yes. Paid features live in a separate, proprietary package. The name and logo stay yours (protect them as trademarks; Apache-2.0 grants no trademark rights). |
| MIT | Like Apache-2.0, shorter, no patent grant | Yes, slightly weaker protection |
| AGPL-3.0 | Anyone running a modified version as a service must publish their changes | Yes, and it deters hosted clones, but it also deters companies and contributors. Usually paired with a contributor license agreement (CLA) so you can sell commercial licenses. |
| FSL / BUSL (source-available) | Commercial use restricted for ~2-4 years, then converts to Apache/MIT | Strongest protection for a paid product, but "not open source", which costs community trust |

**Recommendation:** Apache-2.0 for the core repository. The core's value to users is trust (local, inspectable,
no lock-in), and a permissive license reinforces that. Keep premium functionality (sync service, AI processing
pipelines, polished desktop app) in a separate private repository under a commercial license, and register the
product name if you intend to sell under it. Add a `LICENSE` file and a short `NOTICE` when you decide.

This is a practical recommendation, not legal advice.

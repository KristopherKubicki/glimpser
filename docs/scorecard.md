# OpenSSF Scorecard

This repository uses the [OpenSSF Scorecard](https://github.com/ossf/scorecard) action to measure supply chain security best practices.

The workflow defined in `.github/workflows/openssf-scorecard.yml` runs weekly and on demand. It uploads the results to the repository's Security tab, which allows the public badge to display the latest score.

If the badge in the README shows "Scorecard report not found," make sure the workflow has run successfully at least once on the `main` branch.

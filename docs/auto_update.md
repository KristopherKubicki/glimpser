# Automatic Update

Glimpser can optionally update itself when a new release is published. Set
`AUTO_UPDATE_BRANCH` to `Main` or `Staging` to enable this feature. The running
instance checks hourly for the latest GitHub release targeting the configured
branch. If all CI checks for that commit pass, the release is installed via
`pip` and the process restarts automatically. Use `None` (the default) to
disable automatic updates.


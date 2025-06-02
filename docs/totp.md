# Enabling Two-Factor Authentication

Glimpser supports time-based one-time passwords (TOTP) for an optional second
authentication factor.

1. Install the extra dependency:
   ```sh
   pip install pyotp
   ```
2. Generate a secret for your user in the database. You can use the helper
   function `generate_totp_secret` from `app.utils.totp` and store the value in
   the `totp_secret` column.
3. Add the secret to your authenticator app (such as Google Authenticator).
4. When logging in, enter the current TOTP code along with your username and
   password.

If no `totp_secret` is set, the code field may be left blank and login proceeds
normally.

from __future__ import annotations

import secrets

import gpsoauth


def main() -> None:
    print("Google Keep master token bootstrap")
    print()
    print("1) Open https://accounts.google.com/EmbeddedSetup in your browser")
    print("2) Sign in and click 'I agree' if prompted")
    print("3) Open browser devtools and copy the oauth_token cookie value")
    print()

    email = input("Google account email: ").strip()
    oauth_token = input("oauth_token cookie value: ").strip()

    default_android_id = secrets.token_hex(8)
    android_id = input(f"Android ID [default: {default_android_id}]: ").strip() or default_android_id

    if not email or not oauth_token:
        raise SystemExit("Email and oauth_token are required.")

    try:
        response = gpsoauth.exchange_token(email, oauth_token, android_id)
    except Exception as error:  # noqa: BLE001
        raise SystemExit(f"Token exchange failed: {error}") from error

    master_token = response.get("Token")
    if not master_token:
        raise SystemExit(f"Token exchange did not return a Token. Full response: {response}")

    print()
    print("Copy this into your .env:")
    print(f"KEEP_EMAIL={email}")
    print(f"KEEP_MASTER_TOKEN={master_token}")
    print(f"# Android ID used: {android_id}")


if __name__ == "__main__":
    main()

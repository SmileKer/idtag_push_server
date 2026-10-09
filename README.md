# IDTag Push Service

Python service for registering IDTag mobile devices and delivering community-and-card-targeted notifications through Apple Push Notification service (APNs) and Firebase Cloud Messaging (FCM).

## Architecture

- The Flutter app registers its community code, resident card number, platform, and current push token over the HTTP API.
- An internal system submits a title, body, community code, resident card number, and optional data through a newline-delimited JSON TCP socket. An authenticated HTTP endpoint is also available.
- PostgreSQL stores active devices, queued notifications, and per-device delivery state.
- One background worker sends each delivery through APNs or FCM.
- A provider-accepted delivery is marked complete. A token reported as unregistered or invalid is deleted from `devices`.
- Once every delivery is either accepted or invalid, the notification and its delivery rows are deleted transactionally through `ON DELETE CASCADE`.
- Transient failures use exponential retry. A job is retained as `failed` after `MAX_ATTEMPTS` for operator inspection.

Important: APNs and FCM only acknowledge that they accepted a message. They do not prove that a phone displayed it or that a user read it. End-to-end delivery/read confirmation requires the app to call a separate acknowledgement endpoint; that is intentionally not claimed by this version.

## API

All `/v1/*` requests require `X-API-Key`. The production API listens on port 7004.

Register or refresh a device token:

```bash
curl -X POST http://127.0.0.1:7004/v1/devices \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: YOUR_API_KEY' \
  -d '{"community_code":"NORTH_01","card_number":"A123456","platform":"android","push_token":"TOKEN_FROM_FCM"}'
```

The same token can be registered repeatedly. The operation updates its card number and `last_seen_at`. The app should call it after login and whenever the push SDK refreshes the token.

Explicitly unregister on logout:

```bash
curl -X DELETE http://127.0.0.1:7004/v1/devices \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: YOUR_API_KEY' \
  -d '{"platform":"android","push_token":"TOKEN_FROM_FCM"}'
```

Internal HTTP submission:

```bash
curl -X POST http://127.0.0.1:7004/v1/push \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: YOUR_API_KEY' \
  -d '{"community_code":"NORTH_01","card_number":"A123456","title":"Package arrived","body":"Please collect it at reception","data":{"screen":"packages"}}'
```

## TCP socket protocol

The socket uses UTF-8 JSON, exactly one object per line. Each connection may send multiple lines. Maximum line size is 64 KiB.

Request:

```json
{"secret":"YOUR_SOCKET_SECRET","community_code":"NORTH_01","card_number":"A123456","title":"Package arrived","body":"Please collect it","data":{"screen":"packages"}}
```

Successful queue response:

```json
{"ok":true,"notification_id":"5c5ae3b9-7a26-45bd-a609-79106d1323fb","target_count":2}
```

Test with `python scripts/socket_client.py --secret ... --community NORTH_01 --card A123456 --title Test --body Hello`.

The production socket listens on port 7002. It uses plain TCP; the shared secret
authenticates requests but does not encrypt traffic. Restrict source addresses
at the outer firewall whenever possible.

## macOS push test UI

Double-click `開啟推播測試工具.command`. The launcher opens a local browser UI
at `http://127.0.0.1:8765`. The UI sends directly to the production TCP endpoint
at `211.23.22.158:7002`.
Enter a community code, card number, notification title, and message, and click `傳送推播`.

The local `.push_test_ui.json` stores the socket settings with mode `0600` and
is ignored by Git. The UI sends through the socket service; it does not contain
Firebase credentials.

Production public port mapping:

- `211.23.22.158:7001` currently forwards to Ubuntu SSH port 22.
- `211.23.22.158:7002` -> Windows `7002` -> guest `7002` for TCP push submission.
- `211.23.22.158:7003` -> Windows `7003` -> guest `7003` for SSH administration.
- `211.23.22.158:7004` -> Windows `7004` -> guest `7004` for mobile registration.

Port 7002 carries plain TCP. Restrict its source addresses at the firewall or
place it behind a VPN/TLS proxy when the sender has a stable network.

## Local setup

Python 3.10 or newer and PostgreSQL 14 or newer are recommended.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
# Edit DATABASE_URL, API_KEY, and SOCKET_SECRET.
python run.py
```

Database tables are created idempotently on startup from `sql/001_initial.sql`.

Run checks:

```bash
pytest -q
ruff check .
```

The helper `scripts/install_ubuntu.sh` installs the base Ubuntu packages and creates the locked-down service account. Database credentials are deliberately not embedded in that script or in source control.

Keep `DRY_RUN=true` until APNs and Firebase credentials are installed. Dry-run exercises registration, queueing, worker processing, and deletion without contacting either provider.

## Ubuntu deployment

Install packages and create the database:

```bash
sudo apt update
sudo apt install -y postgresql postgresql-contrib python3-venv
sudo -u postgres psql -c "CREATE USER idtag_push WITH PASSWORD 'USE_A_RANDOM_PASSWORD';"
sudo -u postgres psql -c "CREATE DATABASE idtag_push OWNER idtag_push;"
sudo useradd --system --home /opt/idtag-push --shell /usr/sbin/nologin idtagpush
sudo mkdir -p /opt/idtag-push
sudo chown idtagpush:idtagpush /opt/idtag-push
```

Copy the repository into `/opt/idtag-push`, create its virtual environment, and install `requirements.txt`. Store configuration in `/etc/idtag-push.env` with mode `0600`. Then install `deploy/idtag-push.service` under `/etc/systemd/system/`, run `sudo systemctl daemon-reload`, and enable the service.

## Provider credentials (later step)

For FCM, create a Firebase project, add the Android app with package name `com.idtag.online.idtage_online_version` and the iOS app with bundle ID `idtage.online`, enable Cloud Messaging, and download a service-account JSON file to a credential directory readable by the `idtagpush` service account only. Set `FCM_PROJECT_ID` and `FCM_SERVICE_ACCOUNT_FILE`.

For APNs, enable Push Notifications for the `idtage.online` Apple App ID, create a `.p8` APNs key, and set `APNS_TEAM_ID`, `APNS_KEY_ID`, `APNS_KEY_FILE`, and `APNS_TOPIC=idtage.online`. Use sandbox during development and production for TestFlight/App Store builds.

Each provider can be enabled independently. Install the Firebase service-account
JSON, set `FCM_PROJECT_ID` and `FCM_SERVICE_ACCOUNT_FILE`, then set
`DRY_RUN=false` and restart the service. The same FCM provider sends Android and
iOS notifications when the APNs key has been uploaded in Firebase Console. A
direct server-side APNs key is optional and takes precedence when configured.
Never commit `.p8`, service-account JSON, `.env`, or production secrets.

## App integration

The `idtage_online_version` Flutter app includes Firebase Core and Firebase
Messaging, notification permission handling, foreground/background handlers,
token refresh registration, saved community-and-card association, Android notification channel
setup, and iOS push capabilities. Its production registration endpoint is
`http://211.23.22.158:7004`.

Do not embed the server's privileged internal socket secret in the mobile app. The present API key is only a basic gate and can be extracted from an app binary; production registration should eventually be tied to the existing authenticated login/session.

## Development log

- 2026-10-09: Reviewed the legacy Flutter login and BLE beacon flow, then removed the original backend approval dependency. Resident setup now validates the daily engineering password locally, saves the card permanently, starts beacon broadcasting by default, and allows only beacon start/stop after binding.
- 2026-10-09: Integrated Firebase Cloud Messaging with Android and iOS, including permission handling, foreground notifications, token refresh, background handling, Android notification icon/channel setup, and automatic server registration. Firebase credentials remain outside Git.
- 2026-10-09: Built the Python push service with authenticated HTTP and TCP interfaces, PostgreSQL queueing, per-device fan-out, FCM delivery, invalid-token cleanup, exponential retry, tests, and a systemd service.
- 2026-10-09: Deployed the service to Ubuntu VM `172.10.1.51`. Established public ports `7002` for push submission, `7003` for SSH administration, and `7004` for App registration and health checks through `211.23.22.158`.
- 2026-10-09: Added the local browser-based push test tool and engineering handover/system architecture documents. Verified Android installation, BLE beacon switching, device registration, and end-to-end Firebase submission.
- 2026-10-09: Changed routing from card-only to the composite `community_code + card_number` key across the Flutter App, HTTP API, TCP protocol, test tool, PostgreSQL schema, indexes, and documentation. Existing device rows migrate safely to the `LEGACY` community.
- 2026-10-09: Released Android App `1.1.0+5`, deployed the composite-routing migration to production, backed up the previous application and database, and verified all public ports plus the external health endpoint. Production migration retained three existing device registrations; stale Firebase tokens continue to be removed automatically when rejected by FCM.

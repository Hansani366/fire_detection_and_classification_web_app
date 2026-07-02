# Firebase service-account key goes here

Drop the private key JSON here as **`firebase-sa.json`** so the backend can send
FCM push notifications (HTTP v1).

How to get it:
1. Firebase Console → your project → **Project settings** → **Service accounts**.
2. Click **Generate new private key** → a JSON file downloads.
3. Rename it to `firebase-sa.json` and place it in this folder.

`docker-compose.yml` mounts it read-only at `/secrets/firebase-sa.json` (the
`FIREBASE_CREDENTIALS` env var points there).

Until this file exists, alert-service still runs — it just **logs** pushes
instead of sending them, so you can test the rest of the pipeline first.

This folder is git-ignored; never commit the key.

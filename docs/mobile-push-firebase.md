# Mobile Push Setup

## Android app identity

Praina mobile currently uses:

- application id: `app.praina.mobile`
- frontend Capacitor config: [capacitor.config.ts](/home/luca/dev/code/praina/frontend/capacitor.config.ts)

## Firebase setup

1. Open Firebase Console.
2. Create a Firebase project or reuse an existing one.
3. Add an Android app with package name:

```text
app.praina.mobile
```

4. Download `google-services.json`.
5. Put it here:

```text
frontend/android/app/google-services.json
```

## Backend Firebase service account

Android client setup is only half of the path. The backend also needs Firebase Admin credentials to send FCM pushes.

1. In Firebase Console, open:
   - Project settings
   - Service accounts
2. Generate a new private key JSON.
3. Put it somewhere readable by the backend, for example:

```text
backend/firebase-service-account.json
```

4. Set these in `backend/.env`:

```text
FIREBASE_CREDENTIALS_PATH=backend/firebase-service-account.json
FIREBASE_PROJECT_ID=app-praina-mobile
```

`FIREBASE_CREDENTIALS_PATH` can be either:

- relative to the repo root, like `backend/firebase-service-account.json`
- relative to the backend folder, like `firebase-service-account.json`
- an absolute filesystem path

## What this enables

This is the Android prerequisite for real push notifications through FCM.

It does **not** by itself make Praina send push notifications yet.

## Current implementation status

Praina now already does this:

1. requests push permission on device
2. registers the device with Capacitor
3. sends the token to the backend
4. stores the token server-side
5. fans out backend notifications to FCM when Firebase Admin is configured

## Current mobile notification behavior

With the backend Firebase credentials configured:

- the mobile app refreshes unread notifications when the app returns to foreground
- the backend can send real Android push notifications through FCM
- tapping a push refreshes the in-app notification state

## Manual verification

After login on Android and after the device token is registered, you can trigger a test push with:

```text
POST /api/v1/auth/me/push/test
```

# keys/

Place your Google Cloud Translation service-account key here as:

```
google-translate-key.json
```

This folder is listed in `.gitignore` (except this README) so the real key
file is never committed to GitHub. `src/translation/google_translate.py`
picks it up automatically from this location, or you can point
`GOOGLE_APPLICATION_CREDENTIALS` at a different path.

To create a key:
1. Open the [Google Cloud Console](https://console.cloud.google.com/) and enable the Cloud Translation API for your project.
2. Create a service account and download its JSON key.
3. Save it as `google-translate-key.json` in this folder.

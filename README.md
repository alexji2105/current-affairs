Daily UP TET / Super TET Current Affairs PDF (free tools)

Runs on GitHub Actions at ~5:00 AM IST, builds the PDF for the PREVIOUS day, sends it to your Telegram (Gmail copy optional).

One-time setup
Gemini key (free): aistudio.google.com -> "Get API key".
India map file: download "States" from projects.datameet.org/maps (CC BY 4.0), convert/save as data/india_states.geojson (full India boundary incl. Kashmir). Open it once to check the boundary looks right.
Telegram bot: open @BotFather -> /newbot -> copy the token. Send any message to your new bot, then open https://api.telegram.org/bot<TOKEN>/getUpdates and copy chat -> id (for a channel: add the bot as admin; id starts with -100). (Optional Gmail copy: create an app password and add GMAIL_USER, GMAIL_APP_PASSWORD, MAIL_TO.)
GitHub: create a repo, upload all these files (keep the .github/workflows folder), then Settings -> Secrets and variables -> Actions -> add: GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID.
Test: Actions tab -> "Daily current affairs PDF" -> Run workflow (optionally give a date). The PDF arrives on Telegram (a failure message is sent too if the build breaks) and also saved under the run's "Artifacts".
Things to check
Feed URLs in FEEDS (main.py) open in a browser; fix any that changed. RSS keeps only recent items, so the 5 AM run is best.
Gemini model name: change GEMINI_MODEL if Google retires gemini-2.5-flash. Free limits change; CALL_GAP slows requests.
Natural Earth borders are not India's official ones; the script overlays the DataMeet India boundary on world maps.
Static facts are AI-written: spot-check dates and figures.
Credit: India boundaries by DataMeet (CC BY 4.0); world data from Natural Earth (public domain).
Diagrams/pictures are auto-fetched from Wikimedia Commons (free, licence credited under the image). Google Images is not used: its search API is closed to new users and scraping breaks its terms. India/world maps are drawn by the script so Kashmir is correct; Commons maps may show different boundaries.

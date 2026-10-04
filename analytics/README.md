# Bot visits archive

Daily archive is prepared but not active until the repository secret `CLOUDFLARE_LOGS_TOKEN` is configured and the first run succeeds.

The workflow runs daily around 09:17 Asia/Shanghai, recalculates the preceding two calendar days, and retains older daily CSV files. Repeated runs replace the same day's totals; they do not add duplicate visits. GitHub may delay scheduled runs.

Files in this directory are private and excluded from published website assets. They remain available in repository history after Cloudflare's short-lived logs expire. A gap longer than log retention cannot be recovered.

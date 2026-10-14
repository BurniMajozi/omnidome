# HomeDome commit and deployment handoff

The HomeDome commit preserves Claude's reference-library import and `/api/iot/reference` router registration in `services/iot/main.py`. It also preserves the lifecycle task controlled by `HA_REFERENCE_REFRESH_ENABLED`, enabled by default, alongside residential polling. Shutdown cancels and awaits both tasks. Tests check reference route registration, default-enabled refresh, explicit disablement and cancellation.

Claude's library implementation, worker, knowledge source and library tests remain in commit `800c7e95`. This change does not edit those files.

The HomeDome deployment script no longer creates timestamped `before-*` or `staged-*` image aliases. Backend builds return immutable image IDs through `--iidfile`; a supplied frontend is resolved to its immutable ID. Only existing runtime tags are updated during activation. Failure restores the original IDs, and one bounded `build_logs/homedome-rollback.images` file holds rollback metadata.

Frontend build helpers reuse the single `omnidome-homedome-web:candidate` tag and pass their own build's immutable ID into deployment. The deployment lock, disk reserve, concurrent-deployment check, managed-task check and health-based rollback remain in place. No image prune or service restart is performed for this handoff.

Docker tags are aliases. Disk growth comes from retained images, new layers and build cache. These changes avoid accumulating historical tag aliases; builds still create layers, and overlays based on the running image retain their ancestors. A later fresh-base rebuild and deliberate cache cleanup are separate storage work. Avoid pruning during the deployment's health-check/rollback window.

Validation: 91 IoT tests passed, including reference route registration and refresh lifecycle checks. Four isolated tests run the actual Bash deployment against fake external commands and cover success, rollback, concurrent-deployment refusal and frontend-only deployment. They passed without building images or touching running services. Generated customer TypeScript build metadata is excluded from version control, and local build outputs, credentials and `.codex` state are not part of the commit. Operator recovery helpers generate sensitive one-use links at runtime; their output must never be logged or committed.

The previously deployed reporting feature remains available in HomeDome → Reports. Advanced paid activation and physical-sensor/browser testing remain deferred as recorded in the reporting implementation document.

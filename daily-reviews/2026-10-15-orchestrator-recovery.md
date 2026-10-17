# Orchestrator recovery

The orchestrator, tenant memory, and FNO intelligence containers were stopped after the WSL/Docker restart. The default core startup profile omitted these services, so the active watchdog did not restore them. This explains the unreachable orchestrator and the unavailable FNO backend shown in the screenshot.

Started all three existing containers successfully. Added tenant_memory, agent-orchestrator, and fno_intelligence to both startup profiles, before the web service. Updated both the Windows source copy and the active WSL copy at /home/benedict/omnidome/scripts/start-local.sh. Staggered startup and capacity checks remain in place.

Validation: all three services return HTTP 200 from their health endpoints when called from the running web container. The watchdog is active, the active WSL script passes bash syntax validation, and the Windows repository passes git diff --check. Unauthenticated public proxy requests correctly return 401; a signed-in chat completion and signed-in FNO data request were not verified.

Refresh OmniDome and retry the chat message. The failed message will not automatically resend.

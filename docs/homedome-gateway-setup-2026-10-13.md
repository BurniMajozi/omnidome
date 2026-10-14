# HomeDome: new local home gateway

## Setup journey

1. On the gateway computer, open [Home Assistant onboarding](http://localhost:8123). Create your own administrator account and set your home location and Africa/Johannesburg timezone. No default password is supplied.
2. Open OmniDome → HomeDome (also available inside IoT). As Platform Owner, create a home using the real customer and verified customer login. If that login already has customer portal access, use its existing customer association. Portal access itself does not require a home.
3. Select that home and choose **Use prepared gateway for this home**. This pilot gateway can belong to only one home across the platform. Tenant admins cannot claim it or reassign it to another household.
4. Log in as the customer who owns that home. In Home Assistant, open your profile and create a long-lived access token. Enter it in HomeDome → Connection with `http://localhost:8123`. HomeDome encrypts the token before storage. Keep it out of chat, Git and screenshots.
5. Add devices through Home Assistant → Settings → Devices & services. HomeDome synchronises supported entities, real areas/rooms and configured integration status. Critical security controls stay in Home Assistant.
6. For Energy, select real cumulative meters in HomeDome → Energy → Configure meters. Missing readings remain unavailable. An optional rand/kWh tariff produces a measured grid-cost estimate.
7. Staff request support with a reference and reason; the customer approves diagnostics and, optionally, control/camera access for 5–60 minutes. The customer can revoke access at any time.

The local address works on the gateway computer. A phone or remote customer cannot use that computer's `localhost`; a properly authenticated private remote connection or a customer-site gateway is needed for that pilot stage.

## Deployment

The independent Docker Compose project is [homedome-gateway.yml](../deploy/commercial/homedome-gateway.yml). Run it with [prepare-homedome-gateway.sh](../deploy/commercial/prepare-homedome-gateway.sh) inside Ubuntu WSL with Docker Engine. It does not restart PostgreSQL, WSL or the platform.

- Pinned Home Assistant Container release: **2026.10.1**.
- Persistent named volume: `omnidome-home-assistant-config`. This contains the private home configuration and credentials; do not delete it or commit/export it to Git.
- Private bridge network: `omnidome-home-gateway`. The IoT service joins this network; credentials never go through a public proxy URL.
- Local onboarding port: `127.0.0.1:8123`. The existing ngrok tunnel on port 3000 does not expose Home Assistant.
- CPU ceiling: one core; memory ceiling: 1.5 GiB. Container log rotation is enabled.
- No privileged mode, host-network discovery, USB radios or Bluetooth access are enabled for this software pilot.

HomeDome's managed transport is opt-in at deployment and accepts only the fixed gateway hostname. Regular customer-supplied URLs continue through the existing SSRF checks. The database gateway binding has a globally unique key to prevent sharing a single Home Assistant instance between households.

Stopping or recreating the gateway preserves its named volume. Disconnecting it in HomeDome revokes support access but retains the household assignment. Moving it to another home requires an explicit operator process and clearing the prior household's Home Assistant data; there is no casual reassignment button.

## Integration readiness

HomeDome includes setup cards for Alexa, ESPHome, Google Assistant, Google Cast, HomeKit Bridge, IKEA TRÅDFRI, KNX, Lutron Caséta, Matter, MQTT, Philips Hue, Plex, Shelly, SmartThings, Sonos, Z-Wave and Zigbee Home Automation, plus Imou and ONVIF cameras. A **loaded** component is not proof of successful device pairing.

Home Assistant Container has no Supervisor app/add-on store. Matter Server, MQTT brokers, Zigbee/Z-Wave radios and any required companion services must be installed separately for actual hardware. Bridge networking also means multicast discovery is limited; manual device addresses may be required. For a permanent customer-site appliance, Home Assistant OS is usually the easier supported installation.

Imou needs the correct regional account/App ID/secret and authorised devices. Cloud video/API quotas and device capabilities vary; this setup does not imply free cloud recording or live video. HomeDome currently provides consent-controlled snapshots, not a live-stream relay.

Official references: [Linux installation](https://www.home-assistant.io/installation/linux/), [REST API](https://developers.home-assistant.io/docs/api/rest/), [Imou integration](https://www.home-assistant.io/integrations/imou/), [Matter](https://www.home-assistant.io/integrations/matter/), [ZHA](https://www.home-assistant.io/integrations/zha/).

## Verification and remaining pilot steps

**Deployment completed on 13 October 2026.** The gateway is running and onboarding responds at [localhost:8123](http://localhost:8123). The main [HomeDome workspace](http://localhost:3000/dashboard/home-dome) and [customer login](http://localhost:3001/login) both respond successfully. IoT reaches Home Assistant over its private Docker network; unauthenticated Home Assistant and customer-proxy API calls return 401. The verified Supabase Platform Owner has gateway assignment enabled; tenant Owners do not. No gateway has been assigned to a household yet, and Home Assistant is awaiting account setup.

The earlier disk-space incident is resolved following the user's cleanup. Windows C: had about 8.3 GiB free at the final deployment checks. Setup now checks for 8 GiB before an initial gateway download; platform deployment checks for 3 GiB before rebuilding. No user configuration or database volumes were deleted. The deployment rollback image stamp is `20261013153244`. These source changes are not yet committed or pushed.

The IoT suite passes **61 tests**, covering household isolation, consent, real energy calculations, fixed gateway targets and one-home assignment. This live deployment passed **11 rollback-only PostgreSQL checks**, including the gateway's unique household binding, and verified the three HomeDome workflow events. All probe rows were rolled back. Main web and customer production builds succeeded; the shared HomeDome UI copies match. Physical device pairing, customer token validation and camera/energy readings still require onboarding and real hardware. No customer home or sensor data was invented for this deployment.

Browser visual and authenticated interaction checks remain outstanding. The technician prototype has a passing type check, while its standalone production build remains unverified. The technician view inside the main web app is deployed.

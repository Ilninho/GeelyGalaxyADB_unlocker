# Geely Galaxy ADB unlocker — work in progress

This repository is a local-broker implementation based on the verified
`GeelyGalaxy_ADB` MQTT/DNS approach. The source and one-file build workflow
exist, but **no Windows or on-car acceptance test has been completed**.

## Origin and support

This application develops the idea of [Ruslan Spaceyard](https://www.drive2.ru/users/spaceyard/).
His [original GeelyGalaxy_ADB repository](https://gitverse.ru/spaceyard/GeelyGalaxy_ADB)
contains the broker and client that inspired this local version. Credit for
that original work belongs to Ruslan.

This project is free for noncommercial use under the terms in [LICENSE.md](LICENSE.md).
If you would like
to buy me or Spaceyard a beer, please consider a small monthly donation to a
charity instead. It can cost less than a cup of coffee and helps people beyond
this project. I recommend making it a recurring habit.

My original code is licensed under PolyForm Noncommercial 1.0.0. Ruslan granted
permission to modify and distribute the parts derived from his code for
noncommercial use; the original repository does not publish a general license.
The PolyForm license does not claim ownership of his work. MIT and GPL permit
commercial use, so neither would express this project's noncommercial terms.

## Intended local flow

1. The Windows launcher starts Mobile Hotspot when it is not already on.
2. The head unit joins that hotspot over Wi-Fi. A USB connection to the laptop
   is optional and is needed only for an `adb devices -l` check.
3. DNS on the laptop maps only `oneoss-ecu-mqtt.geely.com` to the hotspot's
   local IPv4 address and forwards other names normally.
4. An MQTT/TLS broker on the laptop listens on TCP 8883 and sends the existing
   `ADBSwitch=ON` command after the car authenticates and subscribes.
5. On normal exit, the program restores the adapter's previous IPv4 DNS mode
   and addresses and removes only firewall rules it created. It saves a
   snapshot before editing and retries recovery at the next launch after an
   abrupt stop. Restoration at the moment of a hard kill or power loss is not
   guaranteed.

The working remote-server sequence is documented in the original project.
The local launcher is `unlocker.py`; the original broker protocol lives in
`broker.py`. On Linux and macOS, `--broker-only` works with a certificate, but
automatic hotspot and DNS configuration is currently Windows-only.

## TLS certificate and DNS ownership

For P145 / IHU039G, the installed CloudAuthService uses the Android trust
store for its MQTT TLS connection. It disables hostname verification, but its
default X.509 trust manager still checks the certificate chain. A certificate
generated and self-signed on a user's Windows laptop is not automatically
trusted by the car. The original VPS succeeded using a publicly trusted
certificate. Therefore a self-signed local broker must first be tested on the
actual head unit; its success is not established by a local TLS test.

A dedicated free DNS name, for example one registered at dynv6 with a
separate project email address, is the preferred release option. dynv6
supports DNS TXT records for an ACME DNS-01 challenge. The DNS account/token
is used only by the maintainer during issuance and renewal; it is never embedded in the executable
or given to end users. No DNS access to a personal domain is required. The
maintainer supplies the PEM chain and key as GitHub Actions secrets, and the
build embeds them in the executable. End users need no domain, token, Python
installation, or runtime VPS. An A record is not required for the car: the
laptop's local DNS redirects the car's MQTT hostname to the hotspot address.

**A private key embedded in a public executable can be extracted by anyone.**
Use a certificate and key dedicated to this tool; never reuse a website or VPS
key. Renew the certificate and rebuild the executables before expiry. The DNS
provider token grants control of the dedicated free name only and must stay
outside the repository and release binaries.

The current release certificate is for `geely-unlocker.dynv6.net`. It was
issued by Let's Encrypt using DNS-01 with an RSA key and a chain to ISRG Root
X1; it expires on 9 January 2027. The DNS token is kept outside the repository.
The certificate and key are also excluded from Git. Renewal and rebuild are
the maintainer's responsibility. Trust by the actual head unit remains to be
verified on the car.

Other options are a user-supplied trusted certificate (`--cert` and `--key`),
or a local CA installed on the head unit before running this tool. A locally
self-signed certificate alone does not establish trust on the car.

## Running and building

For source development, install Python dependencies and run
`python unlocker.py --cert /path/fullchain.pem --key /path/privkey.pem` on
Windows as Administrator. The program attempts to start Mobile Hotspot. If
the Windows API refuses access, enable Mobile Hotspot in Settings first and
run it again. Linux/macOS currently use `--broker-only` and require manual
Wi-Fi/DNS configuration.

For one-file releases, set repository secrets `TLS_FULLCHAIN_PEM` and
`TLS_PRIVATE_KEY_PEM` to the PEM certificate chain and private key for a
dedicated project certificate. Run the **Build standalone executables**
workflow manually.
Its artifacts include the Python runtime; end users do not install Python.
Builds are made separately on Windows, Linux, and macOS. The certificate is
never committed to this repository. A local macOS arm64 binary was built and
its TLS handshake verified. The first [GitHub Actions run](https://github.com/Ilninho/GeelyGalaxyADB_unlocker/actions/runs/38171781378)
completed successfully on all three platforms. Download the [Windows ZIP from the preview release](https://github.com/Ilninho/GeelyGalaxyADB_unlocker/releases/download/v0.1.0-preview/GeelyGalaxyADBUnlocker-Windows.zip).
It contains a single x86-64 `GeelyGalaxyADBUnlocker.exe`; the Windows runner
started it with `--help`. The Windows hotspot and on-car flow still require
acceptance testing.

The same release also provides [Linux x86-64](https://github.com/Ilninho/GeelyGalaxyADB_unlocker/releases/download/v0.1.0-preview/GeelyGalaxyADBUnlocker-Linux.zip)
and [macOS arm64](https://github.com/Ilninho/GeelyGalaxyADB_unlocker/releases/download/v0.1.0-preview/GeelyGalaxyADBUnlocker-macOS.zip)
archives. Each contains one executable. Run it with `--broker-only`; hotspot
and DNS setup on those systems is manual. Both builds passed their CI tests
and started with `--help` on their respective runners.

## Manual Linux setup

You need NetworkManager, a Wi-Fi adapter that supports access-point mode, and
internet access through Ethernet or a second Wi-Fi adapter. The executable
already includes Python. Install the `dnsmasq` binary if it is missing (the
package may be called `dnsmasq-base`); NetworkManager uses it for DHCP and DNS
with `ipv4.method shared`. Do not start a separate dnsmasq service. The
`/etc/NetworkManager/dnsmasq-shared.d/` directory is supported by current
NetworkManager but is not a stable interface; check your installed version
([NetworkManager documentation](https://networkmanager.pages.freedesktop.org/NetworkManager/NetworkManager/nm-settings-nmcli.html)).

1. Extract the Linux ZIP and run `chmod +x GeelyGalaxyADBUnlocker` in its
   directory. Find your Wi-Fi interface with `nmcli device status`. Replace
   `wlan0` and the example password below. First confirm that neither the
   `GeelyADB-AP` profile nor
   `/etc/NetworkManager/dnsmasq-shared.d/geely-adb.conf` exists; these commands
   create new settings and must not replace someone else's configuration.

   ```sh
   sudo nmcli device wifi hotspot ifname wlan0 con-name GeelyADB-AP ssid GeelyADB password 'your-wifi-password'
   sudo nmcli connection modify GeelyADB-AP ipv4.method shared ipv4.addresses 10.42.77.1/24
   sudo install -d /etc/NetworkManager/dnsmasq-shared.d
   printf '%s\n' 'host-record=oneoss-ecu-mqtt.geely.com,10.42.77.1' | sudo tee /etc/NetworkManager/dnsmasq-shared.d/geely-adb.conf
   sudo nmcli connection down GeelyADB-AP
   sudo nmcli connection up GeelyADB-AP
   ```

   `10.42.77.1` is an example network for this new connection; if it
   conflicts with an existing network, replace it in **both** lines.

2. Run `./GeelyGalaxyADBUnlocker --broker-only`. Allow incoming TCP 8883 and
   DNS UDP/TCP 53 on the hotspot interface if a local firewall is active.
   Connect the car to `GeelyADB`; reconnect it if necessary to renew its DHCP
   address and DNS settings.
3. After the session, stop the program with Ctrl+C and remove **only** the
   profile and DNS file created above:

   ```sh
   sudo nmcli connection down GeelyADB-AP
   sudo rm /etc/NetworkManager/dnsmasq-shared.d/geely-adb.conf
   sudo nmcli connection delete GeelyADB-AP
   ```

   These steps do not change the laptop's system DNS. Restore any other network
   settings you changed manually.

## Manual macOS setup

Use a local access point/router whose DHCP settings let you choose the DNS
server advertised to clients. The Mac and car must be on the same LAN; an
Ethernet connection from Mac to router and Wi-Fi from car to router is
convenient. Disable client isolation on the router if enabled. macOS
[Internet Sharing](https://support.apple.com/en-qa/guide/mac-help/mchlp1540/mac)
can create a Wi-Fi network, but does not expose a documented way to set its
DHCP clients' DNS server. Enabling it alone is insufficient for this flow.
The steps below use a router that offers the required setting.

1. Extract the macOS ZIP and run `chmod +x GeelyGalaxyADBUnlocker` in its
   directory. No Python installation is needed. Reserve a stable LAN address
   for the Mac in the router's DHCP settings, for example `192.168.50.2`.
   Record the router's previous DHCP DNS value and temporarily advertise
   `192.168.50.2` as the **only** client DNS server. Replace this example IP
   with your Mac's actual LAN address below. Temporarily disable any other
   DNS advertised by the router, including IPv6 DNS.
2. Install [dnsmasq](https://formulae.brew.sh/formula/dnsmasq) with Homebrew
   (`brew install dnsmasq`). Run it in a separate terminal; do **not** start
   the persistent `brew services` service:

   ```sh
   sudo "$(brew --prefix)/sbin/dnsmasq" --no-daemon --bind-interfaces --listen-address=192.168.50.2 --no-resolv --server=1.1.1.1 --host-record=oneoss-ecu-mqtt.geely.com,192.168.50.2
   ```

   `1.1.1.1` is an example upstream DNS for other names; use yours if needed.
   If another service already uses port 53 on that address, stop it or use a
   different DNS server. Allow incoming DNS UDP/TCP 53 and TCP 8883 through
   the local firewall.
3. In another terminal run `./GeelyGalaxyADBUnlocker --broker-only`. Join the
   car to the router's Wi-Fi and reconnect it after changing DHCP DNS. After
   the session, stop both processes with Ctrl+C, restore the **recorded** DHCP
   DNS value on the router, and remove the temporary DHCP reservation if one
   was made only for this session.

## Verify the manual setup

Before connecting the car, test from **another client of the same Wi-Fi**.
Its DNS server should be `10.42.77.1` on Linux or the Mac's LAN address on
macOS. `nslookup oneoss-ecu-mqtt.geely.com` should return that same address;
`nslookup example.com` should still resolve. Check that TCP 8883 on the laptop
is reachable from the client. Changing DNS or `/etc/hosts` **only on the
laptop** does not redirect the car. Client isolation, bypassing local DNS, or
another IPv6 DNS may prevent the flow. Broker log entries for `ADBSwitch=ON`
and `execSuccess` indicate protocol exchange, but verify ADB separately (for
example, `adb devices -l` if the car is connected over USB). These manual
flows have not yet been verified on a car.

## Tests

Run `python -m unittest discover -v`. These tests cover DNS routing and exact
DNS restore, but not Windows hotspot behavior or an on-car TLS/MQTT connection.

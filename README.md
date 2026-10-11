# Geely Galaxy ADB unlocker — work in progress

This repository is a local-broker implementation based on the verified
`GeelyGalaxy_ADB` MQTT/DNS approach. The source and one-file build workflow
exist, but **no Windows or on-car acceptance test has been completed**.

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
completed successfully on all three platforms. Its [Windows artifact](https://github.com/Ilninho/GeelyGalaxyADB_unlocker/actions/runs/38171781378/artifacts/11714114597)
contains a single x86-64 `GeelyGalaxyADBUnlocker.exe`; the Windows runner
started it with `--help`. The Windows hotspot and on-car flow still require
acceptance testing.

## Tests

Run `python -m unittest discover -v`. These tests cover DNS routing and exact
DNS restore, but not Windows hotspot behavior or an on-car TLS/MQTT connection.

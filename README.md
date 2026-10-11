# Geely Galaxy ADB Unlocker

[Русский](README.ru.md) · [Download for Windows, Linux, and macOS](https://github.com/Ilninho/GeelyGalaxyADB_unlocker/releases/tag/v0.1.0-preview)

This tool helps enable ADB on a Geely Galaxy head unit over a local network. It follows the principle “do it half-assed, like everything else here”: the laptop runs an MQTT broker, the car connects over Wi-Fi, and the broker sends `ADBSwitch=ON`. No remote server or USB cable between the car and laptop is needed.

**You need:** a compatible head unit, a Windows x86-64, Linux x86-64, or macOS arm64 laptop, Wi-Fi, and internet access. Each archive contains one executable with Python bundled. Linux and macOS also need the manual network setup below. The local flow has not yet been verified on a car.

## Windows

1. Download and extract the [Windows ZIP](https://github.com/Ilninho/GeelyGalaxyADB_unlocker/releases/download/v0.1.0-preview/GeelyGalaxyADBUnlocker-Windows.zip).
2. Run `GeelyGalaxyADBUnlocker.exe` **as Administrator**. If Windows does not start Mobile Hotspot automatically, enable it in Settings and run the program again. Find the Wi-Fi name and password there.
3. Join the laptop's Wi-Fi network from the head unit. Keep the program window open.
4. After the session, press Ctrl+C. On a normal exit, the program restores the previous DNS settings and removes the firewall rules it created. If it was interrupted, run it again to restore the saved settings.

## Expected result

The program log should show an exchange with the head unit, including `ADBSwitch=ON`; it may also show `execSuccess`. After some time, the full engineering menu should replace the limited one. Open it through the car's dialer. If the menu does not change, reconnect the head unit to Wi-Fi and inspect the log. `execSuccess` alone does not prove ADB is available.

Find the dialer code yourself, or build it from the **date and time shown on the head unit**:

```text
#*<month + 5><day of month on head unit><head-unit hour in 12-hour format>
```

Join the parts without brackets or separators. Use `4` for 16:xx and `0` for 00:xx. Examples:

- **23 September, 16:45 on the head unit:** `9 + 5 = 14`, day `23`, hour `4` → `#*14234`.
- **23 September evening in Moscow, but already 24 September, 00:43 on the head unit:** month `14`, day **`24`**, hour `0` → `#*14240`.

Use the head unit's date even if your phone or laptop shows a different day. If you connect a USB cable, you can also check ADB with `adb devices -l`; USB is not required for the program.

## Linux: set up a hotspot and DNS manually

You need NetworkManager, a Wi-Fi adapter with access-point support, and internet via Ethernet or a second Wi-Fi adapter. Make sure the `dnsmasq` binary is available (the package may be called `dnsmasq-base`). NetworkManager uses it for DHCP/DNS; do not run a separate dnsmasq service. [The `dnsmasq-shared.d` setting](https://networkmanager.pages.freedesktop.org/NetworkManager/NetworkManager/nm-settings-nmcli.html) depends on the NetworkManager version.

Download and extract the [Linux ZIP](https://github.com/Ilninho/GeelyGalaxyADB_unlocker/releases/download/v0.1.0-preview/GeelyGalaxyADBUnlocker-Linux.zip), then run `chmod +x GeelyGalaxyADBUnlocker`. Find your Wi-Fi interface with `nmcli device status`. Replace `wlan0` and the password below. First confirm that neither the `GeelyADB-AP` profile nor `/etc/NetworkManager/dnsmasq-shared.d/geely-adb.conf` exists.

```sh
sudo nmcli device wifi hotspot ifname wlan0 con-name GeelyADB-AP ssid GeelyADB password 'your-wifi-password'
sudo nmcli connection modify GeelyADB-AP ipv4.method shared ipv4.addresses 10.42.77.1/24
sudo install -d /etc/NetworkManager/dnsmasq-shared.d
printf '%s\n' 'host-record=oneoss-ecu-mqtt.geely.com,10.42.77.1' | sudo tee /etc/NetworkManager/dnsmasq-shared.d/geely-adb.conf
sudo nmcli connection down GeelyADB-AP
sudo nmcli connection up GeelyADB-AP
./GeelyGalaxyADBUnlocker --broker-only
```

If `10.42.77.0/24` conflicts with an existing network, choose another subnet and update the DNS record too. Allow incoming UDP/TCP 53 and TCP 8883 on the hotspot interface if a firewall is active. Join `GeelyADB` from the head unit.

After the session, press Ctrl+C and remove **only** the profile and file created here:

```sh
sudo nmcli connection down GeelyADB-AP
sudo rm /etc/NetworkManager/dnsmasq-shared.d/geely-adb.conf
sudo nmcli connection delete GeelyADB-AP
```

## macOS: set up DNS through a router manually

You need a router/access point whose DHCP settings let you choose the DNS server advertised to clients. Connect the Mac and head unit to the same LAN without client isolation. For example, connect the Mac over Ethernet and the car over Wi-Fi. macOS [Internet Sharing](https://support.apple.com/en-qa/guide/mac-help/mchlp1540/mac) alone does not expose the required client DNS setting through its documented controls.

1. Download and extract the [macOS ZIP](https://github.com/Ilninho/GeelyGalaxyADB_unlocker/releases/download/v0.1.0-preview/GeelyGalaxyADBUnlocker-macOS.zip), then run `chmod +x GeelyGalaxyADBUnlocker`.
2. Reserve a stable LAN address for the Mac in router DHCP, for example `192.168.50.2`. Record the router's previous DHCP DNS value, then temporarily advertise the Mac's address as the **only** client DNS. Temporarily disable any other DNS advertised over IPv6.
3. Install [dnsmasq](https://formulae.brew.sh/formula/dnsmasq) with `brew install dnsmasq`. Run the command below in one terminal. Replace the example IP with the Mac's actual address; `1.1.1.1` is an example upstream DNS:

```sh
sudo "$(brew --prefix)/sbin/dnsmasq" --no-daemon --bind-interfaces --listen-address=192.168.50.2 --no-resolv --server=1.1.1.1 --host-record=oneoss-ecu-mqtt.geely.com,192.168.50.2
```

4. In a second terminal run `./GeelyGalaxyADBUnlocker --broker-only`. Allow incoming UDP/TCP 53 and TCP 8883 if a firewall is active. Join the router's Wi-Fi from the head unit; reconnect it after changing DHCP DNS.
5. After the session, stop both processes with Ctrl+C. Restore the router's **recorded** DHCP DNS value and remove the temporary address reservation if it was created only for this session.

On Linux and macOS, test from **another client on the same network**: `nslookup oneoss-ecu-mqtt.geely.com` should return the laptop's address, ordinary sites should still resolve, and TCP 8883 on the laptop should be reachable. Changing DNS or `/etc/hosts` only on the laptop does not redirect the head unit.

## Credits and use

Based on an idea by [Ruslan Spaceyard](https://www.drive2.ru/users/spaceyard/); see the [original project](https://gitverse.ru/spaceyard/GeelyGalaxy_ADB). Free noncommercial use under [LICENSE.md](LICENSE.md). If you would like to thank the authors, consider a small monthly donation to a charity instead.

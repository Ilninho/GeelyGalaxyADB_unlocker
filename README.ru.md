# Geely Galaxy ADB Unlocker

[English](README.md) · [Скачать для Windows, Linux и macOS](https://github.com/Ilninho/GeelyGalaxyADB_unlocker/releases/tag/v0.1.0-preview)

Программа помогает открыть ADB на головном устройстве Geely Galaxy через локальную сеть. Работает по принципу «делаю на отъебись, как и все здесь»: ноутбук поднимает MQTT-брокер, автомобиль подключается к нему через Wi-Fi, а брокер отправляет `ADBSwitch=ON`. Удалённый сервер и USB-кабель между автомобилем и ноутбуком не нужны.

**Что нужно:** совместимое ГУ, ноутбук с Windows x86-64, Linux x86-64 или macOS arm64, Wi-Fi и доступ в интернет. В архиве один исполняемый файл, Python устанавливать не надо. Для Linux/macOS сеть нужно настроить вручную по инструкции ниже. Локальный вариант пока не проверен на автомобиле.

## Windows

1. Скачайте и распакуйте [Windows ZIP](https://github.com/Ilninho/GeelyGalaxyADB_unlocker/releases/download/v0.1.0-preview/GeelyGalaxyADBUnlocker-Windows.zip).
2. Запустите `GeelyGalaxyADBUnlocker.exe` **от имени администратора**. Если Windows не включила «Мобильный хот-спот» автоматически, включите его в настройках и запустите файл ещё раз. Там же посмотрите имя Wi-Fi-сети и пароль.
3. Подключите ГУ к Wi-Fi ноутбука. Оставьте окно программы открытым.
4. После сеанса нажмите Ctrl+C. При штатном выходе программа возвращает прежние настройки DNS и удаляет созданные ею правила брандмауэра. После аварийного завершения запустите её снова, чтобы восстановить сохранённые настройки.

## Что должно получиться

В окне программы должен появиться обмен с ГУ, в том числе `ADBSwitch=ON`; может появиться `execSuccess`. Через некоторое время вместо усечённого инженерного меню должно открыться полное. Заходите в него через звонилку автомобиля. Если меню не изменилось, переподключите ГУ к Wi-Fi и посмотрите журнал программы. `execSuccess` сам по себе ещё не доказывает, что ADB доступен.

Код для звонилки можно найти самостоятельно или составить по **дате и времени на ГУ**:

```text
#*<месяц + 5><число месяца на ГУ><час на ГУ в 12-часовом формате>
```

Пишите части подряд, без скобок и разделителей. Для 16 часов берите `4`, для 00 часов — `0`. Примеры:

- **23 сентября, 16:45 на ГУ:** `9 + 5 = 14`, число `23`, час `4` → `#*14234`.
- **23 сентября вечером по Москве, но на ГУ уже 24 сентября, 00:43:** месяц `14`, число **`24`**, час `0` → `#*14240`.

Ориентируйтесь именно на дату ГУ. Если подключён USB-кабель, дополнительно проверьте ADB командой `adb devices -l`; для самой программы кабель не нужен.

## Linux: точка доступа и DNS вручную

Нужны NetworkManager, Wi-Fi-адаптер с поддержкой точки доступа и интернет через Ethernet или второй Wi-Fi-адаптер. Убедитесь, что доступен `dnsmasq` (в некоторых дистрибутивах пакет называется `dnsmasq-base`). NetworkManager использует его для DHCP и DNS; отдельную службу dnsmasq не запускайте. [Настройка через `dnsmasq-shared.d`](https://networkmanager.pages.freedesktop.org/NetworkManager/NetworkManager/nm-settings-nmcli.html) зависит от версии NetworkManager.

Скачайте [Linux ZIP](https://github.com/Ilninho/GeelyGalaxyADB_unlocker/releases/download/v0.1.0-preview/GeelyGalaxyADBUnlocker-Linux.zip), распакуйте и выполните `chmod +x GeelyGalaxyADBUnlocker`. Команда `nmcli device status` покажет имя Wi-Fi-интерфейса. Замените ниже `wlan0` и пароль. Сначала убедитесь, что профиль `GeelyADB-AP` и файл `/etc/NetworkManager/dnsmasq-shared.d/geely-adb.conf` ещё не существуют.

```sh
sudo nmcli device wifi hotspot ifname wlan0 con-name GeelyADB-AP ssid GeelyADB password 'your-wifi-password'
sudo nmcli connection modify GeelyADB-AP ipv4.method shared ipv4.addresses 10.42.77.1/24
sudo install -d /etc/NetworkManager/dnsmasq-shared.d
printf '%s\n' 'host-record=oneoss-ecu-mqtt.geely.com,10.42.77.1' | sudo tee /etc/NetworkManager/dnsmasq-shared.d/geely-adb.conf
sudo nmcli connection down GeelyADB-AP
sudo nmcli connection up GeelyADB-AP
./GeelyGalaxyADBUnlocker --broker-only
```

Если сеть `10.42.77.0/24` занята, выберите другую и замените IP в DNS-записи. При включённом файрволе разрешите входящие UDP/TCP 53 и TCP 8883 на интерфейсе точки доступа. Подключите ГУ к `GeelyADB`.

После сеанса нажмите Ctrl+C и удалите **только** созданные здесь профиль и файл:

```sh
sudo nmcli connection down GeelyADB-AP
sudo rm /etc/NetworkManager/dnsmasq-shared.d/geely-adb.conf
sudo nmcli connection delete GeelyADB-AP
```

## macOS: DNS через роутер вручную

Нужен роутер или точка доступа, где можно задать DNS, выдаваемый клиентам по DHCP. Mac и ГУ должны быть в одной сети без изоляции клиентов. Например, Mac подключён к роутеру по Ethernet, ГУ — по Wi-Fi. Штатный [«Общий интернет» macOS](https://support.apple.com/en-qa/guide/mac-help/mchlp1540/mac) сам по себе не позволяет задать нужный DNS клиентам через документированные настройки.

1. Скачайте [macOS ZIP](https://github.com/Ilninho/GeelyGalaxyADB_unlocker/releases/download/v0.1.0-preview/GeelyGalaxyADBUnlocker-macOS.zip), распакуйте и выполните `chmod +x GeelyGalaxyADBUnlocker`.
2. Закрепите за Mac адрес в LAN через DHCP-резервирование, например `192.168.50.2`. Запишите прежний DHCP DNS роутера и временно задайте адрес Mac как **единственный** DNS для клиентов. Если роутер выдаёт другой DNS по IPv6, временно отключите и его.
3. Установите [dnsmasq](https://formulae.brew.sh/formula/dnsmasq) командой `brew install dnsmasq`. В первом терминале запустите команду ниже. Замените пример IP на адрес Mac; `1.1.1.1` — пример вышестоящего DNS:

```sh
sudo "$(brew --prefix)/sbin/dnsmasq" --no-daemon --bind-interfaces --listen-address=192.168.50.2 --no-resolv --server=1.1.1.1 --host-record=oneoss-ecu-mqtt.geely.com,192.168.50.2
```

4. Во втором терминале запустите `./GeelyGalaxyADBUnlocker --broker-only`. При включённом файрволе разрешите входящие UDP/TCP 53 и TCP 8883. Подключите ГУ к Wi-Fi роутера; после изменения DHCP DNS переподключите его.
5. После сеанса остановите оба процесса через Ctrl+C. Верните **записанный ранее** DHCP DNS роутера и удалите временную резервацию адреса, если создавали её только для этого сеанса.

На Linux и macOS проверьте с **другого клиента той же сети**: `nslookup oneoss-ecu-mqtt.geely.com` должен вернуть адрес ноутбука, обычные сайты должны разрешаться как прежде, TCP 8883 ноутбука должен быть доступен. Изменение DNS или `/etc/hosts` только на ноутбуке трафик ГУ не перенаправит.

## Авторы и условия использования

Это развитие идеи [Руслана Spaceyard](https://www.drive2.ru/users/spaceyard/); [оригинальный проект](https://gitverse.ru/spaceyard/GeelyGalaxy_ADB). Бесплатное некоммерческое использование — по [LICENSE.md](LICENSE.md).

Если хочется отблагодарить Руслана, напишите ему на Drive2 или воспользуйтесь [ссылкой для пожертвования](https://pay.cloudtips.ru/p/6657a42a), которую он оставил в [оригинальном посте](https://www.drive2.ru/l/736445467654638943/).

Если хочется отблагодарить автора (меня, Ilninho), лучше оформите небольшое ежемесячное пожертвование любой понравившейся благотворительной организации. Лично я выбираю помощь взрослым и животным: о них, на мой взгляд, заботятся меньше всего.

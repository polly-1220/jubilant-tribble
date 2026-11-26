"""
Зв'язок з польотним контролером Betaflight по USB через протокол MSP (версія 1).

Як влаштоване MSP-повідомлення (запит від комп'ютера до дрона):
    '$' 'M' '<'  розмір  команда  [дані...]  контрольна_сума
Відповідь від дрона виглядає так само, тільки замість '<' стоїть '>'
(або '!', якщо дрон не знає такої команди).
Контрольна сума = XOR (виключне "або") розміру, команди і всіх байтів даних.

Команди, які ми використовуємо (номери з документації Betaflight):
    MSP_FC_VARIANT = 2    -> назва прошивки, для Betaflight це "BTFL"
    MSP_FC_VERSION = 3    -> версія прошивки, напр. 4.5.3
    MSP_RAW_IMU    = 102  -> акселерометр, гіроскоп, магнітометр (9 чисел int16)
(Одиниці звірено з кодом Betaflight 4.5: src/main/msp/msp.c.)
    MSP_ATTITUDE   = 108  -> крен і нахил (у десятих частках градуса), рискання (у градусах)
"""
import struct
import time

import serial
from serial.tools import list_ports

MSP_FC_VARIANT = 2
MSP_FC_VERSION = 3
MSP_RAW_IMU = 102
MSP_ATTITUDE = 108

# Перерахунок гіроскопа в градуси за секунду (див. read_raw_imu)
GYRO_DPS_PER_UNIT = 2000.0 / 32768.0

# Ідентифікатор виробника мікросхем STM32 (на них працює плата дрона)
STM32_VID = 0x0483


class DroneError(Exception):
    """Помилка зв'язку з дроном. Текст помилки — українською, для людини."""


def find_drone_ports():
    """
    Шукає порти, схожі на дрон. Повертає список назв, напр. ['/dev/cu.usbmodem3561']
    На macOS дрон з'являється як /dev/cu.usbmodem..., у нього виробник STM32.
    """
    found = []
    for p in list_ports.comports():
        device = p.device
        # На macOS кожен порт є у двох видах: tty.* і cu.* — нам потрібен cu.*
        if device.startswith("/dev/tty."):
            device = device.replace("/dev/tty.", "/dev/cu.", 1)
        looks_like_drone = "usbmodem" in device or p.vid == STM32_VID
        if looks_like_drone and device not in found:
            found.append(device)
    return found


def all_ports_text():
    """Список усіх портів — для підказки, якщо дрон не знайдено."""
    ports = [p.device for p in list_ports.comports()]
    return ", ".join(ports) if ports else "(жодного)"


class MSPClient:
    """Підключення до одного дрона. Вміє надсилати MSP-запити і читати відповіді."""

    def __init__(self, port=None, timeout=0.3):
        self.port = port
        self.timeout = timeout
        self.ser = None

    # ---------- підключення ----------
    def open(self):
        """Відкриває порт. Якщо порт не вказано — шукає дрон сам."""
        if self.port is None:
            ports = find_drone_ports()
            if not ports:
                raise DroneError(
                    "Дрон не знайдено. Перевір: 1) дрон підключений USB-кабелем; "
                    "2) кабель передає дані (а не лише заряджає); "
                    "3) спробуй інший USB-роз'єм. "
                    f"Знайдені порти: {all_ports_text()}"
                )
            self.port = ports[0]
        try:
            # Для USB швидкість (baudrate) фактично не важлива, але вказати треба
            self.ser = serial.Serial(self.port, baudrate=115200, timeout=0.05)
        except serial.SerialException as e:
            text = str(e)
            if "busy" in text.lower() or "Errno 16" in text:
                raise DroneError(
                    f"Порт {self.port} зайнятий іншою програмою. Найчастіше це "
                    "Betaflight Configurator у Chrome: натисни там «Disconnect» "
                    "або закрий його вкладку, потім спробуй знову."
                ) from e
            raise DroneError(f"Не вдалося відкрити порт {self.port}: {text}") from e
        time.sleep(0.2)  # даємо платі мить «прокинутися»
        self.ser.reset_input_buffer()

    def close(self):
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None

    # ---------- низький рівень: один запит -> одна відповідь ----------
    def request(self, cmd, payload=b""):
        """Надсилає команду і повертає байти відповіді."""
        if self.ser is None:
            raise DroneError("Порт не відкритий.")
        size = len(payload)
        checksum = size ^ cmd
        for b in payload:
            checksum ^= b
        frame = b"$M<" + bytes([size, cmd]) + payload + bytes([checksum])
        self.ser.reset_input_buffer()   # викидаємо старі байти
        self.ser.write(frame)
        return self._read_response(cmd)

    def _read_exact(self, n, deadline):
        """Читає рівно n байтів (або менше, якщо закінчився час)."""
        data = b""
        while len(data) < n and time.monotonic() < deadline:
            data += self.ser.read(n - len(data))
        return data

    def _read_response(self, expected_cmd):
        deadline = time.monotonic() + self.timeout
        pending = None   # байт, який треба перевірити ще раз (міг бути початком '$')
        while time.monotonic() < deadline:
            # Шукаємо початок відповіді: '$' 'M' '>' (або '!')
            b = pending if pending is not None else self._read_exact(1, deadline)
            pending = None
            if b != b"$":
                continue
            m = self._read_exact(1, deadline)
            if m != b"M":
                pending = m
                continue
            direction = self._read_exact(1, deadline)
            if direction not in (b">", b"!"):
                pending = direction
                continue
            header = self._read_exact(2, deadline)
            if len(header) < 2:
                break
            size, cmd = header[0], header[1]
            payload = self._read_exact(size, deadline)
            chk = self._read_exact(1, deadline)
            if len(payload) != size or len(chk) != 1:
                break
            # Перевіряємо контрольну суму
            calc = size ^ cmd
            for b in payload:
                calc ^= b
            if calc != chk[0]:
                continue  # пошкоджене повідомлення — шукаємо далі
            if cmd != expected_cmd:
                continue  # це відповідь на інший запит
            if direction == b"!":
                raise DroneError(f"Дрон не підтримує команду MSP {cmd}.")
            return payload
        raise TimeoutError(f"Дрон не відповів на команду MSP {expected_cmd}.")

    # ---------- зручні функції ----------
    def read_fc_info(self):
        """Повертає рядок на кшталт 'BTFL 4.5.3'."""
        variant = self.request(MSP_FC_VARIANT)[:4].decode("ascii", "replace")
        v = self.request(MSP_FC_VERSION)
        version = f"{v[0]}.{v[1]}.{v[2]}" if len(v) >= 3 else "?"
        return f"{variant} {version}"

    def read_attitude(self):
        """
        Кути дрона в градусах: (крен, нахил, рискання).
        Betaflight надсилає крен і нахил у десятих частках градуса, тому ділимо на 10.
        """
        data = self.request(MSP_ATTITUDE)
        roll, pitch, yaw = struct.unpack("<hhh", data[:6])
        return roll / 10.0, pitch / 10.0, float(yaw)

    def read_raw_imu(self):
        """
        Дані датчиків: (акселерометр x,y,z), (гіроскоп x,y,z у градусах за секунду).

        Важливо: у Betaflight 4.5 гіроскоп по MSP приходить у «сирих» одиницях датчика
        (у коді прошивки: gyroRateDps() ділить на коефіцієнт датчика).
        Для датчиків з діапазоном 2000 °/с одна одиниця = 2000 / 32768 ≈ 0.061 °/с,
        тому множимо на GYRO_DPS_PER_UNIT.
        Акселерометр — у внутрішніх одиницях плати (нам він потрібен лише для довідки).
        """
        data = self.request(MSP_RAW_IMU)
        values = struct.unpack("<9h", data[:18])
        acc = values[0:3]
        gyro = tuple(v * GYRO_DPS_PER_UNIT for v in values[3:6])
        return acc, gyro

"""
Маленький тест зв'язку з дроном.
Просто знаходить дрон на USB і друкує кути та гіроскоп ~20 разів на секунду.

Запуск (з головної папки проєкту, з увімкненим .venv):
    python tools/test_drone.py            # знайти дрон автоматично
    python tools/test_drone.py --list     # лише показати всі порти
    python tools/test_drone.py --port /dev/cu.usbmodem1234   # вказати порт вручну
Зупинити: Control + C
"""
import argparse
import sys
import time
from pathlib import Path

# Щоб Python знайшов папку core (вона лежить на рівень вище)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from serial.tools import list_ports  # noqa: E402

from core.msp import DroneError, MSPClient, find_drone_ports  # noqa: E402
from core.stability import StabilityDetector  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Тест зв'язку з дроном по MSP")
    parser.add_argument("--port", help="назва порту, напр. /dev/cu.usbmodem1234")
    parser.add_argument("--list", action="store_true", help="показати всі порти")
    args = parser.parse_args()

    if args.list:
        print("Усі порти на цьому комп'ютері:")
        for p in list_ports.comports():
            print(f"  {p.device:35s} {p.description}  (VID={p.vid}, PID={p.pid})")
        print("Схожі на дрон:", find_drone_ports() or "немає")
        return

    print("⚠️  Переконайся, що Betaflight Configurator у Chrome ВІД'ЄДНАНИЙ (Disconnect).")
    client = MSPClient(port=args.port)
    try:
        client.open()
        print(f"✅ Підключено до порту {client.port}")
        print(f"   Прошивка: {client.read_fc_info()}")
    except (DroneError, TimeoutError) as e:
        print(f"❌ {e}")
        client.close()
        return

    detector = StabilityDetector()
    print(f"Поріг стабільності: {detector.threshold} °/с. Зупинити: Control + C\n")
    try:
        while True:
            t0 = time.monotonic()
            try:
                roll, pitch, yaw = client.read_attitude()
                _acc, gyro = client.read_raw_imu()
            except TimeoutError as e:
                print(f"\n⏳ {e}")
                continue
            stable = detector.update(gyro, time.monotonic())
            state = "СТАБІЛЬНО   " if stable else "нестабільно "
            # \r повертає курсор на початок рядка, щоб рядок оновлювався на місці
            print(
                f"\rКрен {roll:+6.1f}°  Нахил {pitch:+6.1f}°  Рискання {yaw:5.0f}°  |  "
                f"Гіро X {gyro[0]:+7.1f}  Y {gyro[1]:+7.1f}  Z {gyro[2]:+7.1f} °/с  |  {state}",
                end="", flush=True,
            )
            time.sleep(max(0.0, 0.05 - (time.monotonic() - t0)))  # ~20 разів/с
    except KeyboardInterrupt:
        print("\nЗупинено.")
    except OSError as e:
        print(f"\n❌ Зв'язок з дроном втрачено (кабель від'єднали?): {e}")
    finally:
        client.close()


if __name__ == "__main__":
    main()

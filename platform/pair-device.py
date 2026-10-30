"""Start a bounded Apple trust-pairing request for a selected USB iPhone."""
import argparse
import asyncio
from pymobiledevice3.lockdown import create_using_usbmux

parser = argparse.ArgumentParser()
parser.add_argument('udid')
args = parser.parse_args()


async def main():
    try:
        async with asyncio.timeout(75):
            async with await create_using_usbmux(serial=args.udid, pair_timeout=60) as device:
                print('配对成功' if device.paired else '尚未配对')
    except Exception as exc:
        print(f'未完成配对：{type(exc).__name__}。请解锁手机并确认信任，再重试。')
        raise SystemExit(1)


asyncio.run(main())

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
                print('Paired.' if device.paired else 'Not paired yet.')
    except Exception as exc:
        print(f'Pairing did not finish: {type(exc).__name__}. Unlock the iPhone, confirm Trust This Computer, and try again.')
        raise SystemExit(1)


asyncio.run(main())

#!/usr/bin/env python3
import argparse
import asyncio
from pathlib import Path

import androidtvremote2
from androidtvremote2 import AndroidTVRemote

DEFAULT_STORE_DIR = Path(".androidtvremote2")
DEFAULT_CLIENT_NAME = "fios-remote-cli"


def load_keycodes():
    """
    androidtvremote2 has had small API moves across versions.
    We try a few known names/locations for key code enums.
    """
    try:
        import androidtvremote2.const as const
    except Exception as e:
        raise SystemExit(f"Cannot import androidtvremote2.const: {e}")

    # Common in 0.3.x
    if hasattr(const, "RemoteKeyCode"):
        return const.RemoteKeyCode, "androidtvremote2.const.RemoteKeyCode"

    # Some versions may expose KeyCode
    if hasattr(const, "KeyCode"):
        return const.KeyCode, "androidtvremote2.const.KeyCode"

    # Last resort: find any Enum-like class containing KEYCODE_HOME
    for name in dir(const):
        obj = getattr(const, name)
        if hasattr(obj, "KEYCODE_HOME"):
            return obj, f"androidtvremote2.const.{name}"

    raise SystemExit(
        "Could not find a keycode enum in androidtvremote2.const. "
        f"Available names: {[n for n in dir(const) if not n.startswith('_')]}"
    )


RemoteKeyCode, KEYCODE_SOURCE = load_keycodes()

KEYMAP = {
    "home": RemoteKeyCode.KEYCODE_HOME,
    "back": RemoteKeyCode.KEYCODE_BACK,
    "up": RemoteKeyCode.KEYCODE_DPAD_UP,
    "down": RemoteKeyCode.KEYCODE_DPAD_DOWN,
    "left": RemoteKeyCode.KEYCODE_DPAD_LEFT,
    "right": RemoteKeyCode.KEYCODE_DPAD_RIGHT,
    "ok": RemoteKeyCode.KEYCODE_DPAD_CENTER,
    "enter": RemoteKeyCode.KEYCODE_ENTER,
    "menu": RemoteKeyCode.KEYCODE_MENU,
    "playpause": RemoteKeyCode.KEYCODE_MEDIA_PLAY_PAUSE,
    "play": RemoteKeyCode.KEYCODE_MEDIA_PLAY,
    "pause": RemoteKeyCode.KEYCODE_MEDIA_PAUSE,
    "stop": RemoteKeyCode.KEYCODE_MEDIA_STOP,
    "volup": RemoteKeyCode.KEYCODE_VOLUME_UP,
    "voldown": RemoteKeyCode.KEYCODE_VOLUME_DOWN,
    "mute": RemoteKeyCode.KEYCODE_VOLUME_MUTE,
    "chup": getattr(RemoteKeyCode, "KEYCODE_CHANNEL_UP", None),
    "chdown": getattr(RemoteKeyCode, "KEYCODE_CHANNEL_DOWN", None),
}

# Remove None entries if your version doesn't include channel keys
KEYMAP = {k: v for k, v in KEYMAP.items() if v is not None}

DIGITS = {}
for d in "0123456789":
    name = f"KEYCODE_{d}"
    if hasattr(RemoteKeyCode, name):
        DIGITS[d] = getattr(RemoteKeyCode, name)


async def maybe_await(x):
    if asyncio.iscoroutine(x):
        return await x
    return x


async def connect_remote(remote):
    if hasattr(remote, "async_connect"):
        ok = await remote.async_connect()
        return ok if ok is not None else True
    if hasattr(remote, "connect"):
        await maybe_await(remote.connect())
        return True
    raise RuntimeError("Remote object has no connect/async_connect method")


async def disconnect_remote(remote):
    if hasattr(remote, "async_disconnect"):
        return await remote.async_disconnect()
    if hasattr(remote, "disconnect"):
        return await maybe_await(remote.disconnect())
    return None


async def send_key(remote, keycode, repeat=1, delay=0.06):
    for _ in range(repeat):
        if hasattr(remote, "send_key_command"):
            await remote.send_key_command(keycode)
        elif hasattr(remote, "async_send_key_command"):
            await remote.async_send_key_command(keycode)
        else:
            raise RuntimeError("Remote object has no send_key_command method")
        await asyncio.sleep(delay)


async def send_text(remote, text):
    if hasattr(remote, "send_text"):
        await remote.send_text(text)
    elif hasattr(remote, "async_send_text"):
        await remote.async_send_text(text)
    else:
        raise RuntimeError("Remote object has no send_text method")


async def launch(remote, uri):
    if hasattr(remote, "send_launch_app_command"):
        await remote.send_launch_app_command(uri)
    elif hasattr(remote, "async_send_launch_app_command"):
        await remote.async_send_launch_app_command(uri)
    else:
        raise RuntimeError("Remote object has no send_launch_app_command method")


async def current_app(remote):
    if hasattr(remote, "get_current_app"):
        app = await remote.get_current_app()
        print(app)
        return
    if hasattr(remote, "async_get_current_app"):
        app = await remote.async_get_current_app()
        print(app)
        return
    raise RuntimeError("Remote object has no get_current_app method")


async def run(host, client_name, store_dir, api_port, pair_port, enable_ime, cmd, args):
    store_dir = Path(store_dir)
    certfile = store_dir / f"{client_name}.crt"
    keyfile = store_dir / f"{client_name}.key"

    if not certfile.exists() or not keyfile.exists():
        raise SystemExit(
            f"Missing cert/key in {store_dir}. Copy .androidtvremote2 from your paired machine.\n"
        )

    remote = AndroidTVRemote(
        client_name,
        str(certfile),
        str(keyfile),
        host,
        api_port=api_port,
        pair_port=pair_port,
        enable_ime=enable_ime,
    )

    await connect_remote(remote)
    try:
        if cmd == "key":
            name = args.name.lower()
            if name not in KEYMAP:
                raise SystemExit(f"Unknown key '{name}'. Known: {', '.join(sorted(KEYMAP.keys()))}")
            await send_key(remote, KEYMAP[name], repeat=args.repeat)

        elif cmd == "text":
            await send_text(remote, args.text)

        elif cmd == "launch":
            await launch(remote, args.uri)

        elif cmd == "current-app":
            await current_app(remote)

        elif cmd == "channel":
            if not DIGITS:
                raise SystemExit("This androidtvremote2 version does not expose digit keycodes.")
            for ch in args.number:
                if ch not in DIGITS:
                    raise SystemExit("Channel must be numeric.")
                await send_key(remote, DIGITS[ch], delay=0.08)
            if not args.no_enter and hasattr(RemoteKeyCode, "KEYCODE_ENTER"):
                await send_key(remote, RemoteKeyCode.KEYCODE_ENTER)

    finally:
        await disconnect_remote(remote)


def main():
    ap = argparse.ArgumentParser(description="FiOS TV+ remote control via Android TV Remote v2 (6466).")
    ap.add_argument("--host", default="192.168.1.101")
    ap.add_argument("--client-name", default=DEFAULT_CLIENT_NAME)
    ap.add_argument("--store-dir", default=str(DEFAULT_STORE_DIR))
    ap.add_argument("--api-port", type=int, default=6466)
    ap.add_argument("--pair-port", type=int, default=6467)
    ap.add_argument("--no-ime", action="store_true", help="Disable IME if device prompts mobile keyboard")
    ap.add_argument("--debug", action="store_true", help="Print version/keycode source info")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp_key = sub.add_parser("key")
    sp_key.add_argument("name")
    sp_key.add_argument("--repeat", type=int, default=1)

    sp_text = sub.add_parser("text")
    sp_text.add_argument("text")

    sp_launch = sub.add_parser("launch")
    sp_launch.add_argument("uri")

    sub.add_parser("current-app")

    sp_channel = sub.add_parser("channel")
    sp_channel.add_argument("number")
    sp_channel.add_argument("--no-enter", action="store_true")

    args = ap.parse_args()
    if args.debug:
        print("androidtvremote2 module:", androidtvremote2.__file__)
        print("androidtvremote2 version:", getattr(androidtvremote2, "__version__", "unknown"))
        print("Keycodes loaded from:", KEYCODE_SOURCE)

    enable_ime = not args.no_ime

    asyncio.run(run(
        args.host, args.client_name, args.store_dir,
        args.api_port, args.pair_port, enable_ime,
        args.cmd, args
    ))


if __name__ == "__main__":
    main()

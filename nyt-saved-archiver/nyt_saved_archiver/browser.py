"""Shared hardened browser launch to minimize automation fingerprint (DataDome).

Uses the real Google Chrome binary (channel="chrome") rather than Playwright's
bundled Chromium, strips the automation flags, sets a real UA, and hides
navigator.webdriver. The login page is NYT's most bot-protected surface, so these
matter most there — but the fetch loop uses the same hardening.
"""
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def launch_kwargs() -> dict:
    return dict(
        channel="chrome",                                   # real Chrome, not bundled Chromium
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"],
        user_agent=UA,
        viewport={"width": 1280, "height": 900},
        locale="en-US",
    )


def harden(ctx) -> None:
    """Hide the residual navigator.webdriver flag in every page of the context."""
    ctx.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
    )

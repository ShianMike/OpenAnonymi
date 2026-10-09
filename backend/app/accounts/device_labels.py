"""Allowlisted coarse labels only; never retain the supplied User-Agent."""


def device_label(user_agent: str) -> str:
    ua = user_agent[:512].lower()
    browser = "Unknown browser"
    for name, markers in (
        ("Edge", ("edg/", "edgios/", "edga/")),
        ("Opera", ("opr/", "opera/")),
        ("Firefox", ("firefox/", "fxios/")),
        ("Chrome", ("chrome/", "crios/")),
        ("Safari", ("safari/",)),
    ):
        if any(marker in ua for marker in markers):
            browser = name
            break
    system = "Unknown system"
    for name, markers in (
        ("iOS", ("iphone", "ipad", "ipod")),
        ("Android", ("android",)),
        ("ChromeOS", ("cros ",)),
        ("Windows", ("windows",)),
        ("macOS", ("macintosh", "mac os x")),
        ("Linux", ("linux",)),
    ):
        if any(marker in ua for marker in markers):
            system = name
            break
    return browser + " · " + system

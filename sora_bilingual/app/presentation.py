"""Pure status presentation: no Qt, IO, process control or native hooks."""

import time
from sora_bilingual.config.locales import LOCALES

MODE_NAMES = {
    "annotation": "双语同时显示",
    "language_toggle": "单击切换",
    "language_hold": "按住 / 松开",
}
LANG_NAMES = {code: locale.short_name for code, locale in LOCALES.items()}
LANG_CODES = {
    "zh-Hans": "ZH",
    "zh-Hant": "ZT",
    "ja": "JA",
    "en": "EN",
    "ko": "KO",
    "fr": "FR",
    "de": "DE",
    "es": "ES",
}


def _short_pair(primary, secondary):
    return f"{LANG_CODES.get(primary, primary)} → {LANG_CODES.get(secondary, secondary)}"


def with_font_status(state, fonts):
    """Keep connection truth while surfacing font setup independently."""
    notices = {
        "preparing": "正在准备多语言字体，当前连接继续运行",
        "prepared": "字体已准备，等待安全安装",
        "restart-required": "字体待安装：退出游戏后自动安装，下次启动生效",
        "conflict": "字体安装遇到已有 MOD 文件，请查看详情",
        "error": "字体准备或安装失败，请查看详情",
    }
    notice = notices.get(fonts.get("state"))
    if not notice:
        return state
    detail = fonts.get("detail")
    if isinstance(detail, list):
        detail = "\n".join(str(item) for item in detail)
    return {**state, "font_notice": notice, "font_detail": str(detail or "")}


def describe_state(config, live, backend, now=None):
    """Only fresh, acknowledged runtime state can claim a language is active."""
    now = time.time() if now is None else now
    fresh = bool(live.get("running") and 0 <= now - live.get("updated_at", 0) < 2)
    connection = bool(backend.get("running") and 0 <= now - backend.get("updated_at", 0) < 5)
    error = (live.get("error") if fresh else None) or (
        backend.get("error") if now - backend.get("updated_at", 0) < 5 else None
    )
    strategy = MODE_NAMES.get(config.get("interaction"), "手动显示")
    primary = LANG_NAMES.get(config["primary"], config["primary"])
    secondary = LANG_NAMES.get(config["secondary"], config["secondary"])
    pair = f"{primary} → {secondary}"
    short_pair = _short_pair(config["primary"], config["secondary"])
    if error:
        return {
            "title": "连接异常",
            "detail": str(error),
            "color": "#a32b22",
            "marker": "▲",
            "connected": False,
            "pair": pair,
            "short_pair": short_pair,
        }
    if connection and backend.get("phase") == "connecting":
        return {
            "title": "正在连接游戏",
            "detail": "正在准备语言索引…",
            "color": "#4f6270",
            "marker": "○",
            "connected": False,
            "pair": pair,
            "short_pair": short_pair,
        }
    if not fresh:
        return {
            "title": ("正在同步" if connection else "未连接游戏") + " · " + strategy,
            "detail": "设置已保存 · 连接后生效",
            "color": "#4f6270",
            "marker": "○",
            "connected": False,
            "pair": pair,
            "short_pair": short_pair,
        }
    if not live.get("enabled", True):
        return {
            "title": "已停用 · 游戏原文",
            "detail": "连接保留，可随时重新启用",
            "color": "#4f6270",
            "marker": "■",
            "connected": True,
            "pair": pair,
            "short_pair": short_pair,
        }
    held = live.get("hold_active", False)
    mode = live.get("render_mode", "primary")
    shown = {"annotation": "双语", "primary": "主语言", "secondary": "副语言"}.get(mode, mode)
    strategy = MODE_NAMES.get(live.get("interaction"), "手动显示")
    title = "按住中 · 副语言" if held else strategy + " · " + shown
    if not held and live.get("interaction") == "language_hold":
        title = "已松开 · " + shown
    pending = any(config.get(k) != live.get(k) for k in ("primary", "secondary", "mode_request"))
    phase = backend.get("phase") if connection else live.get("phase")
    reload_error = backend.get("reload_error") if connection else live.get("reload_error")
    detail = (
        backend.get("configuration_error")
        or reload_error
        or (
            "正在准备新语言，当前语言继续显示…"
            if phase == "preparing"
            else "正在应用新语言…"
            if phase == "applying"
            else "正在应用设置…"
            if pending
            else "松开后恢复之前的显示"
            if held
            else "设置实时生效"
        )
    )
    return {
        "title": title,
        "detail": detail,
        "color": "#8a5a00" if held else "#086b68",
        "marker": "◆" if held else "●",
        "connected": True,
        "pair": f"{LANG_NAMES.get(live.get('primary'), primary)} → {LANG_NAMES.get(live.get('secondary'), secondary)}",
        "short_pair": _short_pair(
            live.get("primary", config["primary"]), live.get("secondary", config["secondary"])
        ),
    }

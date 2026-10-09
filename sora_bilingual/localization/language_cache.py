"""Verified, language-local parsing facts; never cache a translation decision."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import json
import time
from pathlib import Path

from sora_bilingual.localization.cache_io import publish_json
from sora_bilingual.localization.resources import Called, assembled_dialogue, parse_scp
from sora_bilingual.paths import ROOT

_CURRENT = ContextVar("language_facts", default=None)


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def _tuples(value):
    if isinstance(value, list):
        return tuple(_tuples(v) for v in value)
    return value


@dataclass(frozen=True)
class HistoryFunction:
    called: tuple
    has_branch: bool

    @property
    def code_shape(self):
        # The history compiler only asks whether any branch is present. This
        # projection must never be passed to dialogue/control-flow alignment.
        return (("branch",),) if self.has_branch else ()


@dataclass(frozen=True)
class HistoryScript:
    functions: dict


@dataclass(frozen=True)
class NotificationMetadata:
    # Deliberately not a Function: the raw bytecode remains authoritative for
    # helper forwarding, branches, call alignment and dynamic stack values.
    argument_types: tuple
    call_targets: tuple


class LanguageFacts:
    def __init__(self, output):
        self.output = Path(output) / "language-facts"
        self.stats = {"hits": 0, "misses": 0, "rejected": 0, "languages": {}, "events": []}
        parser = (ROOT / "sora_bilingual/localization/resources.py").read_bytes()
        own = Path(__file__).read_bytes()
        self.codes = {
            "history": hashlib.sha256(
                parser
                + own
                + (ROOT / "sora_bilingual/localization/runtime_identity.py").read_bytes()
            ).hexdigest(),
            "manifest": hashlib.sha256(
                parser
                + own
                + (ROOT / "sora_bilingual/localization/runtime_identity.py").read_bytes()
                + (ROOT / "sora_bilingual/localization/control_dialogue.py").read_bytes()
            ).hexdigest(),
        }
        self.codes["history_provenance"] = self.codes["history"]
        self.codes["notification_metadata"] = hashlib.sha256(
            parser + own + (ROOT / "sora_bilingual/localization/dynamic_identity.py").read_bytes()
        ).hexdigest()

    def get(self, locale, kind, data, build):
        from sora_bilingual.config.locales import LOCALES

        if locale not in LOCALES or kind not in self.codes:
            raise ValueError("Unknown language fact kind or locale")
        identity = [locale, kind, self.codes[kind], hashlib.sha256(data).hexdigest()]
        path = self.output / locale / kind / (_digest(identity) + ".json")
        start = time.perf_counter()
        event = {
            "locale": locale,
            "kind": kind,
            "key": path.stem,
            "rules_sha256": identity[2],
            "resource_sha256": identity[3],
        }
        local = self.stats["languages"].setdefault(locale, {"hits": 0, "misses": 0})
        try:
            record = json.loads(path.read_text("utf-8"))
            if record["identity"] != identity or record["digest"] != _digest(record["value"]):
                raise ValueError("Language fact identity/checksum mismatch")
            value = record["value"]
        except FileNotFoundError:
            reason = "not_found_for_identity"
            value = None
        except (ValueError, KeyError, TypeError) as error:
            self.stats["rejected"] += 1
            reason = "invalid_record:" + type(error).__name__
            value = None
        if value is not None:
            self.stats["hits"] += 1
            local["hits"] += 1
            self.stats["events"].append(
                {**event, "result": "hit", "seconds": time.perf_counter() - start}
            )
            return value
        value = build()
        publish_json(path, {"identity": identity, "digest": _digest(value), "value": value})
        self.stats["misses"] += 1
        local["misses"] += 1
        self.stats["events"].append(
            {**event, "result": "miss", "reason": reason, "seconds": time.perf_counter() - start}
        )
        return value


@contextmanager
def language_facts(output):
    facts = LanguageFacts(output)
    token = _CURRENT.set(facts)
    try:
        yield facts
    finally:
        _CURRENT.reset(token)


def manifest_fact(data, locale, build):
    facts = _CURRENT.get()
    return build() if facts is None else facts.get(locale, "manifest", data, build)


def history_script(data, locale):
    """Validated SCP projection, independent of language pair and catalog scope.

    Retain every call and argument in marker-bearing functions, including unknown
    and dynamic operations that clear an active name. Other functions cannot
    produce a history marker or a marker-qualified speaker result.
    """
    from sora_bilingual.localization.runtime_identity import _history_marker

    def build():
        script = parse_scp(data)
        return {
            name: [
                [[c.target, c.kind, c.args] for c in f.called],
                any(instruction[0] == "branch" for instruction in f.code_shape),
            ]
            for name, f in script.functions.items()
            if any(
                _history_marker(call) is not None and assembled_dialogue(call) is not None
                for call in f.called
            )
        }

    facts = _CURRENT.get()
    rows = build() if facts is None else facts.get(locale, "history", data, build)
    return HistoryScript(
        {
            name: HistoryFunction(tuple(Called(c[0], c[1], _tuples(c[2])) for c in row[0]), row[1])
            for name, row in rows.items()
        }
    )


def history_provenance(data, locale):
    """Reuse exact native origins across pair/base changes, not pairing decisions."""
    from sora_bilingual.localization.runtime_identity import _history_function_facts

    def build():
        result = {}
        for name, function in parse_scp(data).functions.items():
            fact = _history_function_facts(function)
            if fact["markers"]:
                result[name] = fact
        return result

    facts = _CURRENT.get()
    return build() if facts is None else facts.get(locale, "history_provenance", data, build)


def notification_metadata(data, locale):
    """Language-local declared arguments/ordered targets, never resolved slots.

    The consumer must still read the original executable SCP program. This
    projection saves the unrelated whole-script parse on every target swap.
    """

    def build():
        return {
            name: [function.arg_types, [call.target for call in function.called]]
            for name, function in parse_scp(data).functions.items()
        }

    facts = _CURRENT.get()
    rows = build() if facts is None else facts.get(locale, "notification_metadata", data, build)
    return {name: NotificationMetadata(tuple(row[0]), tuple(row[1])) for name, row in rows.items()}

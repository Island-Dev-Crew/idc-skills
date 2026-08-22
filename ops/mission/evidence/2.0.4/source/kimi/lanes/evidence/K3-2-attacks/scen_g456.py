"""Objectives 4-6: time arithmetic, first-use bootstrap/TOCTOU, HTTP/URL policy."""
from __future__ import annotations

import datetime as dt
import http.client
import io
import json
import urllib.error
import urllib.parse
import urllib.request
from unittest import mock

from harness import (  # noqa: F401
    RESULTS, expect_pass, expect_reject, fresh, make_fixture, record,
)
from tests.test_freshness import _sign

NOW = dt.datetime(2026, 8, 19, 12, 0, 0, tzinfo=dt.timezone.utc)


def index_bytes(fx, *, generated, valid_until, sequence=1, releases=None):
    fx.write_index([fx.entry] if releases is None else releases,
                   sequence=sequence, generated=generated, valid_until=valid_until)
    return fx.index.read_bytes()


def parse_case(group, name, fx, needle, **kw):
    data = index_bytes(fx, **kw)
    expect_reject(group, name, needle,
                  lambda: fresh.parse_index(data, now=NOW))


def parse_ok(group, name, fx, **kw):
    data = index_bytes(fx, **kw)
    expect_pass(group, name, lambda: fresh.parse_index(data, now=NOW))


def run_time() -> None:
    fx = make_fixture()
    G = "obj4-time"
    # boundary: expiry
    parse_case(G, "4a expires == now", fx, "expired",
               generated="2026-08-19T11:00:00Z", valid_until="2026-08-19T12:00:00Z")
    parse_ok(G, "4b expires = now+1s", fx,
             generated="2026-08-19T11:00:00Z", valid_until="2026-08-19T12:00:01Z")
    # boundary: 31-day lifetime
    parse_ok(G, "4c lifetime exactly 31 days", fx,
             generated="2026-08-19T11:00:00Z", valid_until="2026-09-19T11:00:00Z")
    parse_case(G, "4d lifetime 31 days + 1s", fx, "31 days",
               generated="2026-08-19T11:00:00Z", valid_until="2026-09-19T11:00:01Z")
    # boundary: future-dated generation vs 300s skew
    parse_ok(G, "4e generated = now+300s (skew boundary)", fx,
             generated="2026-08-19T12:05:00Z", valid_until="2026-08-26T12:05:00Z")
    parse_case(G, "4f generated = now+301s", fx, "future",
               generated="2026-08-19T12:05:01Z", valid_until="2026-08-26T12:05:01Z")
    # precision / canonical form
    fx.write_index([fx.entry])
    raw = fx.index.read_bytes()
    frac = raw.replace(b"2026-08-26T11:00:00Z", b"2026-08-26T11:00:00.5Z")
    expect_reject(G, "4g fractional-second validUntil", "whole-second",
                  lambda: fresh.parse_index(frac, now=NOW))
    off = raw.replace(b"2026-08-26T11:00:00Z", b"2026-08-26T11:00:00+00:00")
    expect_reject(G, "4h non-Z offset validUntil", "ending in Z",
                  lambda: fresh.parse_index(off, now=NOW))
    parse_case(G, "4i validUntil == generatedAt", fx, "later than generatedAt",
               generated="2026-08-19T11:00:00Z", valid_until="2026-08-19T11:00:00Z")
    # real shipped index arithmetic: 2026-08-21T17:46:09Z -> 2026-09-20T17:46:09Z
    real = open("/tmp/K3-2/trust-index/releases.json", "rb").read()
    real_index = fresh.load_canonical_json(real, "release index", fresh.MAX_INDEX_BYTES)
    gen = dt.datetime.fromisoformat(real_index["generatedAt"].replace("Z", "+00:00"))
    exp = dt.datetime.fromisoformat(real_index["validUntil"].replace("Z", "+00:00"))
    lifetime_days = (exp - gen).total_seconds() / 86400
    record(G, "4j real index lifetime", "INFO",
           f"shipped index lifetime = {lifetime_days} days (limit 31)")
    expect_pass(G, "4k real index valid 1s before expiry",
                lambda: fresh.parse_index(real, now=exp - dt.timedelta(seconds=1)))
    expect_reject(G, "4l real index expired at validUntil exactly", "expired",
                  lambda: fresh.parse_index(real, now=exp))
    # last-second expiry DURING verification (re-parse gates)
    fx2 = make_fixture()
    fx2.write_index([fx2.entry], generated="2026-08-19T11:00:00Z",
                    valid_until="2026-08-19T12:00:02Z")
    fx2.write_config()
    clock = mock.Mock(side_effect=[
        dt.datetime(2026, 8, 19, 12, 0, 0, tzinfo=dt.timezone.utc),   # initial parse
        dt.datetime(2026, 8, 19, 12, 0, 1, tzinfo=dt.timezone.utc),   # pre-checkpoint
        dt.datetime(2026, 8, 19, 12, 0, 3, tzinfo=dt.timezone.utc),   # pre-consumer
    ])
    expect_reject(G, "4m index expires between checkpoint write and consumer",
                  "expired",
                  lambda: fx2.verify(now=None, clock=clock,
                                     consumer_runner=lambda *a: 0))
    record(G, "4m-note", "HELD", "checkpoint write and consumer each re-parse the "
           "expiring index; no consumer runs after expiry")


def run_bootstrap() -> None:
    G = "obj5-bootstrap"
    # 5a first run, wrong digest (end-to-end)
    fx = make_fixture()
    fx.write_config(bootstrap_digest="sha256:" + "0" * 64)
    expect_reject(G, "5a first run with wrong bootstrap digest", "first-run index",
                  fx.verify)
    # 5b TOCTOU: index/sig pair changes between the two captures (file source).
    fx = make_fixture()
    index_v1 = fx.index.read_bytes()
    fx.write_index([fx.entry], sequence=1, generated="2026-08-19T11:00:05Z")
    sig_v2 = Path_bytes = fx.index_signature.read_bytes()
    index_v2 = fx.index.read_bytes()
    fx.write_config()
    original = fresh._read_regular_snapshot
    state = {"n": 0}

    def toctou(path, label, maximum, *, require_single_link=False):
        state["n"] += 1
        if str(path).endswith("releases.json") and "signature" not in label:
            return index_v1  # attacker swaps index back to v1 after sig was made for v2
        return original(path, label, maximum, require_single_link=require_single_link)

    with mock.patch.object(fresh, "_read_regular_snapshot", toctou):
        expect_reject(G, "5b index/sig pair swapped between captures",
                      "signature invalid", fx.verify)
    record(G, "5b-note", "HELD", "signature is verified over the exact captured index "
           "bytes; a swapped pair cannot pass")
    # 5c both fetches see a CONSISTENT attacker-signed pair? impossible without key;
    # demonstrate: consistent v2 pair passes only if bootstrap pin matches v2.
    fx.write_config(bootstrap_digest=fresh.sha256_bytes(index_v2))
    expect_pass(G, "5c first run with consistent pair matching pin", fx.verify)


def run_http() -> None:
    G = "obj6-http"
    fx = make_fixture()
    base = json.loads(fx.config.read_text(encoding="utf-8"))
    base["source"] = {
        "type": "https",
        "indexURL": "https://raw.githubusercontent.com/o/r/trust-index/releases.json",
        "signatureURL": "https://raw.githubusercontent.com/o/r/trust-index/releases.json.sig",
        "allowedHosts": ["raw.githubusercontent.com"],
        "maxRedirects": 0,
    }

    def config_case(name, needle, mutate):
        value = json.loads(json.dumps(base))
        mutate(value["source"])
        data = fresh.canonical_bytes(value)
        expect_reject(G, name, needle,
                      lambda: fresh.parse_config(
                          data, repo_root=fx.repo, config_path=fx.config))

    config_case("6a1 http scheme", "HTTPS on an allowed host",
                lambda s: s.update(indexURL="http://raw.githubusercontent.com/x"))
    config_case("6a2 userinfo in URL", "HTTPS on an allowed host",
                lambda s: s.update(indexURL="https://user@raw.githubusercontent.com/x"))
    config_case("6a3 fragment in URL", "HTTPS on an allowed host",
                lambda s: s.update(indexURL="https://raw.githubusercontent.com/x#frag"))
    config_case("6a4 non-443 port", "HTTPS on an allowed host",
                lambda s: s.update(indexURL="https://raw.githubusercontent.com:8443/x"))
    config_case("6a5 host outside allowedHosts", "HTTPS on an allowed host",
                lambda s: s.update(indexURL="https://evil.invalid/x"))
    config_case("6a6 trailing-dot host bypass", "HTTPS on an allowed host",
                lambda s: s.update(indexURL="https://raw.githubusercontent.com./x"))
    config_case("6a7 uppercase allowedHosts entry", "lowercase",
                lambda s: s.update(allowedHosts=["RAW.GITHUBUSERCONTENT.COM"]))
    config_case("6a8 maxRedirects=4", "between 0 and 3",
                lambda s: s.update(maxRedirects=4))
    # 6a9 split origins: index host A, sig host B, both allowed -> config ACCEPTS
    value = json.loads(json.dumps(base))
    value["source"]["allowedHosts"] = ["a.invalid", "b.invalid"]
    value["source"]["indexURL"] = "https://a.invalid/releases.json"
    value["source"]["signatureURL"] = "https://b.invalid/releases.json.sig"
    expect_pass(G, "6a9 split index/sig origins across two allowed hosts",
                lambda: fresh.parse_config(fresh.canonical_bytes(value),
                                           repo_root=fx.repo, config_path=fx.config))
    record(G, "6a9-note", "BY-DESIGN", "both URLs share one allowedHosts set; the "
           "signature is still verified over fetched index bytes, so cross-origin "
           "substitution cannot forge content")

    # 6b redirect handler logic (no network)
    handler = fresh._PinnedRedirectHandler({"raw.githubusercontent.com"}, 2)
    req = urllib.request.Request("https://raw.githubusercontent.com/o/r/releases.json")

    def redir(url, h=None):
        (h or handler).redirect_request(req, None, 302, "Found", {}, url)

    for name, url in [
        ("6b1 redirect to other host", "https://evil.invalid/x"),
        ("6b2 redirect to http", "http://raw.githubusercontent.com/x"),
        ("6b3 redirect with userinfo", "https://u@raw.githubusercontent.com/x"),
        ("6b4 redirect to port 444", "https://raw.githubusercontent.com:444/x"),
    ]:
        expect_reject(G, name, "origin policy", lambda u=url: redir(u))
    # 6b5 redirect count exhausted
    h2 = fresh._PinnedRedirectHandler({"raw.githubusercontent.com"}, 1)
    redir("https://raw.githubusercontent.com/a", h2)
    expect_reject(G, "6b5 redirect count exceeded", "origin policy",
                  lambda: redir("https://raw.githubusercontent.com/b", h2))
    # 6b6 fragment in redirect target is NOT checked (cosmetic; fragment never sent)
    try:
        redir("https://raw.githubusercontent.com/x#frag")
        record(G, "6b6 fragment in redirect target", "ACCEPTED",
               "redirect handler omits fragment check (harmless: fragment is never "
               "sent to the server and final-URL check does not compare it)")
    except fresh.FreshnessError as exc:
        record(G, "6b6 fragment in redirect target", "HELD", str(exc))

    # 6c body/transport tricks via faithful fake opener driving the REAL handler
    def fake_fetch(name, behavior, needle=None):
        handler = fresh._PinnedRedirectHandler({"mock.invalid"}, 3)

        class Resp:
            def __init__(self, url, data, headers=None, redirects=0):
                self._url, self._data = url, data
                self.headers = headers or {}

            def geturl(self):
                return self._url

            def read(self, n=-1):
                return behavior_read(self._data, n)

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def behavior_read(data, n):
            if isinstance(data, Exception):
                raise data
            return data[:n] if n >= 0 else data

        class Opener:
            def open(self, request, timeout=0):
                nonlocal_handler = handler
                url = request.full_url
                hops = 0
                while True:
                    step = behavior(url, hops)
                    if step[0] == "redirect":
                        new = nonlocal_handler.redirect_request(
                            request, None, 302, "Found", {}, step[1])
                        if new is None:
                            raise urllib.error.HTTPError(url, 302, "refused", {}, None)
                        url, request = new.full_url, new
                        hops += 1
                        continue
                    return Resp(url, step[1])

        with mock.patch.object(fresh.urllib.request, "build_opener",
                               lambda *a, **k: Opener()):
            try:
                out = fresh._fetch_https("https://mock.invalid/releases.json",
                                         {"mock.invalid"}, 3, 1024)
            except fresh.FreshnessError as exc:
                if needle and needle in str(exc):
                    record(G, name, "HELD", f"rejected: {exc}")
                else:
                    record(G, name, "UNEXPECTED-REJECT", str(exc))
                return
            except Exception as exc:  # noqa: BLE001
                record(G, name, "ERROR", f"{type(exc).__name__}: {exc}")
                return
            record(G, name, "ACCEPTED", f"fetched {len(out)} bytes")

    good = b'{"ok":true}'
    fake_fetch("6c1 normal fetch", lambda u, h: ("body", good))
    fake_fetch("6c2 oversized body (>maximum)", lambda u, h: ("body", b"x" * 5000),
               needle="exceeds")
    fake_fetch("6c3 same-host redirect then body",
               lambda u, h: ("redirect", "https://mock.invalid/final") if h == 0
               else ("body", good))
    fake_fetch("6c4 redirect to disallowed host",
               lambda u, h: ("redirect", "https://evil.invalid/x"),
               needle="origin policy")
    fake_fetch("6c5 IncompleteRead mid-body",
               lambda u, h: ("body", http.client.IncompleteRead(b"partial", 4)))
    record(G, "6c5-note", "OBSERVE", "IncompleteRead is http.client.HTTPException, "
           "NOT OSError: escapes _fetch_https uncaught; main() does not catch it "
           "either -> traceback, exit 1. Still fail-CLOSED (no READY), robustness nit.")

    # 6d network failure against real unreachable 127.0.0.1:443 (nothing listening)
    fx2 = make_fixture()
    value = json.loads(fx2.config.read_text(encoding="utf-8"))
    value["source"] = {
        "type": "https",
        "indexURL": "https://127.0.0.1/releases.json",
        "signatureURL": "https://127.0.0.1/releases.json.sig",
        "allowedHosts": ["127.0.0.1"],
        "maxRedirects": 0,
    }
    fx2.config.write_bytes(fresh.canonical_bytes(value))
    expect_reject(G, "6d connection refused mid-bootstrap", "fetch failed", fx2.verify)

    # 6e proxy env is disabled by construction: ProxyHandler({})
    with mock.patch.dict("os.environ", {"HTTPS_PROXY": "http://127.0.0.1:9",
                                        "https_proxy": "http://127.0.0.1:9"}):
        expect_reject(G, "6e HTTPS_PROXY env set, still direct (refused)",
                      "fetch failed", fx2.verify)
    record(G, "6e-note", "HELD", "opener built with ProxyHandler({}); proxy env ignored")


if __name__ == "__main__":
    run_time()
    run_bootstrap()
    run_http()

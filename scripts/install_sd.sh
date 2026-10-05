#!/bin/bash
# Copy the built mod onto the SD card, remove only our own stale variant folders,
# preselect a menu choice, verify every file byte-for-byte, then eject.
# usage: [ALLEY="<alley choice text>"] scripts/install_sd.sh [ball-choice-text-to-preselect]
set -euo pipefail
S="${SD:-/Volumes/4G_SD}"
M="$(cd "$(dirname "$0")/.." && pwd)"
PRESELECT="${1:-TEST:}"
[ -d "$S/riivolution" ] || { echo "SD card not mounted at $S"; exit 1; }

KEEP=()
while IFS= read -r k; do KEEP+=("$k"); done < <(cd "$M/output/WSR_ball_mod" && find . -mindepth 1 -maxdepth 1 -type d -exec basename {} \; | sort)
mkdir -p "$S/WSR_ball_mod"

# remove stale / malformed entries we created earlier (only inside our own folder)
while IFS= read -r -d '' p; do
  name="$(basename "$p")"
  keep=0
  for k in "${KEEP[@]}"; do [ "$name" = "$k" ] && keep=1; done
  case "$name" in README.txt|._*) keep=1;; esac
  if [ $keep = 0 ]; then echo "removing stale: $(printf '%q' "$name")"; rm -rf -- "$p"; fi
done < <(find "$S/WSR_ball_mod" -mindepth 1 -maxdepth 1 -print0)

for v in "${KEEP[@]}"; do
  mkdir -p "$S/WSR_ball_mod/$v"
  if [ "$v" = alley ] || [ "$v" = trail ]; then
    find "$S/WSR_ball_mod/$v" -mindepth 1 -maxdepth 1 -name '*.carc' -exec rm -f {} +
    for f in "$M/output/WSR_ball_mod/$v/"*.carc; do cp -X "$f" "$S/WSR_ball_mod/$v/"; done
  else
    cp -X "$M/output/WSR_ball_mod/$v/common.carc" "$S/WSR_ball_mod/$v/common.carc"
  fi
done
cp -X "$M/output/README.txt" "$S/WSR_ball_mod/README.txt"
cp -X "$M/output/riivolution/WSR_ball_mod.xml" "$S/riivolution/WSR_ball_mod.xml"

# index of a choice within its own <option> block (1-based, as Riivolution's config expects)
choice_index() {
  awk -v opt="$1" -v want="$2" '
    /<option name=/ { inopt = index($0, "name=\"" opt "\"") > 0; n = 0; next }
    /<\/option>/ { inopt = 0 }
    inopt && /<choice/ { n++; if (index($0, want) && !found) { print n; found = 1 } }' "$S/riivolution/WSR_ball_mod.xml"
}
N=$(choice_index "Ball mod" "$PRESELECT")
ALLEY_LINE=""
if [ -n "${ALLEY:-}" ]; then
  A=$(choice_index "Alley" "$ALLEY")
  [ -n "$A" ] || { echo "no Alley choice matching '$ALLEY'"; exit 1; }
  ALLEY_LINE="  <option id=\"WSR Custom Bowling BallsAlley\" default=\"$A\"/>"
fi
cat > "$S/riivolution/config/RZTE.xml" <<EOF
<?xml version="1.0"?>
<riivolution version="2">
  <option id="WSR Custom Bowling BallsBall mod" default="$N"/>
${ALLEY_LINE}
${EXTRA_OPTIONS:-}
</riivolution>
EOF
dot_clean -m "$S/WSR_ball_mod" "$S/riivolution" 2>/dev/null || true
sync

fail=0
for v in "${KEEP[@]}"; do
  if [ "$v" = alley ] || [ "$v" = trail ]; then
    for f in "$M/output/WSR_ball_mod/$v/"*.carc; do
      b=$(basename "$f")
      if cmp -s "$S/WSR_ball_mod/$v/$b" "$f"; then echo "ok   $v/$b"; else echo "FAIL $v/$b"; fail=1; fi
    done
    continue
  fi
  if cmp -s "$S/WSR_ball_mod/$v/common.carc" "$M/output/WSR_ball_mod/$v/common.carc"; then echo "ok   $v"; else echo "FAIL $v"; fail=1; fi
done
cmp -s "$S/riivolution/WSR_ball_mod.xml" "$M/output/riivolution/WSR_ball_mod.xml" && echo "ok   xml" || { echo "FAIL xml"; fail=1; }
# every folder the XML points at must exist on the card
for ext in $(grep -o 'external="[^"]*"' "$S/riivolution/WSR_ball_mod.xml" | cut -d'"' -f2); do
  [ -f "$S$ext" ] || { echo "FAIL missing $ext"; fail=1; }
done
echo "--- card contents:"; find "$S/WSR_ball_mod" -mindepth 1 -maxdepth 1 -not -name '._*' -exec basename {} \; | sort
echo "--- preselected Ball mod choice $N, Alley choice ${A:-none}"; cat "$S/riivolution/config/RZTE.xml"
[ $fail = 0 ] || { echo "VERIFY FAILED - not ejecting"; exit 1; }
[ "${NOEJECT:-0}" = 1 ] || diskutil eject "$S"

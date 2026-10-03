#!/bin/bash
# Copy the built mod onto the SD card, remove only our own stale variant folders,
# preselect a menu choice, verify every file byte-for-byte, then eject.
# usage: scripts/install_sd.sh [menu-choice-text-to-preselect]
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
  cp -X "$M/output/WSR_ball_mod/$v/common.carc" "$S/WSR_ball_mod/$v/common.carc"
done
cp -X "$M/output/README.txt" "$S/WSR_ball_mod/README.txt"
cp -X "$M/output/riivolution/WSR_ball_mod.xml" "$S/riivolution/WSR_ball_mod.xml"

N=$(grep "<choice" "$S/riivolution/WSR_ball_mod.xml" | grep -n -F "$PRESELECT" | head -1 | cut -d: -f1)
cat > "$S/riivolution/config/RZTE.xml" <<EOF
<?xml version="1.0"?>
<riivolution version="2">
  <option id="WSR Custom Bowling BallsBall mod" default="$N"/>
${EXTRA_OPTIONS:-}
</riivolution>
EOF
dot_clean -m "$S/WSR_ball_mod" "$S/riivolution" 2>/dev/null || true
sync

fail=0
for v in "${KEEP[@]}"; do
  if cmp -s "$S/WSR_ball_mod/$v/common.carc" "$M/output/WSR_ball_mod/$v/common.carc"; then echo "ok   $v"; else echo "FAIL $v"; fail=1; fi
done
cmp -s "$S/riivolution/WSR_ball_mod.xml" "$M/output/riivolution/WSR_ball_mod.xml" && echo "ok   xml" || { echo "FAIL xml"; fail=1; }
# every folder the XML points at must exist on the card
for ext in $(grep -o 'external="[^"]*"' "$S/riivolution/WSR_ball_mod.xml" | cut -d'"' -f2); do
  [ -f "$S$ext" ] || { echo "FAIL missing $ext"; fail=1; }
done
echo "--- card contents:"; find "$S/WSR_ball_mod" -mindepth 1 -maxdepth 1 -not -name '._*' -exec basename {} \; | sort
echo "--- preselected choice $N:"; grep "<choice" "$S/riivolution/WSR_ball_mod.xml" | sed -n "${N}p" | sed 's/.*name="\([^"]*\)".*/\1/'
[ $fail = 0 ] || { echo "VERIFY FAILED - not ejecting"; exit 1; }
[ "${NOEJECT:-0}" = 1 ] || diskutil eject "$S"

#!/bin/sh
# Fetch the public inputs ghostldr builds against (into build/, which git ignores):
#   build/nid/known_names.txt  PS4 symbol names for NID resolution (idc/ps4libdoc)
#   build/luac0re-src          Luac0re 2.4b (Gezine, MIT): Lua bundle + PS2 save
#   build/LibOrbisPkg          LibOrbisPkg (maxton, LGPL-3.0) at a pinned commit, with
#                              tools/pkgextract-cli/LibOrbisPkg.patch: pkgextract-cli's library
# The game dump (build/ghost/app0) is your own and is never fetched.
set -e
cd "$(dirname "$0")/.."
mkdir -p build/nid
[ -s build/nid/known_names.txt ] ||
    curl -fsSL -o build/nid/known_names.txt https://raw.githubusercontent.com/idc/ps4libdoc/doc/known_names.txt
[ -d build/luac0re-src ] ||
    git clone --depth 1 --branch 2.4b https://github.com/Gezine/Luac0re build/luac0re-src
LIBORBISPKG=643477263b2644e0803e0f58b8726ea4e3f3b7d4
if [ "$(cat build/LibOrbisPkg/.pkgextract-patched 2>/dev/null)" != "$LIBORBISPKG" ]; then
    rm -rf build/LibOrbisPkg
    git init -q build/LibOrbisPkg
    git -C build/LibOrbisPkg fetch -q --depth 1 https://github.com/maxton/LibOrbisPkg "$LIBORBISPKG"
    git -C build/LibOrbisPkg -c advice.detachedHead=false checkout -q FETCH_HEAD
    git -C build/LibOrbisPkg apply "$PWD/tools/pkgextract-cli/LibOrbisPkg.patch"
    echo "$LIBORBISPKG" > build/LibOrbisPkg/.pkgextract-patched
fi
echo "known_names.txt: $(wc -l < build/nid/known_names.txt) names; Luac0re: build/luac0re-src; LibOrbisPkg: build/LibOrbisPkg"

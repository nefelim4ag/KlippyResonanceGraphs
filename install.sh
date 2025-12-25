#!/usr/bin/env bash

PWD="$(dirname $0)"
cd "$PWD"
if [ ! -d .venv ]; then
    python3 -m venv .venv --system-site-packages
fi

source .venv/bin/activate
pip install -r ./requirements.txt

if [ ! -f ~/printer_data/config/graph-gen-macros.cfg ]; then
    ln -svr ./graph-gen-macros.cfg ~/printer_data/config/graph-gen-macros.cfg
fi

PRINTER_CFG=~/printer_data/config/printer.cfg
if ! grep -c '\[include graph-gen-macros.cfg\]' ${PRINTER_CFG} > /dev/null; then
    sed -i '1s/^/[include graph-gen-macros.cfg]\n/' ${PRINTER_CFG}
fi

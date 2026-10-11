#!/usr/bin/env bash
# Builds the optional C++ backtest core (fastbt). Kairos works without it,
# it just falls back to NumPy. Run from anywhere: ./build_cpp.sh
set -e
cd "$(dirname "$0")"

PY=${PYTHON:-python3}

if ! command -v c++ >/dev/null 2>&1; then
  echo "No C++ compiler found. On Ubuntu/WSL run:  sudo apt install -y g++"
  exit 1
fi

INCDIR=$($PY -c "import sysconfig;print(sysconfig.get_paths()['include'])")
if [ ! -f "$INCDIR/Python.h" ]; then
  VER=$($PY -c "import sys;print(f'{sys.version_info.major}.{sys.version_info.minor}')")
  echo "Python headers missing ($INCDIR/Python.h). On Ubuntu/WSL run:"
  echo "  sudo apt install -y python${VER}-dev     (or: sudo apt install -y python3-dev)"
  exit 1
fi

$PY -m pip install --quiet pybind11 2>/dev/null || $PY -m pip install --quiet --break-system-packages pybind11

EXT=$($PY -c "import sysconfig;print(sysconfig.get_config_var('EXT_SUFFIX'))")
INC=$($PY -m pybind11 --includes)

echo "Compiling cpp/fastbt.cpp ..."
# -march=native is fastest locally; Docker sets ARCH_FLAGS to a portable target
ARCH_FLAGS=${ARCH_FLAGS:--march=native}
c++ -O3 $ARCH_FLAGS -Wall -shared -std=c++17 -fPIC $INC cpp/fastbt.cpp -o "fastbt$EXT"

$PY -c "import fastbt, numpy as np; r=fastbt.strat_returns(np.array([1.,2.,4.]), np.array([1.,1.,1.]), 0.0); assert abs(r[2]-1.0)<1e-12; print('fastbt OK ->', fastbt.__file__)"

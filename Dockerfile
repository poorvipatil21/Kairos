FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements-deploy.txt .
RUN pip install --no-cache-dir -r requirements-deploy.txt

COPY . .

# C++ engine, built for a portable x86-64 target (not -march=native, the host CPU may differ)
RUN ARCH_FLAGS="-march=x86-64-v2" ./build_cpp.sh || echo "C++ build failed, NumPy fallback will be used"

# Run the strategy backtests once at build time so the leaderboard has data
RUN python main.py || echo "main.py failed at build time, leaderboard will be empty"

ENV PORT=8000
EXPOSE 8000
CMD uvicorn api.server:app --host 0.0.0.0 --port ${PORT}

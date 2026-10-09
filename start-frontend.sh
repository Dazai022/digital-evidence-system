#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/frontend"
[ -f .env.local ] || cp .env.local.example .env.local
[ -d node_modules ] || npm install
npm run dev

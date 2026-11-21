#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"

echo "=== 1. List seeded managers ==="
curl -sS "$BASE_URL/managers" | python3 -m json.tool

echo -e "\n=== 2. Create company ==="
curl -sS -X POST "$BASE_URL/companies" \
  -H "Content-Type: application/json" \
  -d '{"name":"ТОО Алматы Трейд Компани","bin":"170340021554","phone":"+77011234567"}' | python3 -m json.tool

echo -e "\n=== 3. List companies ==="
curl -sS "$BASE_URL/companies?limit=20&offset=0" | python3 -m json.tool

echo -e "\n=== 4. Create meeting (Mon 10:00 Asia/Almaty = 05:00Z) ==="
curl -sS -X POST "$BASE_URL/meetings" \
  -H "Content-Type: application/json" \
  -d '{"company_id":1,"manager_id":1,"scheduled_at":"2026-11-23T05:00:00Z"}' | python3 -m json.tool

echo -e "\n=== 5. Record call with result=meeting_set ==="
curl -sS -X POST "$BASE_URL/calls" \
  -H "Content-Type: application/json" \
  -d '{"company_id":1,"manager_id":1,"result":"meeting_set","meeting_id":1,"notes":"Встреча подтверждена"}' | python3 -m json.tool

echo -e "\n=== 6. Reschedule meeting (Mon 11:00 Asia/Almaty = 06:00Z) ==="
curl -sS -X PATCH "$BASE_URL/meetings/1" \
  -H "Content-Type: application/json" \
  -d '{"scheduled_at":"2026-11-23T06:00:00Z"}' | python3 -m json.tool

echo -e "\n=== 7. Get manager schedule for 2026-11-23 (Asia/Almaty) ==="
curl -sS "$BASE_URL/managers/1/schedule?date=2026-11-23" | python3 -m json.tool

echo -e "\n=== 8. Cancel meeting ==="
curl -sS -X PATCH "$BASE_URL/meetings/1" \
  -H "Content-Type: application/json" \
  -d '{"status":"cancelled"}' | python3 -m json.tool

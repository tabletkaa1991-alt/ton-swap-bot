#!/usr/bin/env bash
# Установка бота-обменника на чистый Ubuntu 22.04/24.04 (запускать от root или с sudo).
# Предполагается, что проект уже скопирован в /opt/ton-swap-bot вместе с .env.
#
#   DOMAIN=swap.example.com bash deploy/install.sh
#
# Ставит Docker, поднимает бота в одном контейнере (статика + /api + бот) и Caddy
# для HTTPS. Бесплатные PaaS (Render/Koyeb) этот скрипт не используют — им хватает
# deploy/Dockerfile, см. DEPLOY-FREE.md.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/ton-swap-bot}"
DOMAIN="${DOMAIN:-}"

if [[ ! -f "$APP_DIR/.env" ]]; then
  echo "✗ нет $APP_DIR/.env — скопируйте проект и файл окружения" >&2
  exit 1
fi
if [[ -z "$DOMAIN" ]]; then
  echo "✗ задайте домен: DOMAIN=swap.example.com $0" >&2
  exit 1
fi

echo "== пакеты"
apt-get update -qq
apt-get install -y -qq ca-certificates curl iptables netfilter-persistent >/dev/null

# На образах Oracle Cloud внутренний фаервол закрыт: без этого Let's Encrypt
# не пройдёт HTTP-проверку и HTTPS не поднимется. 8080 наружу не открываем —
# он нужен только внутри docker-сети.
echo "== фаервол (80/443)"
for port in 80 443; do
  iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null \
    || iptables -I INPUT -p tcp --dport "$port" -j ACCEPT
done
netfilter-persistent save >/dev/null 2>&1 || true
if command -v ufw >/dev/null; then
  ufw allow 80/tcp >/dev/null 2>&1 || true
  ufw allow 443/tcp >/dev/null 2>&1 || true
fi

echo "== docker"
if ! command -v docker >/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin >/dev/null
fi

echo "== caddy-конфиг для $DOMAIN"
sed -i "s/^swap\.example\.com/$DOMAIN/" "$APP_DIR/deploy/Caddyfile"

# WEBAPP_URL — единственное, что нужно боту знать про домен: от него строятся
# кнопка WebApp, кнопка меню и манифест TON Connect (манифест отдаётся на лету).
if grep -q '^WEBAPP_URL=' "$APP_DIR/.env"; then
  sed -i "s|^WEBAPP_URL=.*|WEBAPP_URL=https://$DOMAIN/|" "$APP_DIR/.env"
else
  printf '\nWEBAPP_URL=https://%s/\n' "$DOMAIN" >> "$APP_DIR/.env"
fi

echo "== сборка и запуск"
cd "$APP_DIR"
docker compose -f deploy/docker-compose.yml up -d --build

echo "== проверка (до 90 секунд: контейнер + сертификат)"
ok=0
for _ in $(seq 1 30); do
  sleep 3
  if curl -fsS --max-time 5 "http://127.0.0.1:8080/api/health" >/dev/null 2>&1; then ok=1; break; fi
done
if [[ "$ok" != "1" ]]; then
  echo "✗ бот не ответил на /api/health — смотрите: docker compose -f deploy/docker-compose.yml logs bot" >&2
  exit 1
fi
echo "✓ бот отвечает локально"

for _ in $(seq 1 20); do
  if curl -fsS --max-time 8 "https://$DOMAIN/api/health" >/dev/null 2>&1; then
    echo "✓ https://$DOMAIN/api/health — 200"
    echo "готово: https://$DOMAIN/ и кнопка «Обмен» в боте"
    exit 0
  fi
  sleep 3
done
echo "⚠ локально всё работает, но https://$DOMAIN ещё не отвечает."
echo "  Проверьте A-запись домена на IP сервера и логи Caddy:"
echo "  docker compose -f deploy/docker-compose.yml logs caddy"

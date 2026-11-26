#!/bin/zsh
# Відправка проєкту на GitHub.
# Токен вводиться у звичайному вікні macOS (замість символів — крапки),
# тому його не видно в Терміналі й він не потрапляє в історію команд.
# Після першого успіху macOS запам'ятовує токен у «Зв'язці ключів»,
# і далі достатньо просто: git push
#
# Запуск з головної папки проєкту:  zsh tools/github_push.sh

cd "$(dirname "$0")/.." || exit 1
GH_USER="polly-1220"

TOKEN=$(osascript -e 'text returned of (display dialog "Встав токен GitHub (github_pat_…) через Cmd + V і натисни OK" default answer "" with hidden answer with title "ReBuildDrone → GitHub" giving up after 300)')
TOKEN=$(printf "%s" "$TOKEN" | tr -d '[:space:]')
if [ -z "$TOKEN" ]; then
  echo "Скасовано: токен не введено."
  exit 1
fi

# Зберігаємо токен у «Зв'язці ключів» macOS
printf "protocol=https\nhost=github.com\nusername=%s\npassword=%s\n\n" "$GH_USER" "$TOKEN" | git credential approve
unset TOKEN

if GIT_TERMINAL_PROMPT=0 git push -u origin main; then
  echo ""
  echo "✅ Готово! Файли на GitHub."
else
  # Невдалий токен прибираємо, щоб не заважав наступній спробі
  printf "protocol=https\nhost=github.com\nusername=%s\n\n" "$GH_USER" | git credential reject
  echo ""
  echo "❌ Не вдалося. Перевір токен: репозиторій jubilant-tribble, Contents → Read and write."
fi

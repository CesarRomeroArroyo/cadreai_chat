#!/usr/bin/env bash
set -euo pipefail

readonly app_root="/opt/cadre-ai"
readonly current_link="${app_root}/current"
readonly previous_link="${app_root}/previous"

wait_for_health() {
  local attempts=0

  while [[ "${attempts}" -lt 10 ]]; do
    if curl --fail --silent --max-time 2 http://127.0.0.1:8010/health >/dev/null 2>&1; then
      return 0
    fi
    attempts=$((attempts + 1))
    sleep 1
  done

  return 1
}

if [[ "${EUID}" -ne 0 ]]; then
  printf 'Run as root.\n' >&2
  exit 1
fi

current_release="$(readlink -f "${current_link}")"
previous_release="$(readlink -f "${previous_link}")"

if [[ ! -d "${current_release}" || ! -d "${previous_release}" ]]; then
  printf 'Both current and previous releases must exist.\n' >&2
  exit 1
fi

case "${current_release}:${previous_release}" in
  "${app_root}"/releases/*:"${app_root}"/releases/*) ;;
  *)
    printf 'Refusing to switch links outside release directory.\n' >&2
    exit 1
    ;;
esac

ln -sfn "${previous_release}" "${app_root}/current.next"
mv -Tf "${app_root}/current.next" "${current_link}"
ln -sfn "${current_release}" "${app_root}/previous.next"
mv -Tf "${app_root}/previous.next" "${previous_link}"

systemctl restart cadre-ai.service

if ! wait_for_health; then
  ln -sfn "${current_release}" "${app_root}/current.next"
  mv -Tf "${app_root}/current.next" "${current_link}"
  ln -sfn "${previous_release}" "${app_root}/previous.next"
  mv -Tf "${app_root}/previous.next" "${previous_link}"
  systemctl restart cadre-ai.service
  wait_for_health || true
  printf 'Rollback target failed health check; original release restored.\n' >&2
  exit 1
fi

printf 'Active release: %s\n' "${previous_release}"
printf 'Previous release: %s\n' "${current_release}"

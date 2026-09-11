#!/usr/bin/env bash
set -euo pipefail

readonly app_root="/opt/cadre-ai"
readonly current_link="${app_root}/current"
readonly previous_link="${app_root}/previous"

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

if ! curl --fail --silent --show-error --max-time 10 http://127.0.0.1:8010/health >/dev/null; then
  ln -sfn "${current_release}" "${app_root}/current.next"
  mv -Tf "${app_root}/current.next" "${current_link}"
  ln -sfn "${previous_release}" "${app_root}/previous.next"
  mv -Tf "${app_root}/previous.next" "${previous_link}"
  systemctl restart cadre-ai.service
  printf 'Rollback target failed health check; original release restored.\n' >&2
  exit 1
fi

printf 'Active release: %s\n' "${previous_release}"
printf 'Previous release: %s\n' "${current_release}"

#!/bin/sh
set -eu
# Migrations are deliberately not run here; the deployment gate owns them.
exec "$@"

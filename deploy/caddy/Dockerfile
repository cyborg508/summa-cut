# Caddy z wtyczką DNS Cloudflare (do challenge ACME DNS-01 dla Let's Encrypt).
# Budowany lokalnie na drukpolu jako obraz `summa-caddy:local` — TrueNAS Apps (Docker)
# referuje go po tagu. Caddyfile wbudowany w obraz; token CF wstrzykiwany przez env.
FROM caddy:2-builder AS builder
RUN xcaddy build --with github.com/caddy-dns/cloudflare

FROM caddy:2
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
COPY Caddyfile /etc/caddy/Caddyfile

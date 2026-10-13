# Vendored vizarr (RFC-7 prototype)

Copy of [biongff/vizarr](https://github.com/biongff/vizarr) at v1.3.1 (`31d7052`), MIT licensed
(see `LICENSE`, unchanged), plus local changes for the draft RFC-8 / RFC-7 examples in this repo:
RFC-8 multiscale/collection reading, RFC-7 `coordinates`, `default_rendering`, `biological_metadata`
popover (bioregistry links), label-layer bio, z interval marks. Not an official vizarr release.

Run: `cd vizarr && pnpm install && pnpm dev`, then open
`http://localhost:5173/?source=<CORS server>/rfc7_7_collection.zarr`.

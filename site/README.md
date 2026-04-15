# Public Stats Frontend

This directory contains the GitHub Pages frontend for public Swiss IT job statistics.

- source code lives in `src/`
- snapshot JSON files are copied from `../public_stats/data/` into `public/data/` during `npm run build`
- Vite emits the static site to `site/dist/`

The frontend reads only aggregated JSON snapshots. It does not use SQLite or raw vacancy descriptions.

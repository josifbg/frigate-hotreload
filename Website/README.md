# Frigate Hotreload Docs

This directory contains the Docusaurus documentation site for the [Frigate Hotreload](https://github.com/josifbg/frigate-hotreload) project.

## Getting Started Locally

1. Navigate into this `website` directory.
2. Install dependencies:
   ```bash
   npm install
   ```
3. Start the development server:
   ```bash
   npm run start
   ```
4. Open `http://localhost:3000` in your browser.

## Deployment

This site is automatically deployed to GitHub Pages via GitHub Actions. To deploy manually run:

```bash
npm run build
```

and commit the contents of the `build/` directory to the `gh-pages` branch (the CI config handles this automatically).

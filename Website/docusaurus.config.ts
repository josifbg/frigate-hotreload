import { type Config } from '@docusaurus/types';

const config: Config = {
  title: 'Frigate Hotreload docs',
  tagline: 'HotReload your frigate configuration on the fly',
  url: 'https://josifbg.github.io',
  baseUrl: '/frigate-hotreload/',
  onBrokenLinks: 'warn',
  onBrokenMarkdownLinks: 'warn',
  organizationName: 'josifbg',
  projectName: 'frigate-hotreload',
  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },
  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: require.resolve('./sidebars.ts'),
          routeBasePath: '/',
          editUrl: 'https://github.com/josifbg/frigate-hotreload/tree/main/Website',
        },
        blog: false,
        theme: {
customCss: [require.resolve('./src/css/custom.css')],

        },
      },
    ],
  ],
  themeConfig: {
    navbar: {
      title: 'Frigate Hotreload',
      items: [
        {
          type: 'doc',
          docId: 'intro',
          position: 'left',
          label: 'Docs',
        },
        {
          href: 'https://github.com/josifbg/frigate-hotreload',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Docs',
          items: [
            {
              label: 'Getting Started',
              to: 'getting-started',
            },
            {
              label: 'API Overview',
              to: 'api/overview',
            },
          ],
        },
        {
          title: 'Community',
          items: [
            {
              label: 'GitHub Issues',
              href: 'https://github.com/josifbg/frigate-hotreload/issues',
            },
          ],
        },
      ],
      copyright: `© ${new Date().getFullYear()} Josif Tcheresharov`,
    },
    colorMode: {
      defaultMode: 'light',
      respectPrefersColorScheme: true,
    },
  },
};

export default config;

import type { SidebarsConfig } from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  docs: [
    {
      type: 'doc',
      id: 'intro',
      label: 'Introduction',
    },
    {
      type: 'doc',
      id: 'getting-started',
      label: 'Getting Started',
    },
    {
      type: 'category',
      label: 'API',
      collapsible: true,
      items: [
        'api/overview',
      ],
    },
    {
      type: 'category',
      label: 'Operations',
      collapsible: true,
      items: [
        'operations/runbook',
      ],
    },
  ],
};

export default sidebars;

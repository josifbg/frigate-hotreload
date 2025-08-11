import React from 'react';
import Layout from '@theme/Layout';
import Link from '@docusaurus/Link';

export default function Home(): JSX.Element {
  return (
    <Layout
      title="Frigate Hotreload"
      description="Documentation for the Frigate Hotreload project"
    >
      <header className="hero hero--primary">
        <div className="container">
          <h1 className="hero__title">Frigate Hotreload Docs</h1>
          <p className="hero__subtitle">
            Hot reload your Frigate configuration without downtime
          </p>
          <div>
            <Link className="button button--secondary button--lg" to="/getting-started">
              Get Started
            </Link>
          </div>
        </div>
      </header>
      <main>{/* Additional content could go here */}</main>
    </Layout>
  );
}

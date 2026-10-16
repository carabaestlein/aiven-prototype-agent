import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Entity } from '@backstage/catalog-model';
import { useApi } from '@backstage/core-plugin-api';
import { catalogApiRef } from '@backstage/plugin-catalog-react';
import './TemplateLibrary.css';

type TemplateState =
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; templates: Entity[] };

const Arrow = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M5 12h14m-6-6 6 6-6 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const TemplateDiagram = () => (
  <div className="hub-template-diagram" aria-hidden="true">
    <span className="hub-template-diagram__caption">ONE CONNECTED SETUP</span>
    <svg viewBox="0 0 310 210" fill="none">
      <path d="M155 67v37M64 119V99h182v20M155 104v15" stroke="#4a5156" strokeWidth="1.5" />
      <rect x="104" y="19" width="102" height="50" rx="9" fill="#142719" stroke="#5ffa74" />
      <path d="m145 36-7 8 7 8m20-16 7 8-7 8m-7-19-6 22" stroke="#5ffa74" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      {[23, 114, 205].map(x => (
        <g key={x}>
          <rect x={x} y="119" width="82" height="49" rx="8" fill="#161a1f" stroke="#3a4249" />
          <circle cx={x + 41} cy="143" r="7" fill="#5ffa74" fillOpacity="0.12" stroke="#5ffa74" />
        </g>
      ))}
      <text x="64" y="192" textAnchor="middle">MODEL</text>
      <text x="155" y="192" textAnchor="middle">STATE</text>
      <text x="246" y="192" textAnchor="middle">TRACES</text>
      <circle cx="155" cy="99" r="3" fill="#5ffa74" />
    </svg>
  </div>
);

export const TemplateLibrary = () => {
  const catalog = useApi(catalogApiRef);
  const [state, setState] = useState<TemplateState>({ status: 'loading' });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ status: 'loading' });
    catalog.getEntities({ filter: { kind: 'Template', 'spec.type': 'agent' } }).then(
      ({ items }) => {
        if (cancelled) return;
        const templates = [...items].sort((a, b) =>
          (a.metadata.title ?? a.metadata.name).localeCompare(b.metadata.title ?? b.metadata.name),
        );
        setState({ status: 'ready', templates });
      },
      () => {
        if (!cancelled) setState({ status: 'error' });
      },
    );
    return () => { cancelled = true; };
  }, [catalog, attempt]);

  return (
    <main className="hub-template-library">
      <header className="hub-template-library__header">
        <div className="hub-eyebrow">BUILT ON YOUR PLATFORM</div>
        <h1>CREATE AN AGENT<span className="hub-template-library__period">.</span></h1>
        <p>Start with your organization’s approved setup. Make it your own, review the code, then deploy on Aiven.</p>
      </header>

      <section className="hub-template-library__selection" aria-labelledby="hub-template-list-heading" aria-busy={state.status === 'loading'}>
        <div className="hub-template-library__section-title">
          <h2 id="hub-template-list-heading">Choose your starting point</h2>
          {state.status === 'ready' && <span>{state.templates.length} {state.templates.length === 1 ? 'template' : 'templates'} available</span>}
        </div>

        {state.status === 'loading' && <div className="hub-template-library__notice" role="status">Loading your organization’s templates…</div>}
        {state.status === 'error' && (
          <div className="hub-template-library__notice hub-template-library__notice--error" role="alert">
            <h3>Templates couldn’t be loaded</h3>
            <p>Check your connection and try again.</p>
            <button type="button" className="hub-button hub-button--secondary" onClick={() => setAttempt(value => value + 1)}>Try again <Arrow /></button>
          </div>
        )}
        {state.status === 'ready' && state.templates.length === 0 && (
          <div className="hub-template-library__notice" role="status">
            <h3>Your next agent starts here</h3>
            <p>No agent templates are available to your account yet. Your platform team can add an approved starting point.</p>
          </div>
        )}
        {state.status === 'ready' && state.templates.map(template => {
          const namespace = template.metadata.namespace ?? 'default';
          const name = template.metadata.name;
          const title = template.metadata.title ?? name;
          const tags = template.metadata.tags ?? [];
          const isLangGraph = tags.some(tag => tag.toLowerCase() === 'langgraph');
          return (
            <article className="hub-template-card" key={`${namespace}/${name}`} aria-labelledby={`hub-template-${namespace}-${name}`}>
              <div className="hub-template-card__content">
                <div className="hub-template-card__category">
                  <span className="hub-template-card__indicator" aria-hidden="true" />
                  {isLangGraph ? 'LANGGRAPH' : 'AGENT TEMPLATE'}
                </div>
                <h3 id={`hub-template-${namespace}-${name}`}>{title}</h3>
                {template.metadata.description && <p>{template.metadata.description}</p>}
                {tags.length > 0 && <ul className="hub-template-card__tags" aria-label="Template technologies">
                  {tags.filter(tag => tag !== 'agent').map(tag => <li key={tag}>{tag}</li>)}
                </ul>}
                <Link className="hub-button" to={`/create/templates/${encodeURIComponent(namespace)}/${encodeURIComponent(name)}`} aria-label={`Use template: ${title}`}>
                  Use template <Arrow />
                </Link>
              </div>
              <TemplateDiagram />
            </article>
          );
        })}
      </section>

      <section className="hub-template-library__workflow" aria-labelledby="hub-template-workflow-heading">
        <h2 id="hub-template-workflow-heading">From idea to your first deployment</h2>
        <ol>
          <li><span className="hub-template-library__step">01</span><div><h3>Configure</h3><p>Name your agent and choose its platform settings.</p></div><span className="hub-template-library__step-arrow" aria-hidden="true">→</span></li>
          <li><span className="hub-template-library__step">02</span><div><h3>Open a pull request</h3><p>Generate the starter in your repository, ready for review.</p></div><span className="hub-template-library__step-arrow" aria-hidden="true">→</span></li>
          <li><span className="hub-template-library__step">03</span><div><h3>Deploy on Runtime</h3><p>Merge, add your secrets and follow the deployment guide.</p></div></li>
        </ol>
      </section>
    </main>
  );
};

import { useEffect, useMemo, useState } from 'react';
import { Entity } from '@backstage/catalog-model';
import { useApi } from '@backstage/core-plugin-api';
import { catalogApiRef } from '@backstage/plugin-catalog-react';
import { Link } from 'react-router-dom';
import './CatalogPage.css';

const frameworkNames: Record<string, string> = {
  langgraph: 'LangGraph',
  langchain: 'LangChain',
  crewai: 'CrewAI',
  autogen: 'AutoGen',
  'openai-agents': 'OpenAI Agents',
};

const standard = [
  { name: 'LangGraph', role: 'Agent workflows' },
  { name: 'AI Gateway', role: 'Model access' },
  { name: 'PostgreSQL', role: 'Durable checkpoints' },
  { name: 'Langfuse', role: 'Traces & observability' },
];

function specValue(entity: Entity, key: string): string {
  const value = entity.spec?.[key];
  return typeof value === 'string' ? value : '';
}

function entityPath(entity: Entity): string {
  const namespace = entity.metadata.namespace || 'default';
  return `/catalog/${encodeURIComponent(namespace)}/${encodeURIComponent(
    entity.kind.toLocaleLowerCase('en-US'),
  )}/${encodeURIComponent(entity.metadata.name)}`;
}

function ArrowIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M5 12h14m-6-6 6 6-6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function AgentRow({ entity }: { entity: Entity }) {
  const title = entity.metadata.title || entity.metadata.name;
  const owner = specValue(entity, 'owner');
  const ownerName = owner.split('/').pop()?.replace(/^(group|user):/, '');
  const lifecycle = specValue(entity, 'lifecycle');
  const frameworks = (entity.metadata.tags || []).filter(tag => frameworkNames[tag]);

  return (
    <tr className="hub-agent-row">
      <td className="hub-agent-identity">
        <div className="hub-agent-identity-inner">
          <span className="hub-agent-mark" aria-hidden="true">
            <svg viewBox="0 0 32 32" fill="none">
              <path d="m16 5 10 6v10l-10 6-10-6V11L16 5Z" stroke="currentColor" strokeWidth="1.4" />
              <path d="m6 11 10 6 10-6M16 17v10m0-10V5" stroke="currentColor" strokeWidth="1.4" />
            </svg>
          </span>
          <div className="hub-agent-copy">
            <Link className="hub-agent-title" to={entityPath(entity)}>{title}</Link>
            <p className="hub-agent-description">
              {entity.metadata.description || 'No description has been added to the catalog.'}
            </p>
            <span className="hub-agent-slug">{entity.metadata.name}</span>
          </div>
        </div>
      </td>
      <td className="hub-agent-framework" data-label="Framework">
        {frameworks.length ? (
          <div className="hub-agent-tags">
            {frameworks.map(tag => <span className="hub-agent-tag" key={tag}>{frameworkNames[tag]}</span>)}
          </div>
        ) : <span className="hub-agent-unspecified">Not specified</span>}
      </td>
      <td className="hub-agent-owner" data-label="Owner">
        <span title={owner || undefined}>{ownerName || 'Unassigned'}</span>
      </td>
      <td className="hub-agent-lifecycle" data-label="Catalog status">
        <span className="hub-agent-status">{lifecycle || 'Not specified'}</span>
      </td>
      <td className="hub-agent-open">
        <Link to={entityPath(entity)} aria-label={`View ${title}`} className="hub-agent-open-link">
          <ArrowIcon />
        </Link>
      </td>
    </tr>
  );
}

export function CatalogPage() {
  const catalog = useApi(catalogApiRef);
  const [agents, setAgents] = useState<Entity[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setFailed(false);
    catalog.getEntities({ filter: { kind: 'Component', 'spec.type': 'agent' } })
      .then(response => {
        if (!active) return;
        setAgents([...response.items].sort((a, b) =>
          (a.metadata.title || a.metadata.name).localeCompare(b.metadata.title || b.metadata.name),
        ));
      })
      .catch(() => { if (active) setFailed(true); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [catalog, attempt]);

  const filtered = useMemo(() => {
    const term = query.trim().toLocaleLowerCase();
    if (!term) return agents;
    return agents.filter(entity => [
      entity.metadata.name,
      entity.metadata.title,
      entity.metadata.description,
      specValue(entity, 'owner'),
      ...(entity.metadata.tags || []),
    ].some(value => value?.toLocaleLowerCase().includes(term)));
  }, [agents, query]);

  return (
    <main className="hub-catalog-page">
      <header className="hub-catalog-hero">
        <div>
          <p className="hub-catalog-eyebrow">Your agent workspace</p>
          <h1 className="hub-catalog-title">Agents</h1>
          <p className="hub-catalog-intro">From first idea to your next deployment.<br />Your agents, built on a shared foundation.</p>
        </div>
        <Link className="hub-catalog-create" to="/create">
          <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M10 4v12M4 10h12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" /></svg>
          New agent
        </Link>
      </header>

      <section className="hub-catalog-section" aria-labelledby="hub-catalog-heading" aria-busy={loading}>
        <div className="hub-catalog-toolbar">
          <h2 id="hub-catalog-heading" className="hub-catalog-section-title">
            Agent catalog
            {!loading && !failed && <span className="hub-catalog-count">{agents.length}</span>}
          </h2>
          <div className="hub-catalog-search-wrap">
            <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.5" stroke="currentColor" strokeWidth="1.4" /><path d="m13 13 4 4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" /></svg>
            <label className="hub-catalog-sr-only" htmlFor="hub-agent-search">Search agents by name, owner or description</label>
            <input id="hub-agent-search" type="search" placeholder="Search agents" value={query} onChange={event => setQuery(event.target.value)} autoComplete="off" />
          </div>
        </div>

        {loading ? (
          <div className="hub-catalog-message" role="status"><span className="hub-catalog-loading-line" aria-hidden="true" /><p>Loading your agents…</p></div>
        ) : failed ? (
          <div className="hub-catalog-message" role="alert">
            <h3>We couldn’t load the catalog.</h3>
            <p>Try again to reconnect to your agent workspace.</p>
            <button className="hub-catalog-text-button" type="button" onClick={() => setAttempt(value => value + 1)}>Try again <ArrowIcon /></button>
          </div>
        ) : agents.length === 0 ? (
          <div className="hub-catalog-message">
            <h3>Your first agent starts here.</h3>
            <p>Create an agent from the approved template, or bring an existing one into the catalog.</p>
            <Link className="hub-catalog-text-button" to="/catalog-import">Register an existing agent <ArrowIcon /></Link>
          </div>
        ) : filtered.length === 0 ? (
          <div className="hub-catalog-message" role="status">
            <h3>No agents match your search.</h3>
            <p>Try an agent name, owning team or a word from its description.</p>
            <button className="hub-catalog-text-button" type="button" onClick={() => setQuery('')}>Clear search <ArrowIcon /></button>
          </div>
        ) : (
          <div className="hub-agent-table-wrap">
            <table className="hub-agent-table">
              <caption className="hub-catalog-sr-only">Registered agents. Catalog status describes the component lifecycle, not live service health.</caption>
              <thead><tr><th scope="col">Agent</th><th scope="col">Framework</th><th scope="col">Owner</th><th scope="col">Catalog status</th><th scope="col"><span className="hub-catalog-sr-only">Open agent details</span></th></tr></thead>
              <tbody>{filtered.map(entity => <AgentRow key={`${entity.metadata.namespace || 'default'}/${entity.metadata.name}`} entity={entity} />)}</tbody>
            </table>
          </div>
        )}
        {!loading && !failed && agents.length > 0 && (
          <div className="hub-catalog-footnote">
            <span aria-live="polite">{query.trim() ? `${filtered.length} of ${agents.length} agents` : `${agents.length} registered ${agents.length === 1 ? 'agent' : 'agents'}`}</span>
            <Link to="/catalog-import">Register an existing agent <span aria-hidden="true">↗</span></Link>
          </div>
        )}
      </section>

      <section className="hub-catalog-standard" aria-labelledby="hub-standard-heading">
        <div className="hub-catalog-standard-heading">
          <h2 id="hub-standard-heading">One shared foundation.</h2>
          <p>Your organization’s standard, ready for every new agent.</p>
        </div>
        <div className="hub-catalog-standard-grid">
          {standard.map((item, index) => (
            <div className="hub-catalog-standard-item" key={item.name}>
              <span className="hub-catalog-standard-number" aria-hidden="true">0{index + 1}</span>
              <h3>{item.name}</h3>
              <p>{item.role}</p>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}

export default CatalogPage;

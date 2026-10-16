import { Grid } from '@material-ui/core';
import { parseEntityRef } from '@backstage/catalog-model';
import { EntityAboutCard, EntityLayout, EntityLinksCard, EntityDependsOnResourcesCard, EntityHasComponentsCard, EntityHasResourcesCard, EntitySwitch, isComponentType, isKind } from '@backstage/plugin-catalog';
import { EntityRefLink, useEntity } from '@backstage/plugin-catalog-react';
import './EntityPage.css';

const ExternalArrow = () => <span aria-hidden="true">↗</span>;
function externalUrl(value?: string) {
  if (!value) return undefined;
  try { return ['https:', 'http:'].includes(new URL(value).protocol) ? value : undefined; }
  catch { return undefined; }
}

function AgentOverview() {
  const { entity } = useEntity();
  const annotations = entity.metadata.annotations ?? {};
  const links = (entity.metadata.links ?? []).filter(link => externalUrl(link.url));
  const findLink = (pattern: RegExp) => links.find(link => pattern.test(link.title ?? ''))?.url;
  const endpoint = externalUrl(annotations['aiven.io/endpoint']) ?? findLink(/^open agent$/i);
  const runtime = externalUrl(annotations['aiven.io/runtime-url']) ?? findLink(/^aiven runtime service$/i);
  const traces = externalUrl(annotations['langfuse.com/traces-url']) ?? findLink(/traces/i);
  const sessions = externalUrl(annotations['langfuse.com/sessions-url']) ?? findLink(/sessions/i);
  const langfuseProject = externalUrl(annotations['langfuse.com/project-url']) ?? findLink(/langfuse project/i);
  const owner = typeof entity.spec?.owner === 'string' ? entity.spec.owner : undefined;
  const system = typeof entity.spec?.system === 'string' ? entity.spec.system : undefined;
  const lifecycle = typeof entity.spec?.lifecycle === 'string' ? entity.spec.lifecycle : undefined;
  const primaryUrls = new Set([endpoint, runtime, traces, sessions, langfuseProject]);
  const remainingLinks = links.filter(link => !primaryUrls.has(link.url));
  const developmentLinks = remainingLinks.filter(link => /source|github|api|usage|doc/i.test(link.title ?? ''));
  const operationLinks = remainingLinks.filter(link => !developmentLinks.includes(link));

  return <div className="hub-agent-detail">
    <section className="hub-agent-summary" aria-labelledby="agent-summary-title">
      <div className="hub-agent-summary__copy">
        <p className="hub-eyebrow">AGENT WORKSPACE</p>
        <h2 id="agent-summary-title">Agent overview</h2>
        <p className="hub-detail-description">{entity.metadata.description || 'Explore this agent’s configuration, resources and connected services.'}</p>
        <div className="hub-detail-tags">{(entity.metadata.tags ?? []).map(tag => <span key={tag}>{tag}</span>)}</div>
      </div>
      <div className="hub-agent-summary__actions">
        {endpoint && <a className="hub-button" href={endpoint} target="_blank" rel="noopener noreferrer">Open agent <ExternalArrow /></a>}
        {runtime && <a className="hub-button hub-button--secondary" href={runtime} target="_blank" rel="noopener noreferrer">Runtime service <ExternalArrow /></a>}
        {traces && <a className="hub-agent-trace-link" href={traces} target="_blank" rel="noopener noreferrer">View Langfuse traces <ExternalArrow /></a>}
        {!endpoint && <p className="hub-agent-no-endpoint">An application endpoint has not been added to this catalog entry.</p>}
      </div>
    </section>
    <div className="hub-agent-detail__columns">
      <section className="hub-agent-panel" aria-labelledby="agent-config-title">
        <div className="hub-agent-panel__heading"><p className="hub-eyebrow">CONFIGURATION</p><h3 id="agent-config-title">At a glance</h3></div>
        <dl className="hub-agent-facts">
          <div><dt>Owner</dt><dd>{owner ? <EntityRefLink entityRef={parseEntityRef(owner, { defaultKind: 'Group', defaultNamespace: entity.metadata.namespace ?? 'default' })} /> : 'Not assigned'}</dd></div>
          <div><dt>Lifecycle</dt><dd>{lifecycle ? <span className="hub-detail-lifecycle">{lifecycle}</span> : 'Not specified'}</dd></div>
          {system && <div><dt>System</dt><dd><EntityRefLink entityRef={parseEntityRef(system, { defaultKind: 'System', defaultNamespace: entity.metadata.namespace ?? 'default' })} /></dd></div>}
          {annotations['aiven.io/project'] && <div><dt>Aiven project</dt><dd>{annotations['aiven.io/project']}</dd></div>}
          {annotations['aiven.io/service-name'] && <div><dt>Runtime service</dt><dd>{annotations['aiven.io/service-name']}</dd></div>}
          {annotations['aiven.io/deployment-state'] && <div><dt>Catalog deployment state</dt><dd>{annotations['aiven.io/deployment-state']}</dd></div>}
        </dl>
        <p className="hub-agent-panel__note">Catalog configuration. Open Runtime for current deployment status.</p>
      </section>
      <section className="hub-agent-panel" aria-labelledby="agent-observability-title">
        <div className="hub-agent-panel__heading"><p className="hub-eyebrow">OBSERVABILITY</p><h3 id="agent-observability-title">Follow the work</h3></div>
        <p className="hub-agent-panel__intro">Inspect execution traces and follow a conversation across its saved runs.</p>
        {annotations['langfuse.com/project-id'] && <p className="hub-agent-project"><span>Langfuse project</span><strong>{annotations['langfuse.com/project-id']}</strong></p>}
        <div className="hub-agent-link-list">
          {traces && <a href={traces} target="_blank" rel="noopener noreferrer"><span><strong>Traces</strong><small>Inspect execution and model observations</small></span><ExternalArrow /></a>}
          {sessions && <a href={sessions} target="_blank" rel="noopener noreferrer"><span><strong>Sessions</strong><small>Follow related runs in one place</small></span><ExternalArrow /></a>}
          {langfuseProject && <a href={langfuseProject} target="_blank" rel="noopener noreferrer"><span><strong>Project overview</strong><small>Open the connected Langfuse project</small></span><ExternalArrow /></a>}
          {!traces && !sessions && !langfuseProject && <p className="hub-agent-panel__note">No observability links have been added.</p>}
        </div>
      </section>
    </div>
    {(developmentLinks.length > 0 || operationLinks.length > 0) && <section className="hub-agent-connections" aria-labelledby="agent-links-title">
      <div><p className="hub-eyebrow">CONNECTED TOOLS</p><h3 id="agent-links-title">Keep building.</h3></div>
      <div className="hub-agent-connections__groups">
        {developmentLinks.length > 0 && <div><p className="hub-agent-link-group-label">Development</p>{developmentLinks.map(link => <a key={link.url} href={link.url} target="_blank" rel="noopener noreferrer">{link.title ?? link.url}<ExternalArrow /></a>)}</div>}
        {operationLinks.length > 0 && <div><p className="hub-agent-link-group-label">Operations</p>{operationLinks.map(link => <a key={link.url} href={link.url} target="_blank" rel="noopener noreferrer">{link.title ?? link.url}<ExternalArrow /></a>)}</div>}
      </div>
    </section>}
    <section className="hub-agent-dependencies" aria-label="Agent resource dependencies"><EntityDependsOnResourcesCard /></section>
  </div>;
}

const defaultOverview = <Grid container spacing={3}>
  <Grid item xs={12} md={6}><EntityAboutCard /></Grid>
  <Grid item xs={12} md={6}><EntityLinksCard /></Grid>
  <Grid item xs={12}><EntitySwitch>
    <EntitySwitch.Case if={isKind('component')}><EntityDependsOnResourcesCard /></EntitySwitch.Case>
    <EntitySwitch.Case if={isKind('system')}><Grid container spacing={3}><Grid item xs={12} md={6}><EntityHasComponentsCard /></Grid><Grid item xs={12} md={6}><EntityHasResourcesCard /></Grid></Grid></EntitySwitch.Case>
  </EntitySwitch></Grid>
</Grid>;
export const entityPage = <EntityLayout>
  <EntityLayout.Route path="/" title="Overview"><EntitySwitch>
    <EntitySwitch.Case if={isComponentType('agent')}><AgentOverview /></EntitySwitch.Case>
    <EntitySwitch.Case>{defaultOverview}</EntitySwitch.Case>
  </EntitySwitch></EntityLayout.Route>
</EntityLayout>;

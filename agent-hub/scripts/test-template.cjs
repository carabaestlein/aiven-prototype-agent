/* Exercise Backstage's real fetch:template action without GitHub or cloud writes. */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const yaml = require('yaml');
const Ajv = require('ajv');
const { ConfigReader } = require('@backstage/config');
const { ScmIntegrations } = require('@backstage/integration');
const { createFetchTemplateAction } = require('@backstage/plugin-scaffolder-backend');

(async () => {
  const templatePath = path.resolve('templates/langgraph-agent/template.yaml');
  const template = yaml.parse(await fs.readFile(templatePath, 'utf8'));
  const values = Object.assign({}, ...template.spec.parameters.map(page => Object.fromEntries(Object.entries(page.properties).filter(([, spec]) => spec.default !== undefined).map(([key, spec]) => [key, spec.default]))), {
    name: 'smoke-agent', langfuseProjectId: 'smoke-project', description: 'A "quoted" description: safe\nnext line',
  });
  const ajv = new Ajv({ strict: false });
  for (const page of template.spec.parameters) assert(ajv.validate({ type: 'object', required: page.required, properties: page.properties }, values), ajv.errorsText());
  const workspace = await fs.mkdtemp(path.join(os.tmpdir(), 'agent-hub-render-'));
  const temporaryDirectories = [];
  const action = createFetchTemplateAction({
    reader: { readTree: () => { throw new Error('Unexpected remote read'); } },
    integrations: ScmIntegrations.fromConfig(new ConfigReader({ integrations: { github: [{ host: 'github.com' }] } })),
  });
  try {
    const input = { ...template.spec.steps[0].input, values };
    await action.handler({ input, workspacePath: workspace, templateInfo: { baseUrl: `file://${templatePath}` }, logger: { info() {}, warn() {}, error() {}, debug() {} }, createTemporaryDirectory: async () => { const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'agent-hub-source-')); temporaryDirectories.push(dir); return dir; }, output() {}, isDryRun: true });
    const out = path.join(workspace, input.targetPath);
    const catalog = yaml.parse(await fs.readFile(path.join(out, 'catalog-info.yaml'), 'utf8'));
    assert.equal(catalog.metadata.name, 'smoke-agent');
    assert.equal(catalog.metadata.description, values.description);
    assert.equal(catalog.metadata.annotations['aiven.io/deployment-state'], 'scaffolded');
    const runtime = JSON.parse(await fs.readFile(path.join(out, 'runtime.json'), 'utf8'));
    assert.equal(runtime.user_config.application.source.containerfile_path, './agents/smoke-agent/Dockerfile');
    assert.equal(runtime.user_config.application.source.repository_url, 'https://github.com/carabaestlein/aiven-prototype-agent.git');
    assert(!runtime.user_config.application.environment_variables.some(v => /PASSWORD|SECRET|API_KEY|DATABASE_URL/.test(v.key)));
    const compose = yaml.parse(await fs.readFile(path.join(out, 'compose.yaml'), 'utf8'));
    assert(compose.services);
    for (const file of ['app.py', 'settings.py', 'service.py', 'workflow.py', 'telemetry.py', 'requirements.txt', 'constraints.txt', 'LICENSE']) {
      assert.deepEqual(await fs.readFile(path.join(out, file)), await fs.readFile(path.resolve('..', file)), `${file} drifted from Phase 1`);
    }
    assert.equal(template.spec.steps[1].input.targetPath, 'agents/${{ parameters.name }}');
    assert.equal(template.spec.steps[1].input.update, false);
    assert.equal(template.spec.steps[1].input.draft, true);
    assert(!template.spec.steps.some(step => step.action === 'catalog:register'));
    const names = await fs.readdir(out);
    assert(!names.some(name => name.endsWith('.njk')));
    assert.equal(names.filter(name => name.startsWith('.env')).length, 0);
    console.log('PASS: real Backstage fetch:template rendered the Phase 1 agent, quoted YAML, Runtime JSON, Dockerfile paths, and secret-free configuration.');
  } finally {
    await fs.rm(workspace, { recursive: true, force: true });
    for (const dir of temporaryDirectories) await fs.rm(dir, { recursive: true, force: true });
  }
})().catch(error => { console.error(error); process.exitCode = 1; });

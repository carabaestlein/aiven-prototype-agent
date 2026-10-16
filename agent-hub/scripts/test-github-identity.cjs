'use strict';

// Exercise the resolver factory actually registered by the installed GitHub
// provider module, with the checked-in catalog and no OAuth/network requests.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const yaml = require('yaml');
const providerDirectory = path.dirname(require.resolve('@backstage/plugin-auth-backend-module-github-provider'));
const { createGithubProviderSignInResolvers } = require(path.join(providerDirectory, 'resolvers.cjs.js'));

const catalogPath = path.join(__dirname, '../catalog/entities.yaml');
const user = yaml.parseAllDocuments(fs.readFileSync(catalogPath, 'utf8'))
  .map(document => document.toJSON())
  .find(entity => entity.kind === 'User' && entity.metadata.name === 'carabaestlein');
assert.ok(user, 'The permitted GitHub user must exist in the real catalog');
const annotation = 'github.com/user-id';
const verifiedNodeId = 'MDQ6VXNlcjM0NDc1ODM1';
const ownership = ['user:default/carabaestlein', 'group:default/aiven-platform'];

function fixture(catalogUser = user) {
  const issued = [];
  const queries = [];
  const credentials = { principal: { type: 'service', subject: 'plugin:auth' } };
  const resolver = createGithubProviderSignInResolvers({
    auth: { async getOwnServiceCredentials() { return credentials; } },
    catalog: {
      async getEntities(query, options) {
        queries.push(query);
        assert.equal(query.filter.kind, 'user');
        assert.equal(options.credentials, credentials);
        // Catalog annotation filtering can be case-insensitive. The installed
        // auth resolver must still enforce exact identity before issuing a token.
        const requested = query.filter[`metadata.annotations.${annotation}`];
        const stored = catalogUser.metadata.annotations[annotation];
        return { items: stored.toLowerCase() === requested.toLowerCase() ? [catalogUser] : [] };
      },
    },
  }).userIdMatchingUserEntityAnnotation();
  const context = {
    async resolveOwnershipEntityRefs(entity) {
      assert.equal(entity, catalogUser);
      return { ownershipEntityRefs: ownership };
    },
    async issueToken(input) {
      issued.push(input);
      return { token: 'test-token' };
    },
  };
  const signIn = (nodeId, username = 'carabaestlein') => resolver({
    result: { fullProfile: { nodeId, id: '34475835', username } },
    profile: { displayName: 'Test GitHub profile' },
  }, context);
  return { signIn, issued, queries };
}

test('the real catalog maps the verified GraphQL node ID even after a username change', async () => {
  assert.equal(user.metadata.annotations[annotation], verifiedNodeId,
    'Use GitHub node_id, not the numeric REST id, in the catalog annotation');
  const subject = fixture();
  for (const username of ['carabaestlein', 'renamed-account']) {
    assert.deepEqual(await subject.signIn(verifiedNodeId, username), { token: 'test-token' });
  }
  assert.deepEqual(subject.issued, [
    { claims: { sub: ownership[0], ent: ownership } },
    { claims: { sub: ownership[0], ent: ownership } },
  ]);
  assert.ok(subject.queries.every(query => query.filter[`metadata.annotations.${annotation}`] === verifiedNodeId));
});

test('numeric, unrelated and missing node IDs cannot issue a token, including the old catalog configuration', async () => {
  for (const nodeId of ['34475835', 'MDQ6VXNlcjEyMzQ1Njc4', undefined]) {
    const subject = fixture();
    await assert.rejects(subject.signIn(nodeId));
    assert.equal(subject.issued.length, 0);
  }
  const oldUser = structuredClone(user);
  oldUser.metadata.annotations[annotation] = '34475835';
  const oldConfiguration = fixture(oldUser);
  await assert.rejects(oldConfiguration.signIn(verifiedNodeId));
  assert.equal(oldConfiguration.issued.length, 0);
});

test('a case-insensitive catalog result cannot authorize a different node ID', async () => {
  const subject = fixture();
  await assert.rejects(subject.signIn(verifiedNodeId.toLowerCase()), /does not match the catalog user/);
  assert.equal(subject.queries.length, 1);
  assert.equal(subject.issued.length, 0);
});

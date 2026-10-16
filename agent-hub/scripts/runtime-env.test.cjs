'use strict';

const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const path = require('node:path');
const { test } = require('node:test');
const { rootCertificates } = require('node:tls');

const hook = path.join(__dirname, 'runtime-env.cjs');
const certificate = rootCertificates[0];
const encoded = Buffer.from(certificate).toString('base64');

function invoke(value, code = '') {
  const env = value === undefined ? {} : { POSTGRES_CA_CERT_BASE64: value };
  return spawnSync(process.execPath, ['--require', hook, '-e', code, '--', '--config', 'app-config.production.yaml'], {
    env,
    encoding: 'utf8',
  });
}

test('preloads a public root CA before the application and preserves arguments', () => {
  const child = invoke(encoded, `
    const assert = require('node:assert/strict');
    const { X509Certificate } = require('node:crypto');
    assert.ok(process.env.POSTGRES_CA_CERT.includes('\\n'));
    assert.ok(new X509Certificate(process.env.POSTGRES_CA_CERT).ca);
    assert.equal(process.env.POSTGRES_CA_CERT_BASE64, undefined);
    assert.deepEqual(process.argv.slice(1), ['--config', 'app-config.production.yaml']);
  `);
  assert.equal(child.status, 0, child.stderr);
  assert.equal(child.stdout, '');
  assert.equal(child.stderr, '');
});

for (const [label, value] of [
  ['missing input', undefined],
  ['invalid base64', 'sensitive-not-base64!'],
  ['embedded newline', `${encoded}\n`],
  ['encoded non-certificate', Buffer.from('sensitive-invalid-certificate').toString('base64')],
  ['invalid PEM body', Buffer.from('-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n').toString('base64')],
]) {
  test(`fails before starting the application for ${label}`, () => {
    const child = invoke(value, 'process.stdout.write("APPLICATION_STARTED")');
    assert.notEqual(child.status, 0);
    assert.equal(child.stdout, '');
    assert.match(child.stderr, /POSTGRES_CA_CERT_BASE64 must contain one valid PEM CA certificate/);
    assert.ok(!child.stderr.includes('sensitive-'));
    if (value) assert.ok(!child.stderr.includes(value));
  });
}

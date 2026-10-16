'use strict';

// Aiven Runtime transports environment values on one line. Decode the CA before
// Backstage reads app-config.production.yaml; never weaken TLS verification.
const { X509Certificate } = require('node:crypto');

const encoded = process.env.POSTGRES_CA_CERT_BASE64;
let certificate;
try {
  if (
    typeof encoded !== 'string' ||
    encoded.length === 0 ||
    encoded.length > 131072 ||
    !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(encoded)
  ) {
    throw new Error();
  }
  const bytes = Buffer.from(encoded, 'base64');
  if (bytes.toString('base64') !== encoded) throw new Error();
  certificate = bytes.toString('utf8');
  if (!/^-----BEGIN CERTIFICATE-----\r?\n(?:[A-Za-z0-9+/=]+\r?\n)+-----END CERTIFICATE-----(?:\r?\n)?$/.test(certificate)) {
    throw new Error();
  }
  if (!new X509Certificate(certificate).ca) throw new Error();
} catch {
  // Deliberately omit the supplied value and the crypto parser's diagnostics.
  throw new Error('POSTGRES_CA_CERT_BASE64 must contain one valid PEM CA certificate encoded as canonical single-line base64.');
}

process.env.POSTGRES_CA_CERT = certificate;
delete process.env.POSTGRES_CA_CERT_BASE64;

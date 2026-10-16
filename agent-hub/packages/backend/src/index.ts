import { createBackend } from '@backstage/backend-defaults';

const backend = createBackend();
backend.add(import('@backstage/plugin-app-backend'));
backend.add(import('@backstage/plugin-auth-backend'));
backend.add(import('@backstage/plugin-auth-backend-module-github-provider'));
// Guest tokens are only available in local development, never in the Runtime image.
if (process.env.NODE_ENV !== 'production') {
  backend.add(import('@backstage/plugin-auth-backend-module-guest-provider'));
}
backend.add(import('@backstage/plugin-catalog-backend'));
backend.add(import('@backstage/plugin-catalog-backend-module-scaffolder-entity-model'));
backend.add(import('@backstage/plugin-catalog-backend-module-logs'));
backend.add(import('@backstage/plugin-scaffolder-backend'));
backend.add(import('@backstage/plugin-scaffolder-backend-module-github'));
backend.start();

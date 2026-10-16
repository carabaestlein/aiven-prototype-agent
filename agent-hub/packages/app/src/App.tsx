import { Navigate, Route } from 'react-router-dom';
import { CatalogEntityPage, CatalogIndexPage, catalogPlugin } from '@backstage/plugin-catalog';
import { CatalogImportPage, catalogImportPlugin } from '@backstage/plugin-catalog-import';
import { ScaffolderPage, scaffolderPlugin } from '@backstage/plugin-scaffolder';
import { UserSettingsPage } from '@backstage/plugin-user-settings';
import { AlertDisplay, OAuthRequestDialog, SignInPage } from '@backstage/core-components';
import { createApp } from '@backstage/app-defaults';
import { AppRouter, FlatRoutes } from '@backstage/core-app-api';
import { configApiRef, githubAuthApiRef, useApi, SignInPageProps } from '@backstage/core-plugin-api';
import { apis } from './apis';
import { entityPage } from './components/catalog/EntityPage';
import { Root } from './components/Root';

const HubSignInPage = (props: SignInPageProps) => {
  const config = useApi(configApiRef);
  return <SignInPage {...props} auto providers={config.getOptionalString('auth.environment') === 'development' ? ['guest'] : [{ id: 'github-auth-provider', title: 'GitHub', message: 'Sign in with your approved GitHub account', apiRef: githubAuthApiRef }]} />;
};
const app = createApp({
  apis,
  bindRoutes({ bind }) {
    bind(catalogPlugin.externalRoutes, { createComponent: scaffolderPlugin.routes.root, createFromTemplate: scaffolderPlugin.routes.selectedTemplate });
    bind(scaffolderPlugin.externalRoutes, { registerComponent: catalogImportPlugin.routes.importPage });
  },
  components: { SignInPage: HubSignInPage },
});
const routes = <FlatRoutes>
  <Route path="/" element={<Navigate to="catalog" />} />
  <Route path="/catalog" element={<CatalogIndexPage initiallySelectedFilter="all" />} />
  <Route path="/catalog/:namespace/:kind/:name" element={<CatalogEntityPage />}>{entityPage}</Route>
  <Route path="/create" element={<ScaffolderPage />} />
  <Route path="/catalog-import" element={<CatalogImportPage />} />
  <Route path="/settings" element={<UserSettingsPage />} />
</FlatRoutes>;
export default app.createRoot(<><AlertDisplay /><OAuthRequestDialog /><AppRouter><Root>{routes}</Root></AppRouter></>);

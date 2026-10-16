import { Navigate, Route } from 'react-router-dom';
import { CatalogEntityPage, catalogPlugin } from '@backstage/plugin-catalog';
import { CatalogImportPage, catalogImportPlugin } from '@backstage/plugin-catalog-import';
import { ScaffolderPage, scaffolderPlugin } from '@backstage/plugin-scaffolder';
import { UserSettingsPage } from '@backstage/plugin-user-settings';
import { AlertDisplay, OAuthRequestDialog, SignInPage } from '@backstage/core-components';
import { createApp } from '@backstage/app-defaults';
import { AppRouter, FlatRoutes } from '@backstage/core-app-api';
import { configApiRef, githubAuthApiRef, useApi, SignInPageProps, createRoutableExtension } from '@backstage/core-plugin-api';
import { apis } from './apis';
import { entityPage } from './components/catalog/EntityPage';
import { Root } from './components/Root';
import { UnifiedThemeProvider } from '@backstage/theme';
import BubbleChartOutlined from '@material-ui/icons/BubbleChartOutlined';
import { aivenTheme } from './theme';
import { CatalogPage } from './components/catalog/CatalogPage';
import { TemplateLibrary } from './components/create/TemplateLibrary';

const AgentCatalogPage = catalogPlugin.provide(createRoutableExtension({
  name: 'AgentCatalogPage',
  component: () => Promise.resolve(CatalogPage),
  mountPoint: catalogPlugin.routes.catalogIndex,
}));

const HubSignInPage = (props: SignInPageProps) => {
  const config = useApi(configApiRef);
  return <SignInPage {...props} auto providers={config.getOptionalString('auth.environment') === 'development' ? ['guest'] : [{ id: 'github-auth-provider', title: 'GitHub', message: 'Sign in with your approved GitHub account', apiRef: githubAuthApiRef }]} />;
};
const app = createApp({
  apis,
  themes: [{ id: 'aiven', title: 'Aiven', variant: 'dark', icon: <BubbleChartOutlined />, Provider: ({ children }) => <UnifiedThemeProvider theme={aivenTheme}>{children}</UnifiedThemeProvider> }],
  bindRoutes({ bind }) {
    bind(catalogPlugin.externalRoutes, { createComponent: scaffolderPlugin.routes.root, createFromTemplate: scaffolderPlugin.routes.selectedTemplate });
    bind(scaffolderPlugin.externalRoutes, { registerComponent: catalogImportPlugin.routes.importPage });
  },
  components: { SignInPage: HubSignInPage },
});
const routes = <FlatRoutes>
  <Route path="/" element={<Navigate to="catalog" />} />
  <Route path="/catalog" element={<AgentCatalogPage />} />
  <Route path="/catalog/:namespace/:kind/:name" element={<CatalogEntityPage />}>{entityPage}</Route>
  <Route path="/create" element={<ScaffolderPage components={{ EXPERIMENTAL_TemplateListPageComponent: TemplateLibrary }} headerOptions={{ title: 'Create an agent', subtitle: 'Your agent. Your platform. Start with the approved LangGraph setup.' }} />} />
  <Route path="/catalog-import" element={<CatalogImportPage />} />
  <Route path="/settings" element={<UserSettingsPage />} />
</FlatRoutes>;
export default app.createRoot(<><AlertDisplay /><OAuthRequestDialog /><AppRouter><Root>{routes}</Root></AppRouter></>);

import { Grid } from '@material-ui/core';
import { EntityAboutCard, EntityLayout, EntityLinksCard, EntityDependsOnResourcesCard, EntityHasComponentsCard, EntitySwitch, isKind } from '@backstage/plugin-catalog';

export const entityPage = <EntityLayout>
  <EntityLayout.Route path="/" title="Overview">
    <Grid container spacing={3}>
      <Grid item xs={12} md={6}><EntityAboutCard /></Grid>
      <Grid item xs={12} md={6}><EntityLinksCard /></Grid>
      <Grid item xs={12}><EntitySwitch><EntitySwitch.Case if={isKind('component')}><EntityDependsOnResourcesCard /></EntitySwitch.Case><EntitySwitch.Case if={isKind('system')}><EntityHasComponentsCard /></EntitySwitch.Case></EntitySwitch></Grid>
    </Grid>
  </EntityLayout.Route>
</EntityLayout>;
